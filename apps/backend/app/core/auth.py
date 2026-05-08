from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader

from app.core.config import get_settings

x_api_key_header = APIKeyHeader(
    name="x-api-key",
    auto_error=False,
    description="API key from API_AUTH_KEY. Use this in Swagger Authorize.",
)


async def require_api_key(x_api_key: str | None = Depends(x_api_key_header)) -> None:
    settings = get_settings()
    if not x_api_key or x_api_key != settings.api_auth_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid API key",
        )
