"""Security middleware and utilities for Moda Vibe Code application."""

import time
import hashlib
import secrets
from typing import Dict, Optional
from fastapi import HTTPException, Request, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from functools import wraps
import asyncio
from collections import defaultdict, deque

from config import get_settings

settings = get_settings()

# Rate limiting storage
rate_limit_storage: Dict[str, deque] = defaultdict(deque)

# API key for basic authentication (should be set via environment variable)
API_KEY = settings.api_key if hasattr(settings, 'api_key') else None

security = HTTPBearer(auto_error=False)


class RateLimiter:
    """Rate limiting implementation."""
    
    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
    
    def is_allowed(self, client_id: str) -> bool:
        """Check if request is allowed based on rate limits."""
        now = time.time()
        window_start = now - self.window_seconds
        
        # Get client's request history
        requests = rate_limit_storage[client_id]
        
        # Remove old requests outside the window
        while requests and requests[0] < window_start:
            requests.popleft()
        
        # Check if under limit
        if len(requests) >= self.max_requests:
            return False
        
        # Add current request
        requests.append(now)
        return True


# Global rate limiter instances
api_rate_limiter = RateLimiter(max_requests=100, window_seconds=60)
chat_rate_limiter = RateLimiter(max_requests=20, window_seconds=60)


def get_client_id(request: Request) -> str:
    """Get client identifier for rate limiting."""
    # Use IP address as primary identifier
    client_ip = request.client.host if request.client else "unknown"
    
    # Include user agent for better tracking
    user_agent = request.headers.get("user-agent", "")
    user_agent_hash = hashlib.md5(user_agent.encode()).hexdigest()[:8]
    
    return f"{client_ip}:{user_agent_hash}"


def rate_limit(limiter: RateLimiter):
    """Rate limiting decorator."""
    def decorator(func):
        @wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            client_id = get_client_id(request)
            
            if not limiter.is_allowed(client_id):
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded. Please try again later."
                )
            
            return await func(request, *args, **kwargs)
        return wrapper
    return decorator


def validate_api_key(credentials: Optional[HTTPAuthorizationCredentials] = Security(security)):
    """Validate API key for protected endpoints."""
    if not API_KEY:
        # If no API key is configured, allow access (for development)
        return True
    
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not secrets.compare_digest(credentials.credentials, API_KEY):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return True


def sanitize_input(text: str, max_length: int = 10000) -> str:
    """Sanitize user input."""
    if not isinstance(text, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Input must be a string"
        )
    
    if len(text) > max_length:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Input too long. Maximum {max_length} characters allowed."
        )
    
    # Remove potential harmful characters
    sanitized = text.replace('\x00', '').replace('\r', '').strip()
    
    return sanitized


async def verify_mcp_server_health(url: str, timeout: int = 5) -> bool:
    """Verify MCP server health."""
    import httpx
    
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(f"{url}/health")
            return response.status_code == 200
    except Exception:
        return False


class SecurityHeaders:
    """Security headers middleware."""
    
    @staticmethod
    def add_security_headers(response):
        """Add security headers to response."""
        response.headers.update({
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline';",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "camera=(), microphone=(), geolocation=()"
        })
        return response
