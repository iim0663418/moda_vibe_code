"""MCP Server management and monitoring."""

import asyncio
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass
import httpx

from config import get_settings
from models import MCPServerStatus

settings = get_settings()
logger = logging.getLogger(__name__)


@dataclass
class MCPServerInfo:
    """MCP Server information."""
    name: str
    url: str
    health_endpoint: str
    retry_count: int = 0
    max_retries: int = 3
    last_check: Optional[datetime] = None
    status: str = "unknown"
    error_message: Optional[str] = None


class MCPServerManager:
    """Manage MCP servers health and connectivity."""
    
    def __init__(self):
        self.servers: Dict[str, MCPServerInfo] = {
            "github": MCPServerInfo(
                name="GitHub MCP",
                url=settings.mcp_github_url.replace(':3000', ':8080'),  # Health check on port 8080
                health_endpoint="/"
            ),
            "brave_search": MCPServerInfo(
                name="Brave Search MCP",
                url=settings.mcp_brave_search_url.replace(':3000', ':8080'),  # Health check on port 8080
                health_endpoint="/"
            ),
            "sqlite": MCPServerInfo(
                name="SQLite MCP",
                url=settings.mcp_sqlite_url,  # SQLite has health endpoint on main port
                health_endpoint="/health"
            )
        }
        self.check_interval = 30  # seconds
        self.timeout = 10  # seconds
        self._monitoring_task: Optional[asyncio.Task] = None
        
    async def start_monitoring(self):
        """Start health monitoring for all MCP servers."""
        logger.info("Starting MCP server health monitoring...")
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())
        
        # Initial health check
        await self.check_all_servers()
    
    async def stop_monitoring(self):
        """Stop health monitoring."""
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                logger.info("MCP server monitoring stopped")
    
    async def _monitoring_loop(self):
        """Main monitoring loop."""
        while True:
            try:
                await asyncio.sleep(self.check_interval)
                await self.check_all_servers()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in MCP monitoring loop: {e}")
    
    async def check_all_servers(self):
        """Check health of all MCP servers."""
        tasks = [self.check_server_health(server_id) for server_id in self.servers.keys()]
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def check_server_health(self, server_id: str) -> bool:
        """Check health of a specific MCP server."""
        if server_id not in self.servers:
            logger.warning(f"Unknown server ID: {server_id}")
            return False
        
        server = self.servers[server_id]
        health_url = f"{server.url.rstrip('/')}{server.health_endpoint}"
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(health_url)
                
                if response.status_code == 200:
                    server.status = "healthy"
                    server.retry_count = 0
                    server.error_message = None
                    logger.debug(f"MCP server {server.name} is healthy")
                    return True
                else:
                    server.status = "unhealthy"
                    server.error_message = f"HTTP {response.status_code}"
                    logger.warning(f"MCP server {server.name} returned HTTP {response.status_code}")
                    return False
                    
        except httpx.TimeoutException:
            server.status = "timeout"
            server.error_message = "Request timeout"
            logger.warning(f"MCP server {server.name} health check timed out")
            return False
            
        except httpx.ConnectError:
            server.status = "unreachable"
            server.error_message = "Connection refused"
            logger.warning(f"MCP server {server.name} is unreachable")
            return False
            
        except Exception as e:
            server.status = "error"
            server.error_message = str(e)
            logger.error(f"Error checking MCP server {server.name}: {e}")
            return False
        
        finally:
            server.last_check = datetime.utcnow()
    
    async def get_server_status(self, server_id: str) -> Optional[MCPServerStatus]:
        """Get status of a specific server."""
        if server_id not in self.servers:
            return None
        
        server = self.servers[server_id]
        return MCPServerStatus(
            name=server.name,
            url=server.url,
            status=server.status,
            last_check=server.last_check.isoformat() if server.last_check else None
        )
    
    async def get_all_server_status(self) -> List[MCPServerStatus]:
        """Get status of all servers."""
        statuses = []
        for server_id in self.servers.keys():
            status = await self.get_server_status(server_id)
            if status:
                statuses.append(status)
        return statuses
    
    async def is_server_healthy(self, server_id: str) -> bool:
        """Check if a server is currently healthy."""
        if server_id not in self.servers:
            return False
        
        server = self.servers[server_id]
        
        # If never checked or last check was too long ago, do a fresh check
        if (not server.last_check or 
            datetime.utcnow() - server.last_check > timedelta(minutes=5)):
            await self.check_server_health(server_id)
        
        return server.status == "healthy"
    
    async def wait_for_server(self, server_id: str, max_wait_time: int = 60) -> bool:
        """Wait for a server to become healthy."""
        if server_id not in self.servers:
            return False
        
        server = self.servers[server_id]
        start_time = datetime.utcnow()
        
        while (datetime.utcnow() - start_time).total_seconds() < max_wait_time:
            if await self.check_server_health(server_id):
                logger.info(f"MCP server {server.name} is now healthy")
                return True
            
            await asyncio.sleep(2)  # Wait 2 seconds before retrying
        
        logger.error(f"MCP server {server.name} did not become healthy within {max_wait_time} seconds")
        return False
    
    async def restart_server(self, server_id: str) -> bool:
        """Attempt to restart a server (placeholder - would require Docker API)."""
        # This is a placeholder. In a real implementation, you would use Docker API
        # to restart the container
        logger.warning(f"Server restart not implemented for {server_id}")
        return False


# Global MCP manager instance
mcp_manager = MCPServerManager()


async def get_mcp_manager() -> MCPServerManager:
    """Get the global MCP manager instance."""
    return mcp_manager


async def ensure_mcp_server_healthy(server_id: str) -> bool:
    """Ensure an MCP server is healthy before making requests."""
    manager = await get_mcp_manager()
    return await manager.is_server_healthy(server_id)


async def make_mcp_request(server_id: str, endpoint: str, method: str = "GET", **kwargs):
    """Make a request to an MCP server with health checking and retries."""
    manager = await get_mcp_manager()
    
    # Check if server is healthy
    if not await manager.is_server_healthy(server_id):
        # Wait for server to become healthy
        if not await manager.wait_for_server(server_id, max_wait_time=30):
            raise httpx.HTTPError(f"MCP server {server_id} is not available")
    
    # Use the original service URL for actual requests (not health check URL)
    service_urls = {
        "github": settings.mcp_github_url,
        "brave_search": settings.mcp_brave_search_url,
        "sqlite": settings.mcp_sqlite_url
    }
    
    if server_id not in service_urls:
        raise ValueError(f"Unknown MCP server: {server_id}")
    
    url = f"{service_urls[server_id].rstrip('/')}/{endpoint.lstrip('/')}"
    
    async with httpx.AsyncClient(timeout=settings.mcp_timeout) as client:
        if method.upper() == "GET":
            response = await client.get(url, **kwargs)
        elif method.upper() == "POST":
            response = await client.post(url, **kwargs)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")
        
        response.raise_for_status()
        return response.json()
