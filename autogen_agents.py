import logging
import httpx
import tiktoken
from typing import Dict, List, Any, Optional
from datetime import datetime
from enum import Enum
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.conditions import ExternalTermination, TextMentionTermination
from autogen_ext.models.azure import AzureAIChatCompletionClient
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


class HTTPToolWorkbench:
    """Custom workbench to replace MCP workbench with direct HTTP calls."""
    
    def __init__(self, mcp_urls: Dict[str, str], timeout: int = 30):
        self.mcp_urls = mcp_urls
        self.timeout = timeout
        self.client = None
    
    async def __aenter__(self):
        self.client = httpx.AsyncClient(timeout=self.timeout)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()
    
    async def fetch_url(self, url: str) -> Dict[str, Any]:
        """Fetch content from a URL using the fetch MCP server."""
        if not self.client:
            raise RuntimeError("Workbench not initialized. Use 'async with' context manager.")
        
        try:
            # Call MCP fetch service directly via HTTP
            # 這裡假設 MCP 服務提供了 REST API 端點
            response = await self.client.post(
                f"{self.mcp_urls.get('fetch', 'http://localhost:3000')}/fetch",
                json={"url": url}
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching URL {url}: {e}")
            return {"error": str(e)}
    
    async def search_brave(self, query: str) -> Dict[str, Any]:
        """Search using Brave Search via MCP server."""
        if not self.client:
            raise RuntimeError("Workbench not initialized. Use 'async with' context manager.")
        
        try:
            response = await self.client.post(
                f"{self.mcp_urls.get('brave', 'http://localhost:3001')}/search",
                json={"query": query}
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error searching with Brave: {e}")
            return {"error": str(e)}
    
    async def github_operation(self, operation: str, **kwargs) -> Dict[str, Any]:
        """Perform GitHub operations via MCP server."""
        if not self.client:
            raise RuntimeError("Workbench not initialized. Use 'async with' context manager.")
        
        try:
            response = await self.client.post(
                f"{self.mcp_urls.get('github', 'http://localhost:3002')}/{operation}",
                json=kwargs
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error performing GitHub operation {operation}: {e}")
            return {"error": str(e)}


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
        self.workbench = None
        
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
        # Initialize custom workbench
        if self.workbench is None:
            self.workbench = HTTPToolWorkbench(
                mcp_urls={
                    'fetch': self.mcp_config.get('fetch_url', 'http://localhost:3000'),
                    'brave': self.mcp_config.get('brave_search_url', 'http://localhost:3001'),
                    'github': self.mcp_config.get('github_url', 'http://localhost:3002'),
                },
                timeout=self.mcp_config.get('timeout', 30)
            )
            await self.workbench.__aenter__()

        # Create specialized agents with specific system messages
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
        
        self.coordinator_agent = AssistantAgent(
            name="coordinator",
            model_client=self.model_client,
            system_message="""You are a coordination agent. Your role is to:
1. Coordinate tasks between different agents
2. Manage workflow and task distribution
3. Ensure all agents work towards common goals
4. Resolve conflicts and prioritize tasks
Focus on efficient task management and clear communication.""",
            reflect_on_tool_use=True,
        )
        
        self.responder_agent = AssistantAgent(
            name="responder",
            model_client=self.model_client,
            system_message="""You are a response generation agent. Your role is to:
1. Synthesize information from all agents
2. Generate final responses to user queries
3. Ensure responses are coherent and complete
4. Format responses appropriately for the context
Create clear, comprehensive, and user-friendly responses.""",
            reflect_on_tool_use=True,
        )

        # Setup group chat with agents using RoundRobinGroupChat
        # Define termination condition
        text_termination = TextMentionTermination("TASK_COMPLETE")
        
        self.group_chat = RoundRobinGroupChat(
            participants=[
                self.fetcher_agent,
                self.summarizer_agent,
                self.analyzer_agent,
                self.coordinator_agent,
                self.responder_agent,
            ],
            termination_condition=text_termination,
        )

    async def stop(self):
        """Stop the multi-agent system and clean up resources."""
        try:
            await self.model_client.close()
        except Exception as e:
            logger.error(f"Error closing model client: {e}")
        
        if self.workbench is not None:
            try:
                await self.workbench.__aexit__(None, None, None)
            except Exception as e:
                logger.error(f"Error closing workbench: {e}")

    async def send_message(self, content: str, recipient_agent_type: str = "coordinator") -> Dict[str, Any]:
        """Send a message to the multi-agent system and get a response with enhanced conversation history."""
        if self.group_chat is None:
            raise RuntimeError("Multi-agent system not started. Call start() before sending messages.")

        # Initialize session tracking
        if not self.session_start_time:
            self.session_start_time = datetime.utcnow()
            import uuid
            self.conversation_session_id = str(uuid.uuid4())

        # Reset agent statuses at start of conversation
        for agent_name in self.agent_metadata:
            self._update_agent_status(agent_name, AgentStatus.IDLE)

        try:
            from autogen_core import CancellationToken
            
            # Mark conversation as starting
            self._update_agent_status(recipient_agent_type, AgentStatus.ACTIVE)
            
            # Run the team with the user message with specific error handling
            try:
                result = await self.group_chat.run(
                    task=content,
                    cancellation_token=CancellationToken()
                )
            except ResourceNotFoundError as e:
                logger.error(f"Azure OpenAI Resource Not Found Error: {e}")
                logger.info("Attempting fallback to single agent simulation")
                # Use fallback single agent simulation instead of returning error
                return await self.fallback_single_agent_simulation(content)
            except Exception as group_chat_error:
                # Check if it's a GroupChatError or similar autogen error
                error_class_name = type(group_chat_error).__name__
                if "GroupChat" in error_class_name or "Chat" in error_class_name:
                    logger.error(f"GroupChat Error: {group_chat_error}")
                    logger.info("Attempting fallback to single agent simulation")
                    # Use fallback single agent simulation instead of returning error
                    return await self.fallback_single_agent_simulation(content)
                else:
                    # Re-raise other exceptions to be handled by outer try/except
                    raise
            
            # Extract conversation history and final response with enhanced metadata
            conversation_history = []
            final_response = ""
            participating_agents = set()
            
            if hasattr(result, 'messages') and result.messages:
                # Process all messages in the conversation
                for i, message in enumerate(result.messages):
                    if hasattr(message, 'source') and hasattr(message, 'content'):
                        agent_name = getattr(message.source, 'name', 'unknown')
                        participating_agents.add(agent_name)
                        
                        # Update agent status and tracking
                        self._update_agent_status(agent_name, AgentStatus.PROCESSING, increment_message=True)
                        
                        # Create enhanced message with metadata
                        enhanced_message = {
                            "agent": agent_name,
                            "content": str(message.content),
                            "timestamp": datetime.utcnow().isoformat(),
                            "message_id": f"msg_{self.conversation_session_id}_{i}",
                            "sequence_number": i,
                            "agent_role": self.agent_metadata.get(agent_name, {}).role if agent_name in self.agent_metadata else "Unknown",
                            "agent_description": self.agent_metadata.get(agent_name, {}).description if agent_name in self.agent_metadata else "",
                            "message_length": len(str(message.content))
                        }
                        conversation_history.append(enhanced_message)
                
                # Mark participating agents as completed
                for agent_name in participating_agents:
                    self._update_agent_status(agent_name, AgentStatus.COMPLETED)
                
                # Get the last message as final response
                last_message = result.messages[-1]
                if hasattr(last_message, 'content'):
                    final_response = str(last_message.content)
                else:
                    final_response = str(last_message)
            elif hasattr(result, 'content'):
                final_response = str(result.content)
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
            else:
                final_response = str(result)
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
            logger.error(f"Error processing message: {e}")
            
            # Check if this error should trigger fallback
            should_use_fallback = False
            error_str = str(e)
            error_type = type(e).__name__
            
            # Check for ResourceNotFoundError in exception chain or error message
            if "ResourceNotFound" in error_type or "404" in error_str or "Resource not found" in error_str:
                should_use_fallback = True
                logger.info("Detected ResourceNotFoundError in exception chain, attempting fallback")
            
            # Check for GroupChat related errors
            elif any(keyword in error_type for keyword in ["GroupChat", "Chat", "Agent"]):
                should_use_fallback = True
                logger.info("Detected GroupChat/Agent error, attempting fallback")
                
            # Check for serialization errors that might indicate GroupChat issues
            elif "serializ" in error_str.lower() or "Unhandled message" in error_str:
                should_use_fallback = True
                logger.info("Detected serialization/message handling error, attempting fallback")
            
            if should_use_fallback:
                logger.info("Using fallback mechanism due to detected error patterns")
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
        """Fetch content from a URL using the workbench."""
        if not self.workbench:
            raise RuntimeError("System not started. Call start() first.")
        return await self.workbench.fetch_url(url)

    async def search_brave(self, query: str) -> Dict[str, Any]:
        """Search using Brave Search."""
        if not self.workbench:
            raise RuntimeError("System not started. Call start() first.")
        return await self.workbench.search_brave(query)

    async def github_operation(self, operation: str, **kwargs) -> Dict[str, Any]:
        """Perform GitHub operations."""
        if not self.workbench:
            raise RuntimeError("System not started. Call start() first.")
        return await self.workbench.github_operation(operation, **kwargs)
