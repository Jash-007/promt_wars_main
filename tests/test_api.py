# backend/tests/test_api.py
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_check_endpoint():
    """Verify that health check returns 200 operational."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "operational"

def test_user_auth_and_secured_flow():
    """Verifies user registration, login, and secured profile retrieval."""
    test_user = {
        "username": "rahul_test",
        "email": "rahul@student.in",
        "full_name": "Rahul Test",
        "password": "securepassword123",
        "exam_type": "JEE_MAIN"
    }

    # 1. Register User
    reg_resp = client.post("/api/v1/auth/register", json=test_user)
    assert reg_resp.status_code == 200
    assert reg_resp.json()["username"] == "rahul_test"
    assert "id" in reg_resp.json()

    # 2. Register Duplicate User (Should fail with 400)
    dup_resp = client.post("/api/v1/auth/register", json=test_user)
    assert dup_resp.status_code == 400
    assert "already registered" in dup_resp.json()["detail"].lower()

    # 3. Login User
    login_payload = {
        "username_or_email": "rahul_test",
        "password": "securepassword123"
    }
    login_resp = client.post("/api/v1/auth/login", json=login_payload)
    assert login_resp.status_code == 200
    assert "access_token" in login_resp.json()
    assert login_resp.json()["token_type"] == "bearer"

    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 4. Access Secured User Profile (/me)
    me_resp = client.get("/api/v1/auth/me", headers=headers)
    assert me_resp.status_code == 200
    assert me_resp.json()["full_name"] == "Rahul Test"
    assert me_resp.json()["exam_type"] == "JEE_MAIN"

    # 5. Access profile without headers (Should fail with 401)
    blocked_resp = client.get("/api/v1/auth/me")
    assert blocked_resp.status_code == 401

def test_journal_analysis_and_safety_intercepts():
    """Verifies that journal analysis functions securely, and intercepts crises."""
    # Register and login test student
    student = {
        "username": "safety_student",
        "email": "safety@student.in",
        "full_name": "Safety Test Student",
        "password": "studentpassword123",
        "exam_type": "NEET"
    }
    client.post("/api/v1/auth/register", json=student)
    
    login_resp = client.post("/api/v1/auth/login", json={
        "username_or_email": "safety_student",
        "password": "studentpassword123"
    })
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Test 1: Safe journal analysis
    safe_entry = {
        "content": "Today I studied kinematics for 3 hours, but I got stuck on mock questions. I will review it tomorrow."
    }
    resp1 = client.post("/api/v1/journal/analyze", json=safe_entry, headers=headers)
    assert resp1.status_code == 200
    assert "stress_level" in resp1.json()
    assert len(resp1.json()["insights"]) > 0

    # Test 2: Unsafe journal entry (suicide crisis)
    unsafe_entry = {
        "content": "I can't take this pressure anymore. I want to commit suicide tonight, everything is over."
    }
    resp2 = client.post("/api/v1/journal/analyze", json=unsafe_entry, headers=headers)
    assert resp2.status_code == 400
    assert resp2.json()["detail"] == "crisis_triggered"
    assert resp2.json()["crisis_data"]["crisis_triggered"] is True
    assert len(resp2.json()["crisis_data"]["helplines"]) >= 3

def test_mock_tests_and_dashboard_correlation():
    """Verifies that logging mock tests works, and aggregates correlation dashboard data."""
    # Register and login test student
    student = {
        "username": "dashboard_student",
        "email": "dashboard@student.in",
        "full_name": "Dashboard Student",
        "password": "studentpassword123",
        "exam_type": "UPSC"
    }
    client.post("/api/v1/auth/register", json=student)
    
    login_resp = client.post("/api/v1/auth/login", json={
        "username_or_email": "dashboard_student",
        "password": "studentpassword123"
    })
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Log a Mock test
    mock_payload = {
        "test_name": "UPSC Prelims Mock 1",
        "test_date": "2026-06-13",
        "score": 140,
        "total_marks": 200,
        "percentile": 92.5,
        "accuracy": 81.0
    }
    mock_resp = client.post("/api/v1/analytics/mock-test", json=mock_payload, headers=headers)
    assert mock_resp.status_code == 200
    assert mock_resp.json()["status"] == "success"
    assert mock_resp.json()["test"]["test_name"] == "UPSC Prelims Mock 1"

    # 2. Fetch dashboard data
    dash_resp = client.get("/api/v1/analytics/dashboard", headers=headers)
    assert dash_resp.status_code == 200
    assert "mock_tests" in dash_resp.json()
    assert "stress_entries" in dash_resp.json()
    
    # Assert logged mock test appears in database
    mock_names = [t["test_name"] for t in dash_resp.json()["mock_tests"]]
    assert "UPSC Prelims Mock 1" in mock_names
