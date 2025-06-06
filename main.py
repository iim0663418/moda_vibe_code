import os
import asyncio
import logging
from enum import Enum
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel
import httpx
from dotenv import load_dotenv

from config import get_settings
from logging_config import setup_logging
from autogen_agents import VibeCodeMultiAgentSystem
from models import QueryRequest, MultiAgentRequest, ChatRequest
from security import (
    rate_limit, api_rate_limiter, chat_rate_limiter, 
    validate_api_key, sanitize_input, SecurityHeaders
)
from mcp_manager import mcp_manager, make_mcp_request
from teams_api import router as teams_router, initialize_teams_manager, shutdown_teams_manager
from workflow_state_machine import get_workflow_state_machine, TaskPriority

# Load environment variables
load_dotenv()

# Initialize settings and logging
settings = get_settings()
setup_logging(settings.log_level.value)
logger = logging.getLogger(__name__)

# Global multi-agent system instance
multi_agent_system = None

# Global workflow state machine instance
workflow_sm = get_workflow_state_machine()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager."""
    global multi_agent_system
    
    # Startup
    logger.info("Starting Moda Vibe Code application...")
    
    # Start services independently without blocking each other
    startup_tasks = []
    
    # Start MCP server monitoring (non-blocking)
    async def start_mcp_monitoring():
        try:
            await mcp_manager.start_monitoring()
            logger.info("MCP server monitoring started")
        except Exception as e:
            logger.error(f"Failed to start MCP monitoring: {e}")
            logger.info("Application will continue without MCP monitoring")
    
    startup_tasks.append(asyncio.create_task(start_mcp_monitoring()))
    
    # Start multi-agent system (independent of MCP)
    async def start_multi_agent_system():
        try:
            mcp_config_data = {
                'brave_search_url': settings.mcp_config.brave_search_url,
                'github_url': settings.mcp_config.github_url,
                'timeout': settings.mcp_config.timeout
            }
            if settings.mcp_config.fetch_url: # Only add fetch_url if it's configured
                mcp_config_data['fetch_url'] = settings.mcp_config.fetch_url
            
            global multi_agent_system
            multi_agent_system = VibeCodeMultiAgentSystem(
                azure_openai_api_key=settings.azure_openai_api_key,
                azure_openai_endpoint=settings.azure_openai_endpoint,
                azure_openai_deployment_name=settings.azure_openai_deployment_name,
                azure_openai_api_version=settings.azure_openai_api_version,
                mcp_config=mcp_config_data
            )
            await multi_agent_system.start()
            logger.info("Multi-agent system started successfully")
        except Exception as e:
            logger.error(f"Failed to start multi-agent system: {e}")
            logger.info("Application will continue with limited functionality")
    
    startup_tasks.append(asyncio.create_task(start_multi_agent_system()))
    
    # Start teams manager (independent)
    async def start_teams_manager():
        try:
            await initialize_teams_manager()
            logger.info("Teams manager started successfully")
        except Exception as e:
            logger.error(f"Failed to start teams manager: {e}")
            logger.info("Application will continue without teams functionality")
    
    startup_tasks.append(asyncio.create_task(start_teams_manager()))
    
    # Wait for all startup tasks to complete (with timeout)
    try:
        await asyncio.wait_for(
            asyncio.gather(*startup_tasks, return_exceptions=True),
            timeout=60.0  # 60 second timeout for startup
        )
        logger.info("Application startup completed")
    except asyncio.TimeoutError:
        logger.warning("Startup tasks timed out, but application will continue")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Moda Vibe Code application...")
    
    # Shutdown tasks
    shutdown_tasks = []
    
    if multi_agent_system:
        async def stop_multi_agent():
            try:
                await multi_agent_system.stop()
                logger.info("Multi-agent system stopped successfully")
            except Exception as e:
                logger.error(f"Error stopping multi-agent system: {e}")
        shutdown_tasks.append(asyncio.create_task(stop_multi_agent()))
    
    async def stop_mcp_monitoring():
        try:
            await mcp_manager.stop_monitoring()
            logger.info("MCP server monitoring stopped")
        except Exception as e:
            logger.error(f"Error stopping MCP monitoring: {e}")
    
    shutdown_tasks.append(asyncio.create_task(stop_mcp_monitoring()))
    
    # Stop teams manager
    async def stop_teams_manager():
        try:
            await shutdown_teams_manager()
            logger.info("Teams manager stopped successfully")
        except Exception as e:
            logger.error(f"Error stopping teams manager: {e}")
    
    shutdown_tasks.append(asyncio.create_task(stop_teams_manager()))
    
    # Wait for shutdown tasks
    try:
        await asyncio.wait_for(
            asyncio.gather(*shutdown_tasks, return_exceptions=True),
            timeout=30.0
        )
    except asyncio.TimeoutError:
        logger.warning("Shutdown tasks timed out")

# Initialize FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="A sophisticated multi-agent system with Azure OpenAI and MCP integration",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(teams_router)

# Mount static files
app.mount("/static", StaticFiles(directory="app"), name="static")

@app.get("/")
async def root():
    """Serve the frontend HTML interface."""
    try:
        return FileResponse("app/frontend.html")
    except FileNotFoundError:
        logger.error("frontend.html not found at app/frontend.html")
        raise HTTPException(status_code=404, detail="Frontend not found")

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "app_name": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment.value
    }

@app.post("/azure-openai")
async def azure_openai_completion(request: QueryRequest):
    """Direct Azure OpenAI chat completion endpoint."""
    try:
        from openai import AsyncAzureOpenAI
        
        client = AsyncAzureOpenAI(
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
            azure_endpoint=settings.azure_openai_endpoint
        )
        
        # Convert prompt to chat messages format
        messages = [
            {"role": "user", "content": request.prompt}
        ]
        
        response = await client.chat.completions.create(
            model=settings.azure_openai_deployment_name,
            messages=messages,
            max_tokens=100,
            temperature=0.7
        )
        
        await client.close()
        return {"response": response.choices[0].message.content.strip()}
        
    except Exception as e:
        logger.error(f"Azure OpenAI chat completion error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Legacy endpoints for backward compatibility (consider deprecating)
@app.post("/legacy/chat")
async def chat_endpoint_legacy(request: ChatRequest):
    """Legacy chat endpoint - consider using /chat with authentication."""
    if not multi_agent_system:
        raise HTTPException(status_code=503, detail="Multi-agent system not available")
    
    try:
        result = await multi_agent_system.send_message(
            request.message, 
            request.agent_type or "coordinator"
        )
        return {"response": result.get("final_response", "")}
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/multi-agent/send")
async def send_multi_agent_message(request: MultiAgentRequest):
    """Send message to multi-agent system with enhanced conversation history and metadata."""
    if not multi_agent_system:
        raise HTTPException(status_code=503, detail="Multi-agent system not available")
    
    try:
        result = await multi_agent_system.send_message(
            request.content, 
            request.recipient_agent_type
        )
        return {
            "status": "message sent", 
            "final_response": result.get("final_response", ""),
            "conversation_history": result.get("conversation_history", []),
            "total_messages": result.get("total_messages", 0),
            "session_metadata": result.get("session_metadata", {}),
            "agent_statuses": result.get("agent_statuses", {})
        }
    except Exception as e:
        logger.error(f"Multi-agent send error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/multi-agent/status")
async def get_multi_agent_status():
    """Get enhanced multi-agent system status with detailed agent information."""
    if not multi_agent_system:
        return {"status": "unavailable", "agents": []}
    
    try:
        agent_statuses = multi_agent_system.get_agent_statuses()
        system_health = multi_agent_system.get_system_health()
        
        return {
            "status": "running",
            "system_health": system_health,
            "agent_statuses": agent_statuses,
            "agents": list(agent_statuses.keys())
        }
    except Exception as e:
        logger.error(f"Error getting multi-agent status: {e}")
        return {
            "status": "error",
            "error": str(e),
            "agents": []
        }

@app.get("/multi-agent/health")
async def get_multi_agent_health():
    """Get multi-agent system health status."""
    if not multi_agent_system:
        raise HTTPException(status_code=503, detail="Multi-agent system not available")
    
    try:
        health_status = multi_agent_system.get_system_health()
        return health_status
    except Exception as e:
        logger.error(f"Error getting system health: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/multi-agent/agents")
async def get_agent_details():
    """Get detailed information about all agents."""
    if not multi_agent_system:
        raise HTTPException(status_code=503, detail="Multi-agent system not available")
    
    try:
        agent_statuses = multi_agent_system.get_agent_statuses()
        return {"agents": agent_statuses}
    except Exception as e:
        logger.error(f"Error getting agent details: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Workflow State Machine API Endpoints
@app.post("/workflow/create")
async def create_workflow_task(request: dict):
    """Create a new workflow task."""
    try:
        task_id = request.get("task_id")
        workflow_name = request.get("workflow_name", "default")
        user_input = request.get("user_input", "")
        priority = request.get("priority", "normal")
        
        if not task_id:
            task_id = f"task_{int(asyncio.get_event_loop().time() * 1000)}"
        
        priority_enum = TaskPriority(priority) if priority in [p.value for p in TaskPriority] else TaskPriority.NORMAL
        
        task = workflow_sm.create_task(
            task_id=task_id,
            workflow_name=workflow_name,
            user_input=user_input,
            priority=priority_enum,
            **request.get("metadata", {})
        )
        
        return {
            "task_id": task.task_id,
            "status": "created",
            "workflow_name": task.workflow_name,
            "state": task.state,
            "priority": task.priority,
            "created_at": task.created_at.isoformat()
        }
    except Exception as e:
        logger.error(f"Error creating workflow task: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/workflow/{task_id}/start")
async def start_workflow_task(task_id: str):
    """Start a workflow task."""
    try:
        success = workflow_sm.start_task(task_id)
        if not success:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        
        task = workflow_sm.get_task(task_id)
        if not task: # Should be caught by success check, but as a safeguard
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found after state transition attempt.")
        
        # Celery task dispatch is now handled by WorkflowStateMachine.on_task_queued callback
        logger.info(f"Task {task.task_id} state is now {task.state}. Celery dispatch handled by state machine.")

        return {
            "task_id": task.task_id,
            "status": "task_queued_in_state_machine", # Indicates state machine handled queuing
            "celery_task_id": task.metadata.get('celery_task_id'), # Get from metadata if set by callback
            "state": task.state, 
            "queued_at": task.started_at.isoformat() if task.started_at else datetime.utcnow().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting workflow task {task_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/workflow/{task_id}/cancel")
async def cancel_workflow_task(task_id: str):
    """Cancel a workflow task."""
    try:
        task = workflow_sm.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        
        task.cancel_task()
        return {
            "task_id": task_id,
            "status": "cancelled",
            "state": task.state
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling workflow task {task_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/workflow/{task_id}/retry")
async def retry_workflow_task(task_id: str):
    """Retry a failed workflow task."""
    try:
        task = workflow_sm.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        
        if task.state != "failed":
            raise HTTPException(status_code=400, detail=f"Task {task_id} is not in failed state")
        
        if not workflow_sm.can_retry(task):
            raise HTTPException(status_code=400, detail=f"Task {task_id} has exceeded maximum retries")
        
        task.retry_task()
        return {
            "task_id": task_id,
            "status": "retrying",
            "state": task.state,
            "retry_count": task.retry_count
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrying workflow task {task_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/workflow/{task_id}/status")
async def get_workflow_task_status(task_id: str):
    """Get detailed status of a workflow task."""
    try:
        task = workflow_sm.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        
        next_step = workflow_sm.get_next_step(task)
        
        return {
            "task_id": task.task_id,
            "workflow_name": task.workflow_name,
            "state": task.state,
            "priority": task.priority,
            "created_at": task.created_at.isoformat(),
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "current_step": task.current_step,
            "completed_steps": task.completed_steps,
            "failed_steps": task.failed_steps,
            "retry_count": task.retry_count,
            "max_retries": task.max_retries,
            "error_message": task.error_message,
            "next_step": next_step.name if next_step else None,
            "progress": {
                "total_steps": len(task.step_executions),
                "completed": len(task.completed_steps),
                "failed": len(task.failed_steps),
                "percentage": len(task.completed_steps) / max(len(task.step_executions), 1) * 100 if task.step_executions else 0
            },
            "conversation_history": task.conversation_history,
            "final_result": task.final_result,
            "metadata": task.metadata
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting workflow task status {task_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/workflow/statistics")
async def get_workflow_statistics():
    """Get workflow system statistics."""
    try:
        stats = workflow_sm.get_task_statistics()
        return {
            "statistics": stats,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting workflow statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/workflow/tasks")
async def list_workflow_tasks(state: str = None, limit: int = 50):
    """List workflow tasks with optional state filtering."""
    try:
        all_tasks = workflow_sm.get_all_tasks() # Get all tasks from Redis
        tasks = []
        for task in all_tasks:
            if state and task.state != state:
                continue
            
            tasks.append({
                "task_id": task.task_id,
                "workflow_name": task.workflow_name,
                "state": task.state,
                "priority": task.priority.value, # Ensure enum value is returned as string
                "created_at": task.created_at.isoformat(),
                "current_step": task.current_step,
                "progress": len(task.completed_steps) / max(len(task.step_executions), 1) * 100 if task.step_executions else 0
            })
        
        tasks.sort(key=lambda x: x["created_at"], reverse=True)
        return {"tasks": tasks[:limit]}
    except Exception as e:
        logger.error(f"Error listing workflow tasks: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/system/health")
async def get_system_health():
    """Get comprehensive system health status."""
    try:
        health_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "services": {},
            "metrics": {}
        }
        
        # Multi-agent system health
        if multi_agent_system:
            try:
                # Ensure get_system_health returns a dict with 'status'
                mas_health = multi_agent_system.get_system_health()
                if isinstance(mas_health, dict) and "status" in mas_health:
                    health_data["services"]["multi_agent"] = mas_health
                else:
                    logger.error(f"multi_agent_system.get_system_health() returned unexpected data: {mas_health}")
                    health_data["services"]["multi_agent"] = {"status": "error", "error": "Invalid health data format from multi_agent_system"}
            except Exception as e:
                logger.error(f"Error getting multi_agent_system health: {e}")
                health_data["services"]["multi_agent"] = {"status": "error", "error": str(e)}
        else:
            # This case implies multi_agent_system was not initialized or failed to start
            health_data["services"]["multi_agent"] = {"status": "unavailable", "message": "Multi-agent system is not initialized or failed to start."}
        
        # MCP health
        try:
            mcp_statuses = await mcp_manager.get_all_server_status()
            # MCPServerStatus is a Pydantic model, access fields as attributes
            all_healthy = all(s.status == "healthy" for s in mcp_statuses if hasattr(s, 'status'))
            health_data["services"]["mcp"] = {
                "status": "healthy" if all_healthy and mcp_statuses else "degraded",
                "servers": [s.model_dump() for s in mcp_statuses] # Convert Pydantic models to dicts for JSON response
            }
        except Exception as e:
            health_data["services"]["mcp"] = {"status": "error", "error": str(e)}
        
        # Workflow system health
        try:
            workflow_stats = workflow_sm.get_task_statistics()
            health_data["services"]["workflow"] = {
                "status": "healthy",
                "statistics": workflow_stats
            }
        except Exception as e:
            health_data["services"]["workflow"] = {"status": "error", "error": str(e)}
        
        # System metrics (mock data for now)
        health_data["metrics"] = {
            "memory_usage": "N/A",
            "cpu_usage": "N/A",
            "redis_status": "N/A",
            "celery_workers": "N/A"
        }
        
        return health_data
    except Exception as e:
        logger.error(f"Error getting system health: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Enhanced MCP endpoints with monitoring
@app.get("/mcp/status")
async def get_mcp_status():
    """Get status of all MCP servers."""
    try:
        statuses = await mcp_manager.get_all_server_status()
        return {"mcp_servers": statuses}
    except Exception as e:
        logger.error(f"Error getting MCP status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/mcp/{server_id}/status")
async def get_mcp_server_status(server_id: str):
    """Get status of a specific MCP server."""
    try:
        status = await mcp_manager.get_server_status(server_id)
        if not status:
            raise HTTPException(status_code=404, detail=f"MCP server '{server_id}' not found")
        return status
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting MCP server status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/mcp/{server_id}/health-check")
async def force_mcp_health_check(server_id: str):
    """Force a health check for a specific MCP server."""
    try:
        result = await mcp_manager.check_server_health(server_id)
        return {"server_id": server_id, "healthy": result}
    except Exception as e:
        logger.error(f"Error performing health check: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Enhanced endpoints with security
@app.post("/chat")
@rate_limit(chat_rate_limiter)
async def chat_endpoint_secured(
    request: Request,
    chat_request: ChatRequest,
    _: bool = Depends(validate_api_key)
):
    """Chat with the multi-agent system (with security)."""
    if not multi_agent_system:
        raise HTTPException(status_code=503, detail="Multi-agent system not available")
    
    try:
        # Sanitize input
        sanitized_message = sanitize_input(chat_request.message, max_length=5000)
        
        response = await multi_agent_system.send_message(
            sanitized_message, 
            chat_request.agent_type or "coordinator"
        )
        return {"response": response}
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/mcp-github/repos")
@rate_limit(api_rate_limiter)
async def list_github_repos_secured(request: Request):
    """List GitHub repositories via MCP server (with health check)."""
    try:
        # Use enhanced MCP request with health checking
        response = await make_mcp_request("github", "repos")
        return response
    except httpx.HTTPError as e:
        logger.error(f"GitHub MCP server error: {e}")
        raise HTTPException(status_code=503, detail="GitHub MCP server unavailable")
    except Exception as e:
        logger.error(f"GitHub MCP server error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/mcp-brave-search/search")
@rate_limit(api_rate_limiter)
async def brave_search_secured(request: Request, query: str):
    """Perform Brave Search via MCP server (with health check)."""
    try:
        # Sanitize query
        sanitized_query = sanitize_input(query, max_length=500)
        
        # Use enhanced MCP request with health checking
        response = await make_mcp_request("brave_search", "search", params={"q": sanitized_query})
        return response
    except httpx.HTTPError as e:
        logger.error(f"Brave Search MCP server error: {e}")
        raise HTTPException(status_code=503, detail="Brave Search MCP server unavailable")
    except Exception as e:
        logger.error(f"Brave Search MCP server error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/mcp-sqlite/query")
@rate_limit(api_rate_limiter)
async def sqlite_query_secured(
    request: Request, 
    query_request: dict,
    _: bool = Depends(validate_api_key)
):
    """Execute SQLite query via MCP server (with health check and security)."""
    try:
        # Basic validation
        if "sql" not in query_request:
            raise HTTPException(status_code=400, detail="SQL query is required")
        
        # Sanitize SQL query
        sanitized_sql = sanitize_input(query_request["sql"], max_length=2000)
        query_request["sql"] = sanitized_sql
        
        # Use enhanced MCP request with health checking
        response = await make_mcp_request("sqlite", "query", method="POST", json=query_request)
        return response
    except httpx.HTTPError as e:
        logger.error(f"SQLite MCP server error: {e}")
        raise HTTPException(status_code=503, detail="SQLite MCP server unavailable")
    except Exception as e:
        logger.error(f"SQLite MCP server error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Security headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add security headers to all responses."""
    response = await call_next(request)
    return SecurityHeaders.add_security_headers(response)


# Error handlers
@app.exception_handler(429)
async def rate_limit_handler(request: Request, exc: HTTPException):
    """Handle rate limit exceeded errors."""
    return JSONResponse(
        status_code=429,
        content={
            "error": "Rate limit exceeded",
            "message": "Too many requests. Please try again later.",
            "retry_after": 60
        }
    )


@app.exception_handler(500)
async def internal_error_handler(request: Request, exc: HTTPException):
    """Handle internal server errors."""
    logger.error(f"Internal server error: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": "An unexpected error occurred. Please try again later."
        }
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload and settings.environment.value == "development",
        log_level=settings.log_level.value.lower()
    )
