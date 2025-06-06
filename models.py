"""Pydantic models for request/response validation."""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


class AgentType(str, Enum):
    """Available agent types in the multi-agent system."""
    FETCHER = "fetcher"
    SUMMARIZER = "summarizer"
    ANALYZER = "analyzer"
    COORDINATOR = "coordinator"
    RESPONDER = "responder"


class QueryRequest(BaseModel):
    """Request model for Azure OpenAI completion."""
    prompt: str = Field(..., description="The prompt to send to Azure OpenAI")
    max_tokens: Optional[int] = Field(default=100, description="Maximum tokens to generate")
    temperature: Optional[float] = Field(default=0.7, description="Temperature for generation")


class ChatRequest(BaseModel):
    """Request model for chat with multi-agent system."""
    message: str = Field(..., description="The message to send to the agents")
    agent_type: Optional[AgentType] = Field(default=AgentType.COORDINATOR, description="Target agent type")
    context: Optional[Dict[str, Any]] = Field(default=None, description="Additional context for the conversation")


class MultiAgentRequest(BaseModel):
    """Request model for multi-agent system communication."""
    content: str = Field(..., description="Content of the message")
    recipient_agent_type: AgentType = Field(..., description="Type of agent to receive the message")
    sender: Optional[str] = Field(default="user", description="Sender of the message")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional metadata")


class HealthResponse(BaseModel):
    """Response model for health check."""
    status: str = Field(..., description="Health status")
    app_name: str = Field(..., description="Application name")
    version: str = Field(..., description="Application version")
    environment: str = Field(..., description="Current environment")


class AgentStatusResponse(BaseModel):
    """Response model for agent status."""
    status: str = Field(..., description="System status")
    agents: List[str] = Field(..., description="List of available agents")


class APIResponse(BaseModel):
    """Generic API response model."""
    success: bool = Field(default=True, description="Success status")
    message: Optional[str] = Field(default=None, description="Response message")
    data: Optional[Dict[str, Any]] = Field(default=None, description="Response data")
    error: Optional[str] = Field(default=None, description="Error message if any")


class MCPServerStatus(BaseModel):
    """MCP server status model."""
    name: str = Field(..., description="Server name")
    url: str = Field(..., description="Server URL")
    status: str = Field(..., description="Server status")
    last_check: Optional[str] = Field(default=None, description="Last health check timestamp")


class GitHubRepoInfo(BaseModel):
    """GitHub repository information model."""
    name: str = Field(..., description="Repository name")
    full_name: str = Field(..., description="Full repository name")
    description: Optional[str] = Field(default=None, description="Repository description")
    html_url: str = Field(..., description="Repository HTML URL")
    clone_url: str = Field(..., description="Repository clone URL")
    language: Optional[str] = Field(default=None, description="Primary language")
    stars: int = Field(default=0, description="Number of stars")
    forks: int = Field(default=0, description="Number of forks")


class SearchResult(BaseModel):
    """Search result model for Brave Search."""
    title: str = Field(..., description="Result title")
    url: str = Field(..., description="Result URL")
    description: Optional[str] = Field(default=None, description="Result description")
    snippet: Optional[str] = Field(default=None, description="Result snippet")


class BraveSearchResponse(BaseModel):
    """Brave Search API response model."""
    query: str = Field(..., description="Search query")
    results: List[SearchResult] = Field(..., description="Search results")
    total_results: Optional[int] = Field(default=None, description="Total number of results")


class SQLiteQueryRequest(BaseModel):
    """SQLite query request model."""
    sql: str = Field(..., description="SQL query to execute")
    params: Optional[List[Any]] = Field(default=None, description="Query parameters")


class SQLiteQueryResponse(BaseModel):
    """SQLite query response model."""
    columns: List[str] = Field(..., description="Column names")
    rows: List[List[Any]] = Field(..., description="Query result rows")
    row_count: int = Field(..., description="Number of rows returned")
    execution_time: Optional[float] = Field(default=None, description="Query execution time in seconds")


class AgentMessage(BaseModel):
    """Agent message model."""
    content: str = Field(..., description="Message content")
    sender: str = Field(..., description="Sender agent name")
    recipient: Optional[str] = Field(default=None, description="Recipient agent name")
    timestamp: Optional[str] = Field(default=None, description="Message timestamp")
    message_type: Optional[str] = Field(default="text", description="Type of message")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional metadata")


class ConversationHistory(BaseModel):
    """Conversation history model."""
    messages: List[AgentMessage] = Field(..., description="List of messages in conversation")
    conversation_id: str = Field(..., description="Unique conversation identifier")
    created_at: Optional[str] = Field(default=None, description="Conversation creation timestamp")
    updated_at: Optional[str] = Field(default=None, description="Last update timestamp")
