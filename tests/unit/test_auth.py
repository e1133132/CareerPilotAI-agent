from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import api
from config import settings
from db import reset_database_engine
from skills.auth.service import authenticate_user, create_access_token, register_user, verify_access_token
from skills.user_memory import derive_user_id


def test_register_and_login_roundtrip(sql_db) -> None:
    user = register_user(username="alice", password="secret12", email="a@example.com")
    assert user["username"] == "alice"
    assert user["user_id"]

    authed = authenticate_user(username="alice", password="secret12")
    assert authed["user_id"] == user["user_id"]

    with pytest.raises(ValueError, match="Invalid username or password"):
        authenticate_user(username="alice", password="wrong")


def test_jwt_create_and_verify(sql_db) -> None:
    user = register_user(username="bob", password="secret12")
    token = create_access_token(user_id=user["user_id"], username=user["username"])
    payload = verify_access_token(token)
    assert payload["user_id"] == user["user_id"]
    assert payload["username"] == "bob"


def test_derive_user_id_prefers_account(sql_db) -> None:
    user = register_user(username="carol", password="secret12")
    uid = derive_user_id(
        client_id="anonymous-client",
        resume_text="some resume",
        account_user_id=user["user_id"],
    )
    assert uid == user["user_id"]


def test_auth_api_register_login_me(sql_db, monkeypatch) -> None:
    monkeypatch.setattr(settings, "AUTH_JWT_SECRET", "test-secret-key-at-least-32-bytes!!")
    reset_database_engine()
    from db import init_database

    init_database()
    client = TestClient(api.app)

    reg = client.post(
        "/api/auth/register",
        json={"username": "demo", "password": "secret12", "email": "d@example.com"},
    )
    assert reg.status_code == 200
    reg_body = reg.json()
    assert reg_body["ok"] is True
    assert reg_body["user"]["username"] == "demo"

    login = client.post("/api/auth/login", json={"username": "demo", "password": "secret12"})
    assert login.status_code == 200
    login_body = login.json()
    token = login_body["token"]
    assert token

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["user"]["username"] == "demo"
