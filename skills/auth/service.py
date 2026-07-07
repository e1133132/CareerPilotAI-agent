from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from config import settings
from db.session import database_enabled, db_session


def _accounts_path() -> Path:
    path = Path(settings.AUTH_ACCOUNTS_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _load_accounts() -> dict[str, Any]:
    path = _accounts_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_accounts(accounts: dict[str, Any]) -> None:
    _accounts_path().write_text(json.dumps(accounts, ensure_ascii=False, indent=2), encoding="utf-8")


def _hash_password(password: str, salt: str) -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        settings.AUTH_PASSWORD_ITERATIONS,
    )
    return digest.hex()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def register_user(*, username: str, password: str, email: str | None = None) -> dict[str, Any]:
    username = (username or "").strip().lower()
    if len(username) < 3:
        raise ValueError("Username must be at least 3 characters")
    if len(password) < 6:
        raise ValueError("Password must be at least 6 characters")

    if database_enabled():
        return _register_user_db(username=username, password=password, email=email)
    return _register_user_json(username=username, password=password, email=email)


def _register_user_json(*, username: str, password: str, email: str | None) -> dict[str, Any]:
    accounts = _load_accounts()
    if username in accounts:
        raise ValueError("Username already exists")

    user_id = uuid.uuid4().hex[:16]
    salt = secrets.token_hex(16)
    now = _utc_now().isoformat().replace("+00:00", "Z")
    accounts[username] = {
        "user_id": user_id,
        "username": username,
        "email": (email or "").strip() or None,
        "password_hash": _hash_password(password, salt),
        "salt": salt,
        "created_at": now,
    }
    _save_accounts(accounts)
    return {"user_id": user_id, "username": username, "email": accounts[username]["email"]}


def _register_user_db(*, username: str, password: str, email: str | None) -> dict[str, Any]:
    from sqlalchemy import select

    from db.models import Account

    user_id = uuid.uuid4().hex[:16]
    salt = secrets.token_hex(16)
    email_value = (email or "").strip() or None
    row = Account(
        user_id=user_id,
        username=username,
        email=email_value,
        password_hash=_hash_password(password, salt),
        salt=salt,
        created_at=_utc_now(),
    )
    with db_session() as session:
        existing = session.execute(select(Account).where(Account.username == username)).scalar_one_or_none()
        if existing:
            raise ValueError("Username already exists")
        session.add(row)
    return {"user_id": user_id, "username": username, "email": email_value}


def authenticate_user(*, username: str, password: str) -> dict[str, Any]:
    username = (username or "").strip().lower()
    if database_enabled():
        return _authenticate_user_db(username=username, password=password)
    return _authenticate_user_json(username=username, password=password)


def _authenticate_user_json(*, username: str, password: str) -> dict[str, Any]:
    row = _load_accounts().get(username)
    if not row:
        raise ValueError("Invalid username or password")
    expected = _hash_password(password, str(row.get("salt") or ""))
    if expected != row.get("password_hash"):
        raise ValueError("Invalid username or password")
    return {
        "user_id": str(row.get("user_id") or ""),
        "username": username,
        "email": row.get("email"),
    }


def _authenticate_user_db(*, username: str, password: str) -> dict[str, Any]:
    from sqlalchemy import select

    from db.models import Account

    with db_session() as session:
        row = session.execute(select(Account).where(Account.username == username)).scalar_one_or_none()
        if not row:
            raise ValueError("Invalid username or password")
        expected = _hash_password(password, row.salt)
        if expected != row.password_hash:
            raise ValueError("Invalid username or password")
        return {"user_id": row.user_id, "username": username, "email": row.email}


def _jwt_encode(payload: dict[str, Any]) -> str:
    import jwt

    exp = _utc_now() + timedelta(hours=settings.AUTH_JWT_EXPIRE_HOURS)
    body = {**payload, "exp": exp}
    return jwt.encode(body, settings.AUTH_JWT_SECRET, algorithm=settings.AUTH_JWT_ALGORITHM)


def _jwt_decode(token: str) -> dict[str, Any]:
    import jwt

    return jwt.decode(token, settings.AUTH_JWT_SECRET, algorithms=[settings.AUTH_JWT_ALGORITHM])


def create_access_token(*, user_id: str, username: str) -> str:
    return _jwt_encode({"sub": user_id, "username": username})


def verify_access_token(token: str) -> dict[str, Any]:
    if not token or not token.strip():
        raise ValueError("Missing token")
    payload = _jwt_decode(token.strip())
    user_id = str(payload.get("sub") or "").strip()
    username = str(payload.get("username") or "").strip()
    if not user_id:
        raise ValueError("Invalid token")
    return {"user_id": user_id, "username": username}


def get_account_by_user_id(user_id: str) -> dict[str, Any] | None:
    uid = str(user_id or "").strip()
    if not uid:
        return None
    if database_enabled():
        return _get_account_by_user_id_db(uid)
    for row in _load_accounts().values():
        if str(row.get("user_id") or "") == uid:
            return dict(row)
    return None


def _get_account_by_user_id_db(user_id: str) -> dict[str, Any] | None:
    from sqlalchemy import select

    from db.models import Account

    with db_session() as session:
        row = session.execute(select(Account).where(Account.user_id == user_id)).scalar_one_or_none()
        if not row:
            return None
        return {
            "user_id": row.user_id,
            "username": row.username,
            "email": row.email,
            "created_at": row.created_at.isoformat().replace("+00:00", "Z") if row.created_at else None,
        }
