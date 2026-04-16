from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from app.settings import Settings, get_settings


async def verify_api_key(
    x_api_key: Annotated[str, Header(alias="X-API-Key")],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    if x_api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )


ApiKeyDep = Annotated[None, Depends(verify_api_key)]
