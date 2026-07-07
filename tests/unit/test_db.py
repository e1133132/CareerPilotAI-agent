from __future__ import annotations

from sqlalchemy import select

from db.models import Account, UserMemoryRow
from db.session import db_session
from skills.auth.service import register_user
from skills.user_memory import load_user_memory, save_user_memory


def test_accounts_table_roundtrip(sql_db) -> None:
    user = register_user(username="sqluser", password="secret12", email="u@example.com")
    with db_session() as session:
        row = session.execute(select(Account).where(Account.username == "sqluser")).scalar_one()
        assert row.user_id == user["user_id"]
        assert row.email == "u@example.com"


def test_user_memory_table_roundtrip(sql_db) -> None:
    record = {
        "user_id": "mem123",
        "preferred_target_roles": ["Data Analyst"],
        "rejected_job_ids": ["jd-999"],
        "saved_job_ids": [],
        "run_history": [{"run_id": "r1"}],
    }
    save_user_memory(record)
    loaded = load_user_memory("mem123")
    assert loaded["preferred_target_roles"] == ["Data Analyst"]
    assert loaded["rejected_job_ids"] == ["jd-999"]

    with db_session() as session:
        row = session.execute(select(UserMemoryRow).where(UserMemoryRow.user_id == "mem123")).scalar_one()
        assert row.run_history == [{"run_id": "r1"}]
