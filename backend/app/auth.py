import os
from typing import Annotated
from dataclasses import dataclass

import jwt
from fastapi import Depends, Header, HTTPException
from jwt import PyJWKClient

SUPABASE_URL = os.environ["SUPABASE_URL"]
JWKS_URL = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"

jwks_client = PyJWKClient(JWKS_URL, cache_keys=True)

@dataclass
class User:
    id: str
    roles: list[str]


async def get_current_user(authorization: str = Header(...)) -> User:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    token = authorization.removeprefix("Bearer ").strip()

    try:
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256", "RS256"],
            audience="authenticated",
        )
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return User(id=payload["sub"], roles=payload.get("user_roles", []))


CurrentUser = Annotated[User, Depends(get_current_user)]

def require_role(role: str):
    async def check_role(user: CurrentUser) -> User:
        if role not in user.roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user

    return check_role
