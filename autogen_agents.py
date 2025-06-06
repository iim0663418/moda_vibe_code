import logging
import httpx
import tiktoken
from typing import Dict, List, Any, Optional, Callable
from datetime import datetime
from enum import Enum
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.teams import RoundRobinGroupChat, GraphFlow
from autogen_agentchat.graph import DiGraph
from autogen_agentchat.conditions import ExternalTermination, TextMentionTermination
from autogen_ext.models.azure import AzureAIChatCompletionClient
from autogen_ext.tools.mcp import McpWorkbench, McpServerConfig
from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import ResourceNotFoundError
from token_utils import get_encoding_for_model, count_tokens_safe

logger = logging.getLogger(__name__)


class AgentStatus(Enum):
    """Agent status enumeration."""
    IDLE = "idle"
    ACTIVE = "active"
    PROCESSING = "processing"
    COMPLETED = "completed"
    ERROR = "error"


class AgentMetadata:
    """Agent metadata container."""
    def __init__(self, name: str, role: str, description: str, capabilities: List[str]):
        self.name = name
        self.role = role
        self.description = description
        self.capabilities = capabilities
        self.status = AgentStatus.IDLE
        self.message_count = 0
        self.last_activity = None
        self.error_count = 0

# HTTPToolWorkbench class is removed as it's being replaced by McpWorkbench

class VibeCodeMultiAgentSystem:
    def __init__(self, azure_openai_api_key: str, azure_openai_endpoint: str, azure_openai_deployment_name: str, azure_openai_api_version: str, mcp_config: Dict[str, str]):
        # Apply tiktoken monkey patch for better error handling
        self._apply_tiktoken_patch()
        
        # Validate API key
        if not azure_openai_api_key or azure_openai_api_key == "test-key":
            raise ValueError("Azure OpenAI API key is required and cannot be empty or test value")
        
        if not azure_openai_endpoint or azure_openai_endpoint == "https://test.openai.azure.com":
            raise ValueError("Azure OpenAI endpoint is required and cannot be empty or test value")
        
        if not azure_openai_deployment_name:
            raise ValueError("Azure OpenAI deployment name is required")
        
        if not azure_openai_api_version:
            raise ValueError("Azure OpenAI API version is required")
        
        # Initialize model client with correct Azure AI configuration
        try:
            # Clean endpoint format for Azure OpenAI
            clean_endpoint = azure_openai_endpoint.rstrip('/')
            
            # Use correct Azure AI configuration for AzureAIChatCompletionClient
            self.model_client = AzureAIChatCompletionClient(
                model=azure_openai_deployment_name,
                endpoint=clean_endpoint,
                credential=AzureKeyCredential(azure_openai_api_key),
                model_info={
                    "json_output": True,
                    "function_calling": True,
                    "vision": False,
                    "family": "gpt",
                    "structured_output": True,
                }
            )
            logger.info(f"Azure AI client initialized successfully with deployment: {azure_openai_deployment_name}")
        except Exception as e:
            logger.error(f"Failed to initialize Azure AI client: {e}")
            raise ValueError(f"Failed to initialize Azure AI client: {e}")
        
        # Store MCP configuration
        self.mcp_config = mcp_config
        
        # Initialize McpWorkbench
        mcp_servers_config = []
        if mcp_config.get('fetch_url'):
            mcp_servers_config.append(McpServerConfig(name="fetch", url=mcp_config['fetch_url']))
        if mcp_config.get('brave_search_url'):
            mcp_servers_config.append(McpServerConfig(name="brave", url=mcp_config['brave_search_url']))
        if mcp_config.get('github_url'):
            mcp_servers_config.append(McpServerConfig(name="github", url=mcp_config['github_url']))
        # Add other MCP servers as needed, e.g., filesystem, memory
        # Example: mcp_servers_config.append(McpServerConfig(name="filesystem", url="http://localhost:3003"))

        self.workbench = McpWorkbench(mcp_servers=mcp_servers_config, default_timeout=mcp_config.get('timeout', 30))
        logger.info(f"McpWorkbench initialized with servers: {[s.name for s in mcp_servers_config]}")
        
        # Store Azure OpenAI configuration for fallback use
        self._azure_openai_api_key = azure_openai_api_key
        self._azure_openai_endpoint = clean_endpoint
        self._azure_openai_deployment_name = azure_openai_deployment_name
        self._azure_openai_api_version = azure_openai_api_version # Store API version
        
        # Agent definitions
        self.fetcher_agent = None
        self.summarizer_agent = None
        self.analyzer_agent = None
        self.coordinator_agent = None
        self.responder_agent = None
        self.group_chat = None
        
        # Agent metadata tracking
        self.agent_metadata = {}
        self.conversation_session_id = None
        self.session_start_time = None
        
        # Initialize agent metadata
        self._initialize_agent_metadata()
    
    def _apply_tiktoken_patch(self):
        """Apply monkey patch to tiktoken for better error handling with fallback."""
        # Store original function
        original_encoding_for_model = tiktoken.encoding_for_model
        
        def patched_encoding_for_model(model_name: str):
            """
            Patched version of tiktoken.encoding_for_model with fallback to cl100k_base.
            """
            try:
                return original_encoding_for_model(model_name)
            except KeyError:
                logger.warning(f"Model {model_name} not found in tiktoken. Using cl100k_base encoding as fallback.")
                return tiktoken.get_encoding("cl100k_base")
        
        # Apply the patch
        tiktoken.encoding_for_model = patched_encoding_for_model
        logger.info("Applied tiktoken monkey patch for better error handling")
    
    def _initialize_agent_metadata(self):
        """Initialize metadata for all agents."""
        self.agent_metadata = {
            "fetcher": AgentMetadata(
                name="fetcher",
                role="Data Retrieval Specialist",
                description="Fetches and gathers information from various sources",
                capabilities=["web_scraping", "search", "data_retrieval", "source_validation"]
            ),
            "summarizer": AgentMetadata(
                name="summarizer", 
                role="Content Summarization Expert",
                description="Condenses and summarizes complex information",
                capabilities=["text_summarization", "key_extraction", "content_synthesis", "brevity_optimization"]
            ),
            "analyzer": AgentMetadata(
                name="analyzer",
                role="Data Analysis Specialist", 
                description="Analyzes patterns, trends and provides insights",
                capabilities=["pattern_analysis", "trend_identification", "correlation_analysis", "insight_generation"]
            ),
            "coordinator": AgentMetadata(
                name="coordinator",
                role="Workflow Coordinator",
                description="Manages workflow and coordinates between agents", 
                capabilities=["task_management", "workflow_optimization", "conflict_resolution", "priority_setting"]
            ),
            "responder": AgentMetadata(
                name="responder",
                role="Response Generation Expert",
                description="Synthesizes final responses for user queries",
                capabilities=["response_synthesis", "content_formatting", "clarity_optimization", "user_communication"]
            )
        }
    
    def _update_agent_status(self, agent_name: str, status: AgentStatus, increment_message: bool = False):
        """Update agent status and activity tracking."""
        if agent_name in self.agent_metadata:
            metadata = self.agent_metadata[agent_name]
            metadata.status = status
            metadata.last_activity = datetime.utcnow()
            if increment_message:
                metadata.message_count += 1
    
    def _increment_agent_error(self, agent_name: str):
        """Increment error count for an agent."""
        if agent_name in self.agent_metadata:
            self.agent_metadata[agent_name].error_count += 1
            self.agent_metadata[agent_name].status = AgentStatus.ERROR
    
    def _create_error_response(self, error_message: str, error_type: str, original_error: str) -> Dict[str, Any]:
        """Create a standardized error response that can be safely serialized."""
        # Mark error state for any active agents
        for agent_name, metadata in self.agent_metadata.items():
            if metadata.status == AgentStatus.ACTIVE or metadata.status == AgentStatus.PROCESSING:
                self._increment_agent_error(agent_name)
        
        # Create serializable error response
        error_response = {
            "final_response": error_message,
            "conversation_history": [
                {
                    "agent": "error_handler",
                    "content": error_message,
                    "timestamp": datetime.utcnow().isoformat(),
                    "message_id": f"msg_error_{datetime.utcnow().timestamp()}",
                    "sequence_number": 0,
                    "agent_role": "Error Handler",
                    "agent_description": f"Handles {error_type} errors",
                    "message_length": len(error_message),
                    "error_type": error_type,
                    "original_error": str(original_error)[:500]  # Truncate long error messages
                }
            ],
            "total_messages": 1,
            "session_metadata": {
                "session_id": getattr(self, 'conversation_session_id', 'unknown'),
                "session_start_time": getattr(self, 'session_start_time', datetime.utcnow()).isoformat(),
                "session_duration_seconds": 0,
                "participating_agents": [],
                "agent_count": 0,
                "error": {
                    "type": error_type,
                    "message": str(original_error)[:500],  # Truncate for serialization
                    "handled": True,
                    "timestamp": datetime.utcnow().isoformat()
                }
            },
            "agent_statuses": self.get_agent_statuses()
        }
        
        return error_response
    
    async def fallback_single_agent_simulation(self, content: str) -> Dict[str, Any]:
        """
        Fallback method using single Azure OpenAI call to simulate multi-agent collaboration.
        Used when AutoGen GroupChat fails.
        """
        logger.info("Using fallback single agent simulation for multi-agent collaboration")
        
        # Multi-agent simulation prompt template
        simulation_prompt = f"""
You are a sophisticated AI system that simulates a multi-agent collaboration process. 
You need to process the user's request by thinking through the perspective of 5 different specialized agents:

1. **Fetcher Agent** (Data Retrieval Specialist): Identifies what information needs to be gathered
2. **Summarizer Agent** (Content Expert): Condenses and organizes information  
3. **Analyzer Agent** (Data Analysis Specialist): Analyzes patterns and provides insights
4. **Coordinator Agent** (Workflow Manager): Manages the overall process and ensures quality
5. **Responder Agent** (Communication Expert): Synthesizes the final response

Process the following user request through this multi-agent simulation:

**User Request:** {content}

**Instructions:**
- Think step by step through each agent's perspective
- Show the reasoning and contribution of each agent
- Provide a comprehensive final response that synthesizes all agents' work
- Format your response to show the collaborative process

**Response Format:**
```
🔍 Fetcher Agent Analysis:
[What information/data needs to be gathered for this request]

📋 Summarizer Agent Processing:
[How to organize and structure the information]

📊 Analyzer Agent Insights:
[Analysis, patterns, and insights to be considered]

🎯 Coordinator Agent Management:
[Overall process coordination and quality control]

💬 Final Response (Responder Agent):
[Comprehensive final answer synthesizing all agents' contributions]
```
"""
        
        try:
            from openai import AsyncAzureOpenAI
            
            # Extract Azure OpenAI configuration from existing client or from initialization parameters
            api_key = None
            endpoint = None
            deployment_name = None
            api_version = None
            
            # Try multiple ways to extract configuration
            if hasattr(self.model_client, '_credential') and hasattr(self.model_client._credential, 'key'):
                api_key = self.model_client._credential.key
            
            if hasattr(self.model_client, '_endpoint'):
                endpoint = self.model_client._endpoint
            elif hasattr(self.model_client, 'endpoint'):
                endpoint = self.model_client.endpoint
                
            if hasattr(self.model_client, '_model'):
                deployment_name = self.model_client._model
            elif hasattr(self.model_client, 'model'):
                deployment_name = self.model_client.model
            
            # If we can't extract from client, try to use initialization parameters stored during __init__
            if not api_key or not endpoint or not deployment_name or not api_version:
                # Store these during initialization for fallback use
                if hasattr(self, '_azure_openai_api_key'):
                    api_key = api_key or self._azure_openai_api_key
                if hasattr(self, '_azure_openai_endpoint'):
                    endpoint = endpoint or self._azure_openai_endpoint
                if hasattr(self, '_azure_openai_deployment_name'):
                    deployment_name = deployment_name or self._azure_openai_deployment_name
                if hasattr(self, '_azure_openai_api_version'):
                    api_version = api_version or self._azure_openai_api_version
            
            if not all([api_key, endpoint, deployment_name, api_version]):
                logger.error(f"Configuration extraction failed - API Key: {'✓' if api_key else '✗'}, Endpoint: {'✓' if endpoint else '✗'}, Deployment: {'✓' if deployment_name else '✗'}, API Version: {'✓' if api_version else '✗'}")
                raise ValueError("Failed to extract Azure OpenAI configuration for fallback")
            
            # Create Azure OpenAI client for fallback
            fallback_client = AsyncAzureOpenAI(
                api_key=api_key,
                api_version=api_version,
                azure_endpoint=endpoint.rstrip('/')
            )
            
            # Call Azure OpenAI with simulation prompt
            response = await fallback_client.chat.completions.create(
                model=deployment_name,
                messages=[
                    {"role": "system", "content": "You are a multi-agent simulation system that provides comprehensive analysis through multiple specialized perspectives."},
                    {"role": "user", "content": simulation_prompt}
                ],
                max_tokens=2000,
                temperature=0.7
            )
            
            await fallback_client.close()
            
            fallback_response = response.choices[0].message.content.strip()
            
            # Create response in the expected format
            return {
                "final_response": fallback_response,
                "conversation_history": [
                    {
                        "agent": "fallback_simulator",
                        "content": fallback_response,
                        "timestamp": datetime.utcnow().isoformat(),
                        "message_id": f"msg_fallback_{datetime.utcnow().timestamp()}",
                        "sequence_number": 0,
                        "agent_role": "Multi-Agent Simulator",
                        "agent_description": "Fallback system simulating multi-agent collaboration through single Azure OpenAI call",
                        "message_length": len(fallback_response),
                        "fallback_mode": True
                    }
                ],
                "total_messages": 1,
                "session_metadata": {
                    "session_id": getattr(self, 'conversation_session_id', f'fallback_{datetime.utcnow().timestamp()}'),
                    "session_start_time": datetime.utcnow().isoformat(),
                    "session_duration_seconds": 0,
                    "participating_agents": ["fallback_simulator"],
                    "agent_count": 1,
                    "fallback_mode": True,
                    "original_request": content
                },
                "agent_statuses": {
                    "fallback_simulator": {
                        "name": "fallback_simulator",
                        "role": "Multi-Agent Simulator",
                        "description": "Single Azure OpenAI call simulating multi-agent collaboration",
                        "capabilities": ["multi_agent_simulation", "comprehensive_analysis", "error_recovery"],
                        "status": "completed",
                        "message_count": 1,
                        "last_activity": datetime.utcnow().isoformat(),
                        "error_count": 0,
                        "fallback_mode": True
                    }
                }
            }
            
        except Exception as e:
            logger.error(f"Fallback single agent simulation failed: {e}")
            # Return a basic error response if even fallback fails
            error_msg = f"Both multi-agent system and fallback simulation failed. Error: {str(e)}"
            return self._create_error_response(error_msg, "FallbackSimulationError", str(e))

    async def start(self):
        """Initialize the multi-agent system."""
        # McpWorkbench is initialized in __init__ and does not require explicit start/aenter for this use case
        # if it were managing its own client lifecycle directly, it might.
        logger.debug("VibeCodeMultiAgentSystem start called. McpWorkbench should be already initialized.")

        # Create specialized agents with specific system messages
        logger.debug("Creating fetcher_agent...")
        self.fetcher_agent = AssistantAgent(
            name="fetcher",
            model_client=self.model_client,
            system_message="""You are a data fetcher agent. Your role is to:
1. Fetch content from URLs using web scraping
2. Search for information using Brave Search
3. Retrieve data from various online sources
4. Parse and clean fetched data
Always respond with structured data and indicate the source of information.""",
            reflect_on_tool_use=True,
        )
        logger.debug("fetcher_agent created.")
        
        logger.debug("Creating summarizer_agent...")
        self.summarizer_agent = AssistantAgent(
            name="summarizer",
            model_client=self.model_client,
            system_message="""You are a content summarizer agent. Your role is to:
1. Summarize long documents and articles
2. Extract key points and main ideas
3. Create concise but comprehensive summaries
4. Maintain the original context and meaning
Focus on clarity and brevity while preserving important details.""",
            reflect_on_tool_use=True,
        )
        logger.debug("summarizer_agent created.")
        
        logger.debug("Creating analyzer_agent...")
        self.analyzer_agent = AssistantAgent(
            name="analyzer",
            model_client=self.model_client,
            system_message="""You are a data analyzer agent. Your role is to:
1. Analyze patterns and trends in data
2. Perform comparative analysis
3. Identify insights and correlations
4. Generate analytical reports
Provide objective analysis with evidence-based conclusions.""",
            reflect_on_tool_use=True,
        )
        logger.debug("analyzer_agent created.")
        
        logger.debug("Creating coordinator_agent...")
        self.coordinator_agent = AssistantAgent(
            name="coordinator",
            model_client=self.model_client,
            system_message="""You are a coordination agent. Your role is to:
1. Understand the user's overall goal and break it down into sub-tasks.
2. Coordinate tasks between the fetcher, summarizer, analyzer, and responder agents.
3. Manage the workflow: decide which agent should act next and provide clear instructions.
4. Ensure all agents work towards the common goal and that their outputs are relevant.
5. Resolve conflicts or ambiguities in information if they arise.
6. When you believe all necessary information has been gathered, summarized, and analyzed, instruct the responder_agent to synthesize the final response.
Focus on efficient task management, clear communication, and guiding the team to a comprehensive solution.""",
            reflect_on_tool_use=True,
        )
        logger.debug("coordinator_agent created.")
        
        logger.debug("Creating responder_agent...")
        self.responder_agent = AssistantAgent(
            name="responder",
            model_client=self.model_client,
            system_message="""You are a response generation agent. Your role is to:
1. Synthesize information provided by the fetcher, summarizer, and analyzer agents, as coordinated by the coordinator.
2. Generate a final, coherent, and comprehensive response to the user's query.
3. Ensure the response directly addresses the user's request and incorporates all relevant insights.
4. Format the response appropriately for clarity and readability.
5. Once you have formulated the complete final response, end your message with "TASK_COMPLETE".
Create clear, comprehensive, and user-friendly responses.""",
            reflect_on_tool_use=True,
        )
        logger.debug("responder_agent created.")

        # Setup group chat with agents using RoundRobinGroupChat
        # Define termination condition
        text_termination = TextMentionTermination("TASK_COMPLETE")
        logger.debug("Setting up GraphFlow...")

        # Define a decision function for the graph
        def decide_next_step_after_analysis(messages: List[Dict[str, Any]]) -> Optional[str]:
            if not messages:
                return None # Or raise error
            last_message_content = messages[-1].get("content", "").lower()
            # Simple decision logic, can be made more sophisticated
            if "需要更多資訊" in last_message_content or "clarification needed" in last_message_content:
                logger.info("Decision: Analysis requires more data, looping back to fetcher.")
                return "fetcher"
            elif "task_complete" in last_message_content: # If analyzer somehow says task complete
                 logger.info("Decision: Analysis indicates task is complete, proceeding to responder.")
                 return "responder"
            else: # Default to responder if analysis seems sufficient
                logger.info("Decision: Analysis seems sufficient, proceeding to responder.")
                return "responder"

        graph = DiGraph()
        graph.add_node("fetcher", self.fetcher_agent)
        graph.add_node("summarizer", self.summarizer_agent)
        graph.add_node("analyzer", self.analyzer_agent)
        graph.add_node("responder", self.responder_agent)
        
        # The coordinator's role is now partly embedded in the graph logic
        # and the decision function. We might not need a separate coordinator node
        # if the graph structure and decision functions handle its responsibilities.
        # For now, we'll keep the coordinator_agent instance if its system message
        # is still useful for general guidance or if it's used in a more complex graph.
        # However, for a simple sequential flow with a decision, it might be replaced by functions.

        graph.add_edge("fetcher", "summarizer")
        graph.add_edge("summarizer", "analyzer")
        
        # Conditional routing after analyzer
        # The 'decide_next_step_after_analysis' function will be called by the GraphFlow
        # when a message is sent from the 'analyzer' node, if 'analyzer' is configured
        # as a speaker that can transition to multiple next speakers based on a condition.
        # AutoGen's GraphFlow typically uses a registered function with an agent or a special
        # 'selector' node for this. For simplicity here, we'll assume the GraphFlow
        # can be configured to use such a function or that the 'analyzer' agent itself
        # can suggest the next step based on its output, which GraphFlow can interpret.
        # A more robust way is to use a dedicated function node or a selector.
        # Let's define a functional node for decision making.
        
        # We need to register the decision function with an agent or use a mechanism
        # that GraphFlow supports for conditional branching.
        # A common pattern is to have an agent whose reply determines the next step.
        # Or, use a selector_dict in add_edge for more complex routing.

        # For now, let's assume a simplified conditional edge based on a selector function
        # that GraphFlow can use. The actual implementation might require
        # registering this function with a (perhaps dummy) agent or using specific
        # GraphFlow features for conditional routing.

        # Simplified approach: Analyzer's output is passed to a selector.
        # This requires `analyzer` to be a `Speaker` that can have conditional next speakers.
        # Or, we add a functional node.
        
        # Let's try adding a functional node for the decision.
        # This function node will receive the last message (from analyzer) and decide.
        graph.add_node(
            name="decision_node",
            agent=decide_next_step_after_analysis # This assumes GraphFlow can take a callable as a node
                                               # More typically, this logic is part of a Speaker's `generate_reply`
                                               # or a specific selector mechanism in GraphFlow.
                                               # For now, this is a placeholder for the decision logic.
                                               # AutoGen's GraphFlow expects agents as nodes.
                                               # So, the decision logic might need to be wrapped in a simple agent
                                               # or handled by the 'analyzer' agent itself by suggesting the next speaker.
        )
        graph.add_edge("analyzer", "decision_node")
        graph.add_edge("decision_node", "fetcher", condition=lambda msg_content: msg_content == "fetcher")
        graph.add_edge("decision_node", "responder", condition=lambda msg_content: msg_content == "responder")


        # The entry_point and exit_points need to be defined.
        # Let's assume the initial message goes to the fetcher.
        # The final response comes from the responder.
        self.group_chat = GraphFlow(
            graph=graph,
            entry_point="fetcher", 
            # exit_points=["responder"], # GraphFlow might not use exit_points like this,
                                      # termination is usually handled by agent messages or max_rounds.
            max_round=20 # Increased max_round for potentially complex flows
        )
        logger.info("GraphFlow setup complete.")

    async def stop(self):
        """Stop the multi-agent system and clean up resources."""
        try:
            await self.model_client.close()
            logger.info("Model client closed.")
        except Exception as e:
            logger.error(f"Error closing model client: {e}")
        
        if self.workbench is not None:
            # McpWorkbench does not have an __aexit__ in the same way HTTPToolWorkbench did for its httpx.AsyncClient
            # If McpWorkbench manages resources that need explicit closing, it should provide a close() method.
            # For now, we assume its resources are managed internally or don't require explicit async closing.
            logger.info("McpWorkbench does not require explicit async closing in this context.")
            pass

    async def send_message(self, content: str, recipient_agent_type: str = "coordinator") -> Dict[str, Any]:
        """Send a message to the multi-agent system and get a response with enhanced conversation history."""
        if self.group_chat is None:
            logger.error("Attempted to send message but multi-agent system (group_chat) is not started.")
            raise RuntimeError("Multi-agent system not started. Call start() before sending messages.")

        # Initialize session tracking
        if not self.session_start_time:
            self.session_start_time = datetime.utcnow()
            import uuid
            self.conversation_session_id = str(uuid.uuid4())
            logger.info(f"New conversation session started. ID: {self.conversation_session_id}")

        # Reset agent statuses at start of conversation
        for agent_name in self.agent_metadata:
            self._update_agent_status(agent_name, AgentStatus.IDLE)
        logger.debug("Agent statuses reset to IDLE for new message.")

        try:
            from autogen_core import CancellationToken
            
            # Mark conversation as starting
            # For GraphFlow, the recipient_agent_type might be less relevant if entry_point is fixed.
            # However, we can still use it to mark the initial target or a conceptual recipient.
            initial_speaker_name = self.group_chat.entry_point if isinstance(self.group_chat.entry_point, str) else self.group_chat.entry_point.name
            self._update_agent_status(initial_speaker_name, AgentStatus.ACTIVE) # Mark entry point as active
            logger.info(f"Sending message to GraphFlow. Entry point: {initial_speaker_name}. Content: '{content[:50]}...'")
            
            # Run the team with the user message with specific error handling
            try:
                # GraphFlow's run method might take messages list directly
                # For a new task, we typically provide the initial message.
                # The 'task' parameter might still be valid, or it might expect an initial message dict.
                # Referring to AutoGen docs: graph_flow.run(messages=[...], cancellation_token=...)
                # Let's assume the first message is from a "user_proxy" or similar.
                # For simplicity, we'll adapt the existing 'task=content' if possible,
                # or construct an initial message.
                
                # Constructing an initial message for GraphFlow
                # This part needs careful alignment with how GraphFlow expects initial input.
                # Typically, a UserProxyAgent sends the first message.
                # If VibeCodeMultiAgentSystem acts as the user proxy, it should format the message.
                
                # Let's assume GraphFlow's `run` can take a `task` string which it internally
                # uses to initiate the conversation with the entry_point agent.
                # If not, we'd need a UserProxyAgent or to manually craft the first message.
                # For now, we'll try with `task=content` and see if it's compatible or needs adjustment.
                
                # The result of graph_flow.run() is typically the list of messages in the conversation.
                result_messages = await self.group_chat.run(
                    # messages=[{"role": "user", "content": content, "name": "user_proxy_for_vibe_code"}], # Alternative
                    task=content, # Assuming this works by sending to entry_point
                    cancellation_token=CancellationToken()
                )
                logger.debug("GraphFlow run completed.")
                
                # Adapt the result processing if result_messages is a list of messages
                # The previous code expected `result.messages`. If `result_messages` is the list itself:
                processed_result = {"messages": result_messages}

            except ResourceNotFoundError as e:
                logger.error(f"Azure OpenAI Resource Not Found Error during group chat: {e}. Triggering fallback.")
                # Use fallback single agent simulation instead of returning error
                return await self.fallback_single_agent_simulation(content)
            except Exception as group_chat_error:
                error_class_name = type(group_chat_error).__name__
                # Check if it's a GroupChatError or similar autogen error
                if "GroupChat" in error_class_name or "Chat" in error_class_name or "Agent" in error_class_name:
                    logger.error(f"AutoGen specific error ({error_class_name}) during group chat: {group_chat_error}. Triggering fallback.")
                    # Use fallback single agent simulation instead of returning error
                    return await self.fallback_single_agent_simulation(content)
                else:
                    # Re-raise other exceptions to be handled by outer try/except
                    logger.error(f"Unhandled exception during group_chat.run: {group_chat_error}", exc_info=True)
                    raise
            
            # Extract conversation history and final response with enhanced metadata
            conversation_history = []
            final_response = ""
            participating_agents = set()
            
            # Use processed_result which should have a 'messages' attribute
            if hasattr(processed_result, 'messages') and processed_result['messages']:
                logger.debug(f"Processing {len(processed_result['messages'])} messages from GraphFlow result.")
                # Process all messages in the conversation
                for i, message_obj in enumerate(processed_result['messages']):
                    # Message object structure from GraphFlow might be different.
                    # Assuming it's a dict with 'role', 'content', and 'name' (for agent name)
                    # Or it could be an AgentMessage object with a 'sender' attribute.
                    
                    agent_name = "unknown"
                    msg_content = ""

                    if isinstance(message_obj, dict):
                        agent_name = message_obj.get("name") or message_obj.get("role", "unknown") # Prefer name if available
                        msg_content = str(message_obj.get("content", ""))
                    elif hasattr(message_obj, 'sender') and hasattr(message_obj, 'content'): # For AgentMessage like objects
                        agent_name = getattr(message_obj.sender, 'name', 'unknown_sender_object')
                        msg_content = str(message_obj.content)
                    elif hasattr(message_obj, 'source') and hasattr(message_obj, 'content'): # Compatibility with older structure
                        agent_name = getattr(message_obj.source, 'name', 'unknown_source_object')
                        msg_content = str(message_obj.content)
                    else:
                        logger.warning(f"Message object at index {i} has unexpected structure: {message_obj}")
                        continue

                    participating_agents.add(agent_name)
                    
                    # Update agent status and tracking
                    self._update_agent_status(agent_name, AgentStatus.PROCESSING, increment_message=True)
                    
                    # Create enhanced message with metadata
                    enhanced_message = {
                        "agent": agent_name,
                        "content": msg_content,
                        "timestamp": datetime.utcnow().isoformat(),
                        "message_id": f"msg_{self.conversation_session_id}_{i}",
                        "sequence_number": i,
                        "agent_role": self.agent_metadata.get(agent_name, {}).get("role", "Unknown Role") if agent_name in self.agent_metadata else "Unknown Agent",
                        "agent_description": self.agent_metadata.get(agent_name, {}).get("description", "") if agent_name in self.agent_metadata else "",
                        "message_length": len(msg_content)
                    }
                    conversation_history.append(enhanced_message)
                
                # Mark participating agents as completed
                for agent_name_iter in participating_agents: # Use a different variable name
                    self._update_agent_status(agent_name_iter, AgentStatus.COMPLETED)
                
                # Get the last message as final response
                if conversation_history: # Ensure there's at least one message
                    final_response = conversation_history[-1]["content"]
                else:
                    logger.warning("No messages in conversation_history after processing GraphFlow result.")
                    final_response = "No response generated."

            elif hasattr(processed_result, 'content'): # Fallback if result is a single content string
                logger.debug("GraphFlow result has 'content' attribute directly (unexpected for message list).")
                final_response = str(processed_result.content)
                conversation_history.append({
                    "agent": "system", 
                    "content": final_response,
                    "timestamp": datetime.utcnow().isoformat(),
                    "message_id": f"msg_{self.conversation_session_id}_0",
                    "sequence_number": 0,
                    "agent_role": "System", # Or determine
                    "agent_description": "System-level response",
                    "message_length": len(final_response)
                })
            else:
                logger.warning(f"Group chat result is not in expected format: {result}")
                final_response = str(result) # Fallback to string representation
                conversation_history.append({
                    "agent": "system", 
                    "content": final_response,
                    "timestamp": datetime.utcnow().isoformat(),
                    "message_id": f"msg_{self.conversation_session_id}_0",
                    "sequence_number": 0,
                    "agent_role": "System",
                    "agent_description": "System-level response",
                    "message_length": len(final_response)
                })

            # Calculate session statistics
            session_duration = (datetime.utcnow() - self.session_start_time).total_seconds()
            logger.info(f"Multi-agent processing complete. Final response length: {len(final_response)}. Duration: {session_duration:.2f}s.")
            
            return {
                "final_response": final_response,
                "conversation_history": conversation_history,
                "total_messages": len(conversation_history),
                "session_metadata": {
                    "session_id": self.conversation_session_id,
                    "session_start_time": self.session_start_time.isoformat(),
                    "session_duration_seconds": session_duration,
                    "participating_agents": list(participating_agents),
                    "agent_count": len(participating_agents)
                },
                "agent_statuses": self.get_agent_statuses()
            }

        except Exception as e:
            logger.error(f"Error processing message in send_message: {e}", exc_info=True)
            
            # Check if this error should trigger fallback
            should_use_fallback = False
            error_str = str(e)
            error_type = type(e).__name__
            
            # Check for ResourceNotFoundError in exception chain or error message
            if "ResourceNotFound" in error_type or "404" in error_str or "Resource not found" in error_str.lower():
                should_use_fallback = True
                logger.warning(f"Detected ResourceNotFoundError-like pattern in error type '{error_type}' or message. Error: {e}. Triggering fallback.")
            
            # Check for GroupChat related errors
            elif any(keyword.lower() in error_type.lower() for keyword in ["GroupChat", "Chat", "Agent", "AutoGen", "Message"]): # Broader check for AutoGen related errors
                should_use_fallback = True
                logger.warning(f"Detected AutoGen-related error pattern in error type '{error_type}'. Error: {e}. Triggering fallback.")
                
            # Check for serialization errors that might indicate GroupChat issues
            elif "serializ" in error_str.lower() or "unhandled message" in error_str.lower(): # case-insensitive
                should_use_fallback = True
                logger.warning(f"Detected serialization/message handling error pattern. Error: {e}. Triggering fallback.")
            
            if should_use_fallback:
                # logger.info("Using fallback mechanism due to detected error patterns") # Already logged with more details above
                return await self.fallback_single_agent_simulation(content)
            
            # Mark error state for any active agents
            for agent_name, metadata in self.agent_metadata.items():
                if metadata.status == AgentStatus.ACTIVE or metadata.status == AgentStatus.PROCESSING:
                    self._increment_agent_error(agent_name)
            
            error_msg = f"Error processing your request: {str(e)}"
            return {
                "final_response": error_msg,
                "conversation_history": [
                    {
                        "agent": "system",
                        "content": error_msg,
                        "timestamp": datetime.utcnow().isoformat(),
                        "message_id": f"msg_error_{datetime.utcnow().timestamp()}",
                        "sequence_number": 0,
                        "agent_role": "Error Handler",
                        "agent_description": "System error response",
                        "message_length": len(error_msg)
                    }
                ],
                "total_messages": 1,
                "session_metadata": {
                    "session_id": getattr(self, 'conversation_session_id', 'unknown'),
                    "session_start_time": getattr(self, 'session_start_time', datetime.utcnow()).isoformat(),
                    "session_duration_seconds": 0,
                    "participating_agents": [],
                    "agent_count": 0,
                    "error": str(e)
                },
                "agent_statuses": self.get_agent_statuses()
            }

    def get_agent_statuses(self) -> Dict[str, Dict[str, Any]]:
        """Get current status of all agents."""
        statuses = {}
        for agent_name, metadata in self.agent_metadata.items():
            statuses[agent_name] = {
                "name": metadata.name,
                "role": metadata.role,
                "description": metadata.description,
                "capabilities": metadata.capabilities,
                "status": metadata.status.value,
                "message_count": metadata.message_count,
                "last_activity": metadata.last_activity.isoformat() if metadata.last_activity else None,
                "error_count": metadata.error_count
            }
        return statuses

    def get_system_health(self) -> Dict[str, Any]:
        """Get overall system health status."""
        total_agents = len(self.agent_metadata)
        healthy_agents = sum(1 for m in self.agent_metadata.values() if m.status != AgentStatus.ERROR)
        error_agents = sum(1 for m in self.agent_metadata.values() if m.status == AgentStatus.ERROR)
        
        return {
            "system_status": "healthy" if error_agents == 0 else "degraded" if error_agents < total_agents else "error",
            "total_agents": total_agents,
            "healthy_agents": healthy_agents,
            "error_agents": error_agents,
            "uptime_seconds": (datetime.utcnow() - self.session_start_time).total_seconds() if self.session_start_time else 0,
            "session_active": self.conversation_session_id is not None
        }

    async def fetch_url(self, url: str) -> Dict[str, Any]:
        """Fetch content from a URL using McpWorkbench."""
        if not self.workbench:
            logger.error("McpWorkbench not initialized in fetch_url.")
            raise RuntimeError("System not started or workbench not initialized. Call start() first.")
        try:
            # Assuming the 'fetch' MCP server has a tool named 'fetch_url' or similar
            # The exact tool_name depends on the MCP server's definition.
            # For a generic fetch server, 'fetch' or 'get_url_content' might be tool names.
            # Let's assume a tool named 'fetch_html' for now, similar to zcaceres/fetch-mcp
            logger.debug(f"Using McpWorkbench to fetch URL: {url}")
            return await self.workbench.use_tool(server_name="fetch", tool_name="fetch_html", arguments={"url": url})
        except Exception as e:
            logger.error(f"Error using McpWorkbench for fetch_url {url}: {e}", exc_info=True)
            return {"error": str(e)}

    async def search_brave(self, query: str) -> Dict[str, Any]:
        """Search using Brave Search via McpWorkbench."""
        if not self.workbench:
            logger.error("McpWorkbench not initialized in search_brave.")
            raise RuntimeError("System not started or workbench not initialized. Call start() first.")
        try:
            # Assuming the 'brave' MCP server has a tool named 'search'
            logger.debug(f"Using McpWorkbench to search Brave: {query}")
            return await self.workbench.use_tool(server_name="brave", tool_name="search", arguments={"query": query})
        except Exception as e:
            logger.error(f"Error using McpWorkbench for search_brave with query '{query}': {e}", exc_info=True)
            return {"error": str(e)}

    async def github_operation(self, operation: str, **kwargs) -> Dict[str, Any]:
        """Perform GitHub operations via McpWorkbench."""
        if not self.workbench:
            logger.error("McpWorkbench not initialized in github_operation.")
            raise RuntimeError("System not started or workbench not initialized. Call start() first.")
        try:
            # The 'operation' itself is likely the tool_name for the 'github' MCP server
            logger.debug(f"Using McpWorkbench for GitHub operation: {operation} with args {kwargs}")
            return await self.workbench.use_tool(server_name="github", tool_name=operation, arguments=kwargs)
        except Exception as e:
            logger.error(f"Error using McpWorkbench for github_operation '{operation}': {e}", exc_info=True)
            return {"error": str(e)}
