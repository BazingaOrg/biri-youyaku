import pytest
from fastapi import HTTPException

from biri_youyaku import db
from biri_youyaku.distill import repo as distill_repo
from biri_youyaku.distill.model import DistillRunStatus
from biri_youyaku.routes import distill as distill_route


def _init_db(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "distill.db")
    db.init_db()
    monkeypatch.setattr(
        distill_route.distill_storage.settings, "distill_storage_dir", tmp_path / "distill"
    )


@pytest.mark.asyncio
async def test_start_distill_success(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    created = distill_repo.create_run(1, video_limit=50, dir_path="d")

    async def fake_start_run(mid, video_limit=50):
        assert mid == 1
        assert video_limit == 20
        return created

    monkeypatch.setattr(distill_route.orchestrator, "start_run", fake_start_run)

    result = await distill_route.start_distill(
        None, 1, distill_route.StartDistillPayload(video_limit=20)
    )

    assert result["ok"] is True
    assert result["run"]["id"] == created.id


@pytest.mark.asyncio
async def test_start_distill_conflict_returns_409(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)

    async def fake_start_run(mid, video_limit=50):
        raise RuntimeError("已有进行中的蒸馏任务")

    monkeypatch.setattr(distill_route.orchestrator, "start_run", fake_start_run)

    with pytest.raises(HTTPException) as exc:
        await distill_route.start_distill(None, 1, distill_route.StartDistillPayload())
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_get_distill_status_and_404(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    run = distill_repo.create_run(1, video_limit=50, dir_path="d")

    result = await distill_route.get_distill(run.id)
    assert result["run"]["status"] == DistillRunStatus.PENDING.value

    with pytest.raises(HTTPException) as exc:
        await distill_route.get_distill("nope")
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_cancel_distill(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    run = distill_repo.create_run(1, video_limit=50, dir_path="d")

    calls = []
    monkeypatch.setattr(
        distill_route.orchestrator, "cancel_run", lambda run_id: calls.append(run_id)
    )

    result = await distill_route.cancel_distill(run.id)

    assert result["ok"] is True
    assert calls == [run.id]

    with pytest.raises(HTTPException) as exc:
        await distill_route.cancel_distill("nope")
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_corpus_404_then_200(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    run = distill_repo.create_run(5, video_limit=50, dir_path="d")

    with pytest.raises(HTTPException) as exc:
        await distill_route.get_distill_corpus(run.id)
    assert exc.value.status_code == 404

    distill_route.distill_storage.save_corpus(5, "# 语料内容")
    result = await distill_route.get_distill_corpus(run.id)

    assert result["ok"] is True
    assert result["corpus"] == "# 语料内容"


@pytest.mark.asyncio
async def test_latest_distill_returns_most_recent_or_none(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)

    empty = await distill_route.get_latest_distill(999)
    assert empty["run"] is None

    run = distill_repo.create_run(1, video_limit=50, dir_path="d")
    result = await distill_route.get_latest_distill(1)

    assert result["run"]["id"] == run.id


@pytest.mark.asyncio
async def test_delete_distill_removes_records_and_dir(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    run = distill_repo.create_run(7, video_limit=50, dir_path="d")
    distill_repo.update_status(run.id, DistillRunStatus.COMPLETED)
    distill_route.distill_storage.save_corpus(7, "# 语料内容")
    run_dir = distill_route.distill_storage.run_dir(7)
    assert run_dir.exists()

    result = await distill_route.delete_distill(7)

    assert result["ok"] is True
    assert distill_repo.list_runs_by_mid(7) == []
    assert not run_dir.exists()


@pytest.mark.asyncio
async def test_delete_distill_conflict_when_running(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    distill_repo.create_run(8, video_limit=50, dir_path="d")  # 默认 PENDING（非终态）

    with pytest.raises(HTTPException) as exc:
        await distill_route.delete_distill(8)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_delete_distill_idempotent_when_no_run(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)

    result = await distill_route.delete_distill(999)

    assert result["ok"] is True
