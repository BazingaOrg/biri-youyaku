import pytest

from biri_youyaku import db
from biri_youyaku.jobs import repo, tags_backfill
from biri_youyaku.jobs.model import JobOptions, JobStatus
from biri_youyaku.modules.llm import client


def test_parse_tags_dedupes_and_caps():
    out = client._parse_tags("机器学习、机器学习, 深度学习\n1. 强化学习；CV/NLP、这个标签太长了肯定超过十二个字啊啊")
    assert out[:4] == ["机器学习", "深度学习", "强化学习", "CV"]
    assert "NLP" in out
    assert len(out) <= 6
    assert all(len(t) <= 12 for t in out)


@pytest.mark.asyncio
async def test_generate_tags_empty_without_key(monkeypatch):
    monkeypatch.setattr(client.settings, "llm_api_key", "")
    assert await client.generate_tags("一些笔记", JobOptions()) == []


@pytest.mark.asyncio
async def test_generate_tags_parses_completion(monkeypatch):
    monkeypatch.setattr(client.settings, "llm_api_key", "key")

    async def fake_complete(*args, **kwargs):
        return "投资、估值、护城河"

    monkeypatch.setattr(client, "_complete", fake_complete)
    monkeypatch.setattr(client, "openai_client", lambda **kw: object())

    assert await client.generate_tags("一些笔记", JobOptions()) == ["投资", "估值", "护城河"]


@pytest.mark.asyncio
async def test_backfill_sets_tags_and_skips_processed(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    monkeypatch.setattr(tags_backfill.settings, "llm_api_key", "key")
    db.init_db()

    job = repo.create_job("https://www.bilibili.com/video/BV1", JobOptions())
    summary_path = tmp_path / f"{job.id}.md"
    summary_path.write_text("# 笔记", encoding="utf-8")
    repo.set_summary_path(job.id, str(summary_path))
    repo.update_status(job.id, JobStatus.COMPLETED)

    async def fake_generate_tags(summary, options, *, raise_on_error=False):
        return ["A", "B"]

    monkeypatch.setattr(tags_backfill.llm_client, "generate_tags", fake_generate_tags)

    assert await tags_backfill.backfill_missing_tags(delay_seconds=0) == 1
    assert repo.get_job(job.id).tags == ["A", "B"]
    # 已有标签 → 第二次不再处理
    assert await tags_backfill.backfill_missing_tags(delay_seconds=0) == 0
