# backend/tests/test_auth.py
import pytest
from datetime import timedelta
from jose import jwt
from app.auth import (
    hash_password,
    verify_password,
    create_access_token,
    SECRET_KEY,
    ALGORITHM
)

def test_password_hashing():
    """Verify passwords are salted and hashed correctly."""
    pw = "mySecretPassword123"
    hashed = hash_password(pw)
    assert hashed != pw
    assert len(hashed) == 64  # SHA-256 length in hex
    
    # Test verification matches
    assert verify_password(pw, hashed) is True
    assert verify_password("wrongpw", hashed) is False

def test_jwt_token_generation():
    """Verify JWT access tokens encode data and carry correct signatures."""
    payload = {"sub": "aspirant_test"}
    token = create_access_token(payload, expires_delta=timedelta(minutes=5))
    
    # Decode token and assert payload
    decoded = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    assert decoded["sub"] == "aspirant_test"
    assert "exp" in decoded
