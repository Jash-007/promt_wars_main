# backend/app/auth.py
import os
import uuid
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional
from jose import jwt, JWTError
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger(__name__)

SECRET_KEY = os.getenv("SECRET_KEY", "stressfreak-production-secret-auth-key-2026")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440  # 24 hours

# Simple password hashing helper using SHA-256 + salt
def hash_password(password: str) -> str:
    """Secure SHA-256 hashing with key-salting."""
    salt = "stressfreak-secure-salt-987"
    return hashlib.sha256((password + salt).encode('utf-8')).hexdigest()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain password against the saved hash."""
    return hash_password(plain_password) == hashed_password

# JWT Helper Functions
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Creates a JWT token carrying user profile data."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# In-memory user database matching PostgreSQL mapping
USERS_DB: Dict[str, dict] = {
    # Default seed user for testing
    "aspirant": {
        "id": "a4d5e123-b123-4c56-8901-234567890abc",
        "username": "aspirant",
        "email": "student@stressfreak.in",
        "full_name": "Aspirant Rahul",
        "hashed_password": hash_password("password123"),
        "exam_type": "JEE_MAIN",
        "created_at": datetime.utcnow()
    }
}

# Bearer token helper
security_scheme = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security_scheme)) -> dict:
    """
    Dependency injection to secure endpoints.
    Validates the JWT token signature and returns the authenticated user payload.
    """
    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    user = USERS_DB.get(username)
    if user is None:
        raise credentials_exception
        
    return user
