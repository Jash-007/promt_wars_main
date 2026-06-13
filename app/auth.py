# backend/app/auth.py
import os
import uuid
import base64
import json
import hmac
import hashlib
import logging
from time import time
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger(__name__)

SECRET_KEY: str = os.getenv("SECRET_KEY", "stressfreak-production-secret-auth-key-2026")
ALGORITHM: str = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours

# In-memory validation cache to prevent signature decoding overhead on subsequent requests (Efficiency boost)
TOKEN_VALIDATION_CACHE: Dict[str, Tuple[float, dict]] = {}

# --- Pure Python JWT (HS256) Implementation (Eliminates python-jose/ModuleNotFoundError) ---
def base64url_encode(data: bytes) -> str:
    """Encodes bytes payload into safe URL base64 format."""
    return base64.urlsafe_b64encode(data).replace(b'=', b'').decode('utf-8')

def base64url_decode(data: str) -> bytes:
    """Decodes URL base64 format back to bytes, adding padding if required."""
    rem = len(data) % 4
    if rem > 0:
        data += '=' * (4 - rem)
    return base64.urlsafe_b64decode(data.encode('utf-8'))

def custom_jwt_encode(payload: dict, secret: str) -> str:
    """Generates standard JWT using HMAC-SHA256 with zero third-party dependencies."""
    header = {"alg": "HS256", "typ": "JWT"}
    header_bytes = json.dumps(header, separators=(',', ':')).encode('utf-8')
    payload_bytes = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    
    unsigned_part = base64url_encode(header_bytes) + "." + base64url_encode(payload_bytes)
    
    # Compute signature
    signature = hmac.new(secret.encode('utf-8'), unsigned_part.encode('utf-8'), hashlib.sha256).digest()
    return unsigned_part + "." + base64url_encode(signature)

def custom_jwt_decode(token: str, secret: str) -> dict:
    """Decodes and validates standard JWT signature and expiry."""
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid JWT format structure")
        
    unsigned_part = parts[0] + "." + parts[1]
    signature = base64url_decode(parts[2])
    
    # Verify HMAC-SHA256 signature
    expected_signature = hmac.new(secret.encode('utf-8'), unsigned_part.encode('utf-8'), hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected_signature):
        raise ValueError("JWT Signature validation failed")
        
    payload = json.loads(base64url_decode(parts[1]).decode('utf-8'))
    
    # Validate expiration time
    exp = payload.get("exp")
    if exp and time() > exp:
        raise ValueError("JWT Token has expired")
        
    return payload
# --------------------------------------------------------------------------------------------

def hash_password(password: str) -> str:
    """Secure SHA-256 hashing with key-salting."""
    salt = "stressfreak-secure-salt-987"
    return hashlib.sha256((password + salt).encode('utf-8')).hexdigest()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain password against the saved hash."""
    return hash_password(plain_password) == hashed_password

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Creates a JWT token carrying user profile data."""
    to_encode = data.copy()
    if expires_delta:
        expire = time() + expires_delta.total_seconds()
    else:
        expire = time() + (ACCESS_TOKEN_EXPIRE_MINUTES * 60)
    
    to_encode.update({"exp": expire})
    encoded_jwt: str = custom_jwt_encode(to_encode, SECRET_KEY)
    return encoded_jwt

# In-memory user database matching PostgreSQL mapping
USERS_DB: Dict[str, dict] = {
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
    Uses an in-memory cache to prevent repetitive JWT decoding overhead.
    """
    token: str = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # Evaluate cache hit (15 min TTL) to bypass expensive crypto decoding
    now: float = time()
    if token in TOKEN_VALIDATION_CACHE:
        cache_time, cached_user = TOKEN_VALIDATION_CACHE[token]
        if now - cache_time < 900:  # 15 minutes validity
            return cached_user

    # Decode and validate JWT using pure Python helper
    try:
        payload = custom_jwt_decode(token, SECRET_KEY)
        username: Optional[str] = payload.get("sub")
        if username is None:
            raise credentials_exception
    except Exception as e:
        logger.warning(f"JWT decode error: {e}")
        raise credentials_exception
        
    user = USERS_DB.get(username)
    if user is None:
        raise credentials_exception
        
    TOKEN_VALIDATION_CACHE[token] = (now, user)
    return user
