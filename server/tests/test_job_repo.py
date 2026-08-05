import pytest
from fastapi import HTTPException

from biri_youyaku import db
from biri_youyaku.jobs import repo
from biri_youyaku.jobs.model import JobOptions, JobStatus
from biri_youyaku.modules.bilibili.meta import Chapter
from biri_youyaku.modules.bilibili.subtitle import TranscriptItem
from biri_youyaku.routes import jobs as jobs_route


def test_create_job_persists_overrides_and_effective_options(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    db.init_db()

    job = repo.create_job(
        "https://www.bilibili.com/video/BV123",
        JobOptions(llm_model="model-b", email_enabled=False),
        option_overrides={"llm_model": "model-b", "email_enabled": False},
    )
    loaded = repo.get_job(job.id)

    assert loaded is not None
    assert loaded.option_overrides == {"llm_model": "model-b", "email_enabled": False}
    assert loaded.options.llm_model == "model-b"
    assert loaded.options.email_enabled is False


def test_repo_persists_chapters_and_transcript(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    db.init_db()
    job = repo.create_job("https://www.bilibili.com/video/BV123", JobOptions())

    repo.set_chapters(job.id, [Chapter(start=1, end=5, title="Intro")])
    repo.set_transcript(job.id, [TranscriptItem(start=1, end=2, text="hello")])
    loaded = repo.get_job(job.id)

    assert loaded is not None
    assert loaded.chapters == [{"start": 1, "end": 5, "title": "Intro"}]
    assert loaded.transcript == [{"start": 1, "end": 2, "text": "hello"}]


def test_create_resummary_job_reuses_transcript_and_meta(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    db.init_db()
    source = repo.create_job("https://www.bilibili.com/video/BV123", JobOptions(email_enabled=False))
    repo.update_meta(source.id, bvid="BV123", cid=7, title="Title", author="UP", duration=12.0, mid=42)
    repo.set_subtitle_source(source.id, "platform")
    repo.set_chapters(source.id, [Chapter(start=1, end=5, title="Intro")])
    repo.set_transcript(source.id, [TranscriptItem(start=1, end=2, text="hello")])
    source = repo.get_job(source.id)

    created = repo.create_resummary_job(
        source,
        JobOptions(llm_model="model-b", email_enabled=False),
        option_overrides={"llm_model": "model-b", "email_enabled": False},
    )

    assert created.id != source.id
    assert created.status == JobStatus.TRANSCRIPT_READY
    assert created.url == source.url
    assert created.bvid == "BV123"
    assert created.cid == 7
    assert created.mid == 42
    assert created.title == "Title"
    assert created.author == "UP"
    assert created.duration == 12.0
    assert created.subtitle_source == "platform"
    assert created.chapters == [{"start": 1, "end": 5, "title": "Intro"}]
    assert created.transcript == [{"start": 1, "end": 2, "text": "hello"}]
    assert created.option_overrides == {"llm_model": "model-b", "email_enabled": False}
    assert created.options.llm_model == "model-b"


def test_delete_job_removes_row(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    db.init_db()
    job = repo.create_job("https://www.bilibili.com/video/BV123", JobOptions())

    assert repo.delete_job(job.id) == 1
    assert repo.get_job(job.id) is None


def test_delete_jobs_by_status_removes_only_matching_rows(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    db.init_db()
    done = repo.create_job("https://www.bilibili.com/video/BVdone", JobOptions())
    active = repo.create_job("https://www.bilibili.com/video/BVactive", JobOptions())
    repo.update_status(done.id, JobStatus.COMPLETED)
    repo.update_status(active.id, JobStatus.SUMMARIZING)

    skipped = repo.count_jobs_excluding_status({JobStatus.COMPLETED})
    deleted = repo.delete_jobs_by_status({JobStatus.COMPLETED})

    assert skipped == 1
    assert deleted == 1
    assert repo.get_job(done.id) is None
    assert repo.get_job(active.id) is not None


def test_list_jobs_by_status_returns_matching_rows(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    db.init_db()
    done = repo.create_job("https://www.bilibili.com/video/BVdone", JobOptions())
    active = repo.create_job("https://www.bilibili.com/video/BVactive", JobOptions())
    repo.update_status(done.id, JobStatus.COMPLETED)
    repo.update_status(active.id, JobStatus.SUMMARIZING)

    jobs = repo.list_jobs_by_status({JobStatus.COMPLETED})

    assert [job.id for job in jobs] == [done.id]


def test_list_jobs_supports_created_at_cursor(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    db.init_db()
    first = repo.create_job("https://www.bilibili.com/video/BVfirst", JobOptions())
    second = repo.create_job("https://www.bilibili.com/video/BVsecond", JobOptions())
    with db.connect() as connection:
        connection.execute(
            "UPDATE jobs SET created_at = ?, status = ? WHERE id = ?",
            (100, JobStatus.COMPLETED.value, first.id),
        )
        connection.execute(
            "UPDATE jobs SET created_at = ?, status = ? WHERE id = ?",
            (200, JobStatus.COMPLETED.value, second.id),
        )

    jobs = repo.list_jobs(limit=10, cursor=200)

    assert [job.id for job in jobs] == [first.id]


def test_history_pagination_filters_and_composite_cursor_do_not_skip_same_millisecond(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    db.init_db()
    matching = [
        repo.create_job(f"https://www.bilibili.com/video/BVmatch{index}", JobOptions())
        for index in range(3)
    ]
    unrelated = repo.create_job("https://www.bilibili.com/video/BVother", JobOptions())
    unknown = repo.create_job("https://www.bilibili.com/video/BVunknown", JobOptions())
    distill = repo.create_job(
        "https://www.bilibili.com/video/BVdistill", JobOptions(task_type="distill")
    )
    for index, job in enumerate(matching):
        repo.update_meta(
            job.id,
            bvid=f"BVmatch{index}",
            cid=None,
            title=f"AI review {index}",
            author="Alice",
            duration=1,
        )
        repo.set_tags(job.id, ["技术"])
    repo.update_meta(
        unrelated.id, bvid="BVother", cid=None, title="Other", author="Bob", duration=1
    )
    repo.update_meta(
        unknown.id, bvid="BVunknown", cid=None, title="Unknown", author="", duration=1
    )
    repo.update_meta(
        distill.id, bvid="BVdistill", cid=None, title="AI hidden", author="Alice", duration=1
    )
    with db.connect() as connection:
        for job in [*matching, unrelated, unknown, distill]:
            connection.execute(
                "UPDATE jobs SET created_at = ?, status = ? WHERE id = ?",
                (100, JobStatus.COMPLETED.value, job.id),
            )

    first_page = repo.list_jobs(
        limit=2, query="ai", author="Alice", tag="技术", terminal_only=True
    )
    second_page = repo.list_jobs(
        limit=2,
        cursor=repo.encode_history_cursor(first_page[-1]),
        query="ai",
        author="Alice",
        tag="技术",
        terminal_only=True,
    )

    assert {job.id for job in [*first_page, *second_page]} == {job.id for job in matching}
    assert [job.id for job in repo.list_jobs(limit=10, author="未知 UP")] == [unknown.id]


def test_history_pagination_uses_completion_time_before_creation_time(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    db.init_db()
    old_but_just_completed = repo.create_job("https://www.bilibili.com/video/BVold", JobOptions())
    recent_completed = repo.create_job("https://www.bilibili.com/video/BVrecent", JobOptions())
    older_completed = repo.create_job("https://www.bilibili.com/video/BVolder", JobOptions())
    with db.connect() as connection:
        connection.execute(
            "UPDATE jobs SET created_at = ?, completed_at = ?, status = ? WHERE id = ?",
            (10, 1_000, JobStatus.COMPLETED.value, old_but_just_completed.id),
        )
        connection.execute(
            "UPDATE jobs SET created_at = ?, completed_at = ?, status = ? WHERE id = ?",
            (900, 900, JobStatus.COMPLETED.value, recent_completed.id),
        )
        connection.execute(
            "UPDATE jobs SET created_at = ?, completed_at = ?, status = ? WHERE id = ?",
            (800, 800, JobStatus.COMPLETED.value, older_completed.id),
        )

    first_page = repo.list_jobs(limit=2, terminal_only=True)
    second_page = repo.list_jobs(
        limit=2,
        cursor=repo.encode_history_cursor(first_page[-1], terminal_only=True),
        terminal_only=True,
    )

    assert [job.id for job in first_page] == [old_but_just_completed.id, recent_completed.id]
    assert [job.id for job in second_page] == [older_completed.id]


def test_legacy_numeric_cursor_keeps_created_at_semantics_after_completion(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    db.init_db()
    older = repo.create_job("https://www.bilibili.com/video/BVolder", JobOptions())
    newer = repo.create_job("https://www.bilibili.com/video/BVnewer", JobOptions())
    with db.connect() as connection:
        connection.execute(
            "UPDATE jobs SET created_at = ?, completed_at = ?, status = ? WHERE id = ?",
            (100, 9_000, JobStatus.COMPLETED.value, older.id),
        )
        connection.execute(
            "UPDATE jobs SET created_at = ?, completed_at = ?, status = ? WHERE id = ?",
            (200, 300, JobStatus.COMPLETED.value, newer.id),
        )

    legacy_page = repo.list_jobs(limit=10, cursor=200)

    assert [job.id for job in legacy_page] == [older.id]


def test_history_active_scope_is_complete_and_excluded_from_terminal_pages(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    db.init_db()
    active = repo.create_job("https://www.bilibili.com/video/BVactive", JobOptions())
    paused = repo.create_job("https://www.bilibili.com/video/BVpaused", JobOptions())
    completed = repo.create_job("https://www.bilibili.com/video/BVcompleted", JobOptions())
    distill = repo.create_job(
        "https://www.bilibili.com/video/BVdistill", JobOptions(task_type="distill")
    )
    repo.update_status(paused.id, JobStatus.TRANSCRIPT_READY)
    repo.update_status(completed.id, JobStatus.COMPLETED)

    active_jobs = repo.list_jobs(active_only=True)
    terminal_jobs = repo.list_jobs(limit=10, terminal_only=True)

    assert {job.id for job in active_jobs} == {active.id, paused.id}
    assert [job.id for job in terminal_jobs] == [completed.id]
    assert distill.id not in {job.id for job in [*active_jobs, *terminal_jobs]}


@pytest.mark.asyncio
async def test_list_jobs_scope_cursor_response_contract(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    db.init_db()
    job = repo.create_job("https://www.bilibili.com/video/BV1", JobOptions())
    repo.update_status(job.id, JobStatus.COMPLETED)
    # terminal_only cursor uses completed_at; re-read after status update.
    job = repo.get_job(job.id)
    assert job is not None

    legacy = await jobs_route.list_jobs(
        limit=1,
        offset=0,
        cursor=None,
        query=None,
        author=None,
        tag=None,
        active_only=False,
        terminal_only=False,
    )
    terminal = await jobs_route.list_jobs(
        limit=1,
        offset=0,
        cursor=None,
        query=None,
        author=None,
        tag=None,
        active_only=False,
        terminal_only=True,
    )
    with pytest.raises(HTTPException, match="不能同时使用") as exc_info:
        await jobs_route.list_jobs(
            limit=50,
            offset=0,
            cursor=None,
            query=None,
            author=None,
            tag=None,
            active_only=True,
            terminal_only=True,
        )

    assert legacy["next_cursor"] == job.created_at
    assert terminal["next_cursor"] == repo.encode_history_cursor(job, terminal_only=True)
    assert exc_info.value.status_code == 422


def test_stage_timings_and_token_usage_are_persisted(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    db.init_db()
    job = repo.create_job("https://www.bilibili.com/video/BV123", JobOptions())

    repo.add_stage_timing(job.id, "FETCHING_META", 100, 160)
    repo.add_token_usage(job.id, {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15})
    repo.add_token_usage(job.id, {"input_tokens": 2, "output_tokens": 3, "total_tokens": 5})
    loaded = repo.get_job(job.id)

    assert loaded.stage_timings == [
        {"stage": "FETCHING_META", "started_at": 100, "ended_at": 160, "duration_ms": 60}
    ]
    assert loaded.token_usage == {
        "input_tokens": 12,
        "output_tokens": 8,
        "total_tokens": 20,
        "cost_estimate": None,
    }


def test_find_completed_by_bvid_returns_latest_completed(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    db.init_db()

    def make(bvid: str, status: JobStatus):
        job = repo.create_job(f"https://www.bilibili.com/video/{bvid}", JobOptions())
        repo.update_meta(job.id, bvid=bvid, cid=None, title="T", author="UP", duration=1.0)
        repo.update_status(job.id, status)
        return job

    # BV1：先失败再完成 → 命中已完成那条
    make("BV1", JobStatus.FAILED)
    done = make("BV1", JobStatus.COMPLETED)
    # BV2：只有进行中 → 不算命中
    make("BV2", JobStatus.SUMMARIZING)

    assert repo.find_completed_by_bvid("BV1").id == done.id
    assert repo.find_completed_by_bvid("BV2") is None
    assert repo.find_completed_by_bvid("BVnone") is None
    assert repo.find_completed_by_bvid("") is None


def test_list_jobs_by_status_before_filters_by_updated_at(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    db.init_db()
    old = repo.create_job("https://www.bilibili.com/video/BVold", JobOptions())
    new = repo.create_job("https://www.bilibili.com/video/BVnew", JobOptions())
    repo.update_status(old.id, JobStatus.COMPLETED)
    repo.update_status(new.id, JobStatus.COMPLETED)
    with db.connect() as connection:
        connection.execute(
            "UPDATE jobs SET updated_at = ? WHERE id = ?",
            (repo.now_ms() - 10_000, old.id),
        )

    cutoff = repo.get_job(new.id).updated_at
    jobs = repo.list_jobs_by_status_before({JobStatus.COMPLETED}, cutoff)

    assert [job.id for job in jobs] == [old.id]


def test_update_meta_persists_mid(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    db.init_db()
    job = repo.create_job("https://www.bilibili.com/video/BV123", JobOptions())

    repo.update_meta(job.id, bvid="BV123", cid=1, title="T", author="UP", duration=12.0, mid=42)
    loaded = repo.get_job(job.id)

    assert loaded is not None
    assert loaded.mid == 42


def test_summary_status_for_bvids_prefers_completed(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    db.init_db()

    def make(bvid: str, status: JobStatus):
        job = repo.create_job(f"https://www.bilibili.com/video/{bvid}", JobOptions())
        repo.update_meta(job.id, bvid=bvid, cid=None, title="T", author="UP", duration=1.0, mid=1)
        repo.update_status(job.id, status)
        return job

    # BV1：先失败再完成 → 应取 COMPLETED 那条
    failed = make("BV1", JobStatus.FAILED)
    completed = make("BV1", JobStatus.COMPLETED)
    # BV2：只有进行中
    running = make("BV2", JobStatus.SUMMARIZING)

    result = repo.summary_status_for_bvids(["BV1", "BV2", "BVnone"])

    assert result["BV1"] == {"status": "COMPLETED", "job_id": completed.id}
    assert result["BV2"] == {"status": "SUMMARIZING", "job_id": running.id}
    assert "BVnone" not in result
    assert failed.id != completed.id  # sanity


def test_update_meta_backfills_mid_for_same_author(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    db.init_db()

    # 老任务：有 author、没有 mid（模拟 mid 列上线前建的）。
    old = repo.create_job("https://www.bilibili.com/video/BVold", JobOptions())
    repo.update_meta(old.id, bvid="BVold", cid=None, title="旧", author="老番茄", duration=1.0)
    assert repo.get_job(old.id).mid is None  # 这次没传 mid

    # 另一作者的老任务，不应被误伤。
    other = repo.create_job("https://www.bilibili.com/video/BVx", JobOptions())
    repo.update_meta(other.id, bvid="BVx", cid=None, title="别人", author="别的UP", duration=1.0)

    # 新任务带上了同作者的 mid → 触发回填。
    fresh = repo.create_job("https://www.bilibili.com/video/BVnew", JobOptions())
    repo.update_meta(fresh.id, bvid="BVnew", cid=None, title="新", author="老番茄", duration=1.0, mid=546195)

    assert repo.get_job(old.id).mid == 546195   # 老任务被补上
    assert repo.get_job(fresh.id).mid == 546195
    assert repo.get_job(other.id).mid is None    # 不同作者不动
