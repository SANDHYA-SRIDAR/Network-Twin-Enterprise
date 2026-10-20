from typing import Annotated

from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer = HTTPBearer(auto_error=False, scheme_name="SupabaseBearer", bearerFormat="JWT", description="The signed-in user's Supabase access token. Do not enter a project API key.")


def require_access_token(credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer)]) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials.strip() or any(c.isspace() for c in credentials.credentials):
        raise HTTPException(status_code=401, detail="Sign in and send Authorization: Bearer <user access token>.", headers={"WWW-Authenticate": "Bearer"})
    token = credentials.credentials.strip()
    if token.startswith(("sb_publishable_", "sb_secret_")):
        raise HTTPException(status_code=401, detail="A project API key is not a user session. Send your signed-in user's access token.", headers={"WWW-Authenticate": "Bearer"})
    return token
