import asyncio

import pytest
from fastapi import FastAPI

from biri_youyaku import app as app_module


@pytest.mark.asyncio
async def test_lifespan_shuts_down_distill_before_runner_maintenance_and_http(
    monkeypatch
):
    unfinished_jobs = {}
    events = []

    monkeypatch.setattr(app_module, "configure_logging", lambda: None)
    monkeypatch.setattr(app_module, "expected_token", lambda: "")
    monkeypatch.setattr(app_module, "init_db", lambda: None)
    monkeypatch.setattr(app_module, "clean_tempfile_residues", lambda: None)
    monkeypatch.setattr(app_module, "cleanup_once", lambda: _done())
    monkeypatch.setattr(app_module, "fail_stale_running_once", lambda: _done())
    monkeypatch.setattr(app_module, "scan_orphans_once", lambda: _done())
    monkeypatch.setattr(app_module.runner, "prepare_startup", lambda: events.append("runner.prepare"))
    monkeypatch.setattr(
        app_module.runner, "begin_shutdown", lambda: events.append("runner.begin_shutdown"), raising=False
    )
    monkeypatch.setattr(app_module.runner, "recover_unfinished_jobs", lambda: None)
    monkeypatch.setattr(
        app_module.distill_orchestrator, "prepare_startup", lambda: events.append("distill.prepare")
    )
    monkeypatch.setattr(
        app_module.distill_orchestrator,
        "begin_shutdown",
        lambda: events.append("distill.begin_shutdown"),
    )

    async def distill_shutdown():
        events.append("distill.shutdown")

    async def runner_shutdown():
        events.append("runner.shutdown")
        return unfinished_jobs

    monkeypatch.setattr(app_module.distill_orchestrator, "shutdown", distill_shutdown)
    monkeypatch.setattr(app_module.runner, "shutdown", runner_shutdown)
    monkeypatch.setattr(app_module, "cleanup_loop", lambda: _until_cancelled(events, "maintenance"))
    monkeypatch.setattr(app_module, "_warmup_asr", lambda: _until_cancelled(events, "warmup"))
    monkeypatch.setattr(app_module, "_backfill_tags", lambda: _until_cancelled(events, "tags"))

    async def close_http():
        events.append("http.close")

    monkeypatch.setattr(app_module, "aclose_all", close_http)

    async with app_module.lifespan(FastAPI()):
        events.append("body")
        await asyncio.sleep(0)

    assert events[:3] == ["runner.prepare", "distill.prepare", "body"]
    assert events[3:7] == [
        "runner.begin_shutdown",
        "distill.begin_shutdown",
        "distill.shutdown",
        "runner.shutdown",
    ]
    assert {"maintenance", "warmup", "tags"}.issubset(events[7:])
    assert events[-1] == "http.close"


@pytest.mark.asyncio
async def test_lifespan_closes_http_once_after_unfinished_job_completes(monkeypatch):
    completed = asyncio.Event()
    closed = []

    monkeypatch.setattr(app_module, "configure_logging", lambda: None)
    monkeypatch.setattr(app_module, "expected_token", lambda: "")
    monkeypatch.setattr(app_module, "init_db", lambda: None)
    monkeypatch.setattr(app_module, "clean_tempfile_residues", lambda: None)
    monkeypatch.setattr(app_module, "cleanup_once", lambda: _done())
    monkeypatch.setattr(app_module, "fail_stale_running_once", lambda: _done())
    monkeypatch.setattr(app_module, "scan_orphans_once", lambda: _done())
    monkeypatch.setattr(app_module.runner, "prepare_startup", lambda: None)
    monkeypatch.setattr(app_module.runner, "begin_shutdown", lambda: None)
    monkeypatch.setattr(app_module.runner, "recover_unfinished_jobs", lambda: None)
    monkeypatch.setattr(app_module.distill_orchestrator, "prepare_startup", lambda: None)
    monkeypatch.setattr(app_module.distill_orchestrator, "begin_shutdown", lambda: None)
    monkeypatch.setattr(app_module.distill_orchestrator, "shutdown", _done)

    async def runner_shutdown():
        return {"job-1": "TRANSCRIBING"}

    async def await_completion(job_id):
        await completed.wait()

    monkeypatch.setattr(app_module.runner, "shutdown", runner_shutdown)
    monkeypatch.setattr(app_module.runner, "await_job_completion", await_completion)
    monkeypatch.setattr(app_module, "cleanup_loop", lambda: _until_cancelled([], "maintenance"))
    monkeypatch.setattr(app_module, "_warmup_asr", lambda: _until_cancelled([], "warmup"))
    monkeypatch.setattr(app_module, "_backfill_tags", lambda: _until_cancelled([], "tags"))

    async def close_http():
        closed.append(True)

    monkeypatch.setattr(app_module, "aclose_all", close_http)

    async with app_module.lifespan(FastAPI()):
        await asyncio.sleep(0)

    assert closed == []
    assert app_module._deferred_http_close_tasks
    cleanup_task = next(iter(app_module._deferred_http_close_tasks))
    completed.set()
    await cleanup_task
    await asyncio.sleep(0)
    assert closed == [True]
    assert not app_module._deferred_http_close_tasks


@pytest.mark.asyncio
async def test_old_deferred_close_does_not_close_a_new_lifespan_client(monkeypatch):
    completed = asyncio.Event()
    closed = []
    shutdown_results = iter([{"job-1": "TRANSCRIBING"}, {"job-1": "TRANSCRIBING"}])

    monkeypatch.setattr(app_module, "configure_logging", lambda: None)
    monkeypatch.setattr(app_module, "expected_token", lambda: "")
    monkeypatch.setattr(app_module, "init_db", lambda: None)
    monkeypatch.setattr(app_module, "clean_tempfile_residues", lambda: None)
    monkeypatch.setattr(app_module, "cleanup_once", lambda: _done())
    monkeypatch.setattr(app_module, "fail_stale_running_once", lambda: _done())
    monkeypatch.setattr(app_module, "scan_orphans_once", lambda: _done())
    monkeypatch.setattr(app_module.runner, "prepare_startup", lambda: None)
    monkeypatch.setattr(app_module.runner, "begin_shutdown", lambda: None)
    monkeypatch.setattr(app_module.runner, "recover_unfinished_jobs", lambda: None)
    monkeypatch.setattr(app_module.runner, "has_active_task", lambda job_id: False)
    monkeypatch.setattr(app_module.distill_orchestrator, "prepare_startup", lambda: None)
    monkeypatch.setattr(app_module.distill_orchestrator, "begin_shutdown", lambda: None)
    monkeypatch.setattr(app_module.distill_orchestrator, "shutdown", _done)

    async def runner_shutdown():
        return next(shutdown_results)

    async def await_completion(job_id):
        await completed.wait()

    monkeypatch.setattr(app_module.runner, "shutdown", runner_shutdown)
    monkeypatch.setattr(app_module.runner, "await_job_completion", await_completion)
    monkeypatch.setattr(app_module, "cleanup_loop", lambda: _until_cancelled([], "maintenance"))
    monkeypatch.setattr(app_module, "_warmup_asr", lambda: _until_cancelled([], "warmup"))
    monkeypatch.setattr(app_module, "_backfill_tags", lambda: _until_cancelled([], "tags"))

    async def close_http():
        closed.append(True)

    monkeypatch.setattr(app_module, "aclose_all", close_http)

    async with app_module.lifespan(FastAPI()):
        await asyncio.sleep(0)
    old_cleanup = next(iter(app_module._deferred_http_close_tasks))

    async with app_module.lifespan(FastAPI()):
        await asyncio.sleep(0)

    new_cleanup = next(task for task in app_module._deferred_http_close_tasks if task is not old_cleanup)
    assert closed == []
    completed.set()
    await new_cleanup
    assert closed == [True]
    await old_cleanup
    assert closed == [True]


async def _done() -> None:
    return None


async def _until_cancelled(events: list[str], name: str) -> None:
    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        events.append(name)
        raise
