import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader

from .settings import settings

api_key_header = APIKeyHeader(
    name=settings.API_KEY_HEADER,
    scheme_name="ApiKeyAuth",
    description="Hold API key (try 42)",
    auto_error=False,
)


def api_key_auth(
    api_key: str = Security(api_key_header),
) -> str:
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
            headers={"WWW-Authenticate": api_key_header.scheme_name},
        )

    if not secrets.compare_digest(api_key, settings.API_KEY_SECRET):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
            headers={"WWW-Authenticate": api_key_header.scheme_name},
        )

    return api_key


Protected = Annotated[str, Depends(api_key_auth)]
