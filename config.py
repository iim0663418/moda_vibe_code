"""Configuration management for Moda Vibe Code application."""

import os
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field, validator
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Environment(str, Enum):
    """Application environment types."""
    DEVELOPMENT = "development"
    PRODUCTION = "production"
    TESTING = "testing"


class LogLevel(str, Enum):
    """Logging level options."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class AzureOpenAIConfig(BaseModel):
    """Azure OpenAI configuration."""
    api_key: str = Field(..., description="Azure OpenAI API key")
    endpoint: str = Field(..., description="Azure OpenAI endpoint URL")
    deployment_name: str = Field(..., description="Azure OpenAI deployment name")
    api_version: str = Field(default="2025-01-01-preview", description="API version")
    
    @validator('endpoint')
    def validate_endpoint(cls, v):
        if not v.startswith('https://'):
            raise ValueError('Endpoint must start with https://')
        return v.rstrip('/')


class MCPServerConfig(BaseModel):
    """MCP Server configuration."""
    fetch_url: Optional[str] = Field(default=None, description="URL for the fetch MCP server") # Added fetch_url
    github_url: str = Field(default="http://mcp-github:3000")
    brave_search_url: str = Field(default="http://mcp-brave-search:3000")
    sqlite_url: str = Field(default="http://mcp-sqlite:3000")
    timeout: int = Field(default=30, description="Request timeout in seconds")


class Settings(BaseModel):
    """Application settings."""
    
    # Application settings
    app_name: str = Field(default="Moda Vibe Code")
    app_version: str = Field(default="1.1.0")
    environment: Environment = Field(default=Environment.DEVELOPMENT)
    debug: bool = Field(default=False)
    log_level: LogLevel = Field(default=LogLevel.INFO)
    
    # Server settings
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    reload: bool = Field(default=False)
    
    # Azure OpenAI settings
    azure_openai_api_key: str = Field(..., description="Azure OpenAI API key")
    azure_openai_endpoint: str = Field(..., description="Azure OpenAI endpoint")
    azure_openai_deployment_name: str = Field(..., description="Azure OpenAI deployment name")
    azure_openai_model: str = Field(default="gpt-4o-mini", description="Azure OpenAI model name")
    azure_openai_api_version: str = Field(default="2025-01-01-preview")
    
    # External API settings
    github_personal_access_token: Optional[str] = Field(default=None, description="GitHub Personal Access Token")
    brave_api_key: Optional[str] = Field(default=None, description="Brave Search API key")
    
    # Security settings
    api_key: Optional[str] = Field(default=None, description="API key for authentication")
    enable_rate_limiting: bool = Field(default=True, description="Enable rate limiting")
    cors_origins: str = Field(default="http://localhost:3000,http://localhost:8000")
    max_request_size: int = Field(default=10 * 1024 * 1024, description="Maximum request size in bytes")
    
    # MCP Server settings
    mcp_fetch_url: Optional[str] = Field(default=None, description="URL for the fetch MCP server, e.g., http://mcp-fetch:3000") # Added
    mcp_github_url: str = Field(default="http://mcp-github:3000")
    mcp_brave_search_url: str = Field(default="http://mcp-brave-search:3000")
    mcp_sqlite_url: str = Field(default="http://mcp-sqlite:3000")
    mcp_timeout: int = Field(default=30)
    
    # Agent settings
    max_agent_iterations: int = Field(default=10)
    agent_timeout: int = Field(default=60)

    @classmethod
    def from_env(cls) -> "Settings":
        """Create settings instance from environment variables."""
        
        def get_env(key: str, default=None, cast_type=str):
            """Get environment variable with type casting."""
            value = os.getenv(key, default)
            if value is None:
                return default
            if cast_type == bool:
                if isinstance(value, bool):
                    return value
                return str(value).lower() in ('true', '1', 'yes', 'on')
            elif cast_type == int:
                try:
                    return int(value)
                except (ValueError, TypeError):
                    return default
            return cast_type(value) if value else default
        
        # Get required Azure OpenAI settings
        azure_openai_api_key = os.getenv("AZURE_OPENAI_API_KEY")
        azure_openai_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        azure_openai_deployment_name = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
        
        # For testing purposes, provide defaults if env vars are missing
        if not azure_openai_api_key:
            azure_openai_api_key = "test-key"
        if not azure_openai_endpoint:
            azure_openai_endpoint = "https://test.openai.azure.com"
        if not azure_openai_deployment_name:
            azure_openai_deployment_name = "test-deployment"
        
        return cls(
            # Application settings
            app_name=get_env("APP_NAME", "Moda Vibe Code"),
            app_version=get_env("APP_VERSION", "1.1.0"),
            environment=Environment(get_env("ENVIRONMENT", "development").lower()),
            debug=get_env("DEBUG", False, bool),
            log_level=LogLevel(get_env("LOG_LEVEL", "INFO").upper()),
            
            # Server settings
            host=get_env("HOST", "0.0.0.0"),
            port=get_env("PORT", 8000, int),
            reload=get_env("RELOAD", False, bool),
            
            # Azure OpenAI settings
            azure_openai_api_key=azure_openai_api_key,
            azure_openai_endpoint=azure_openai_endpoint,
            azure_openai_deployment_name=azure_openai_deployment_name,
            azure_openai_model=get_env("AZURE_OPENAI_MODEL", "gpt-4o-mini"),
            azure_openai_api_version=get_env("AZURE_OPENAI_API_VERSION", "2025-01-01-preview"),
            
            # External API settings
            github_personal_access_token=get_env("GITHUB_PERSONAL_ACCESS_TOKEN"),
            brave_api_key=get_env("BRAVE_API_KEY"),
            
            # Security settings
            api_key=get_env("API_KEY"),
            enable_rate_limiting=get_env("ENABLE_RATE_LIMITING", True, bool),
            cors_origins=get_env("CORS_ORIGINS", "http://localhost:3000,http://localhost:8000"),
            max_request_size=get_env("MAX_REQUEST_SIZE", 10 * 1024 * 1024, int),
            
            # MCP Server settings
            mcp_fetch_url=get_env("MCP_FETCH_URL"), # Added
            mcp_github_url=get_env("MCP_GITHUB_URL", "http://mcp-github:3000"),
            mcp_brave_search_url=get_env("MCP_BRAVE_SEARCH_URL", "http://mcp-brave-search:3000"),
            mcp_sqlite_url=get_env("MCP_SQLITE_URL", "http://mcp-sqlite:3000"),
            mcp_timeout=get_env("MCP_TIMEOUT", 30, int),
            
            # Agent settings
            max_agent_iterations=get_env("MAX_AGENT_ITERATIONS", 10, int),
            agent_timeout=get_env("AGENT_TIMEOUT", 60, int),
        )
    
    @property
    def azure_openai_config(self) -> AzureOpenAIConfig:
        """Get Azure OpenAI configuration."""
        return AzureOpenAIConfig(
            api_key=self.azure_openai_api_key,
            endpoint=self.azure_openai_endpoint,
            deployment_name=self.azure_openai_deployment_name,
            api_version=self.azure_openai_api_version
        )
    
    @property
    def mcp_config(self) -> MCPServerConfig:
        """Get MCP server configuration."""
        return MCPServerConfig(
            fetch_url=self.mcp_fetch_url, # Added
            github_url=self.mcp_github_url,
            brave_search_url=self.mcp_brave_search_url,
            sqlite_url=self.mcp_sqlite_url,
            timeout=self.mcp_timeout
        )
    
    @property
    def cors_origins_list(self) -> List[str]:
        """Get CORS origins as a list."""
        return [origin.strip() for origin in self.cors_origins.split(',') if origin.strip()]
    
    @validator('environment', pre=True)
    def validate_environment(cls, v):
        if isinstance(v, str):
            return Environment(v.lower())
        return v
    
    @validator('log_level', pre=True)
    def validate_log_level(cls, v):
        if isinstance(v, str):
            return LogLevel(v.upper())
        return v
    
    @validator('debug', pre=True)
    def validate_debug(cls, v, values):
        if values.get('environment') == Environment.DEVELOPMENT:
            return True
        return v


# Global settings instance
_settings = None


def get_settings() -> Settings:
    """Get application settings."""
    global _settings
    if _settings is None:
        _settings = Settings.from_env()
    return _settings


# Create global settings instance
settings = get_settings()
