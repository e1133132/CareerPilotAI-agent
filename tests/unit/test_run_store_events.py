from __future__ import annotations

import queue
import threading
import time

from pipeline.session import RunStore


def test_subscribe_notified_on_update() -> None:
    store = RunStore()
    store.create(
        run_id="r1",
        state={"x": 1},
        plan_status="pending",
        resume_status="pending",
        apply_status="pending",
    )
    q = store.subscribe("r1")
    store.update("r1", latest_step_message="step")
    q.get(timeout=1.0)
    store.unsubscribe("r1", q)


def test_subscribe_notified_on_create_for_late_subscriber_via_update() -> None:
    store = RunStore()
    q = store.subscribe("r2")
    store.create(
        run_id="r2",
        state={},
        plan_status="pending",
        resume_status="skipped",
        apply_status="pending",
    )
    q.get(timeout=1.0)
    store.unsubscribe("r2", q)


def test_wait_blocks_until_update() -> None:
    store = RunStore()
    store.create(
        run_id="r3",
        state={},
        plan_status="pending",
        resume_status="pending",
        apply_status="pending",
    )
    q = store.subscribe("r3")
    seen = {"ok": False}

    def waiter() -> None:
        q.get(timeout=2.0)
        seen["ok"] = True

    t = threading.Thread(target=waiter)
    t.start()
    time.sleep(0.05)
    store.update("r3", status="done")
    t.join(timeout=2.0)
    assert seen["ok"] is True
    store.unsubscribe("r3", q)


def test_unsubscribe_stops_delivery() -> None:
    store = RunStore()
    store.create(
        run_id="r4",
        state={},
        plan_status="pending",
        resume_status="pending",
        apply_status="pending",
    )
    q = store.subscribe("r4")
    store.unsubscribe("r4", q)
    store.update("r4", status="done")
    try:
        q.get(timeout=0.05)
        raised = False
    except queue.Empty:
        raised = True
    assert raised is True
