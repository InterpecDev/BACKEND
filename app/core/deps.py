from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt

from app.core.config import JWT_SECRET  # usa tu config.py

bearer = HTTPBearer()
JWT_ALG = "HS256"

def get_current_user(creds: HTTPAuthorizationCredentials = Depends(bearer)):
    token = creds.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        return payload  # {sub, role, email, exp, iat}
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado.")
    except Exception:
        raise HTTPException(status_code=401, detail="Token inválido.")
