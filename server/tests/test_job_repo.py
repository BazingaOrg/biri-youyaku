from biri_youyaku import db
from biri_youyaku.jobs import repo
from biri_youyaku.jobs.model import JobOptions, JobStatus
from biri_youyaku.modules.bilibili.meta import Chapter
from biri_youyaku.modules.bilibili.subtitle import TranscriptItem


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
        connection.execute("UPDATE jobs SET created_at = ? WHERE id = ?", (100, first.id))
        connection.execute("UPDATE jobs SET created_at = ? WHERE id = ?", (200, second.id))

    jobs = repo.list_jobs(limit=10, cursor=200)

    assert [job.id for job in jobs] == [first.id]


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


def test_usage_since_sums_completed_jobs(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "jobs.db")
    db.init_db()
    done = repo.create_job("https://www.bilibili.com/video/BVdone", JobOptions())
    old = repo.create_job("https://www.bilibili.com/video/BVold", JobOptions())
    active = repo.create_job("https://www.bilibili.com/video/BVactive", JobOptions())
    repo.add_token_usage(done.id, {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15})
    repo.add_token_usage(old.id, {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150})
    repo.add_token_usage(active.id, {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2})
    repo.update_status(done.id, JobStatus.COMPLETED)
    repo.update_status(old.id, JobStatus.COMPLETED)
    repo.update_status(active.id, JobStatus.SUMMARIZING)
    with db.connect() as connection:
        connection.execute("UPDATE jobs SET completed_at = ? WHERE id = ?", (100, old.id))
        connection.execute("UPDATE jobs SET completed_at = ? WHERE id = ?", (1000, done.id))

    usage = repo.usage_since(500)

    assert usage == {
        "jobs_count": 1,
        "input_tokens": 10,
        "output_tokens": 5,
        "total_tokens": 15,
        "cost_estimate": None,
    }


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
