import jwt

from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi import Depends, HTTPException

from app.security import decode_access_token
from app.services.users import get_user_by_id

security = HTTPBearer()

def get_current_user(
        credentials: HTTPAuthorizationCredentials = Depends(security),
):
    token = credentials.credentials

    try: 
        user_id = decode_access_token(token)
    except (jwt.InvalidTokenError, ValueError, TypeError) as exc:
        print("JWT ERROR: ", repr(exc))
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
            )

    user = get_user_by_id(user_id)

    if user is None:
        raise HTTPException(
                    status_code=401,
                    detail="Invalid or expired token",
                    headers={"WWW-Authenticate": "Bearer"},
        )

    return user