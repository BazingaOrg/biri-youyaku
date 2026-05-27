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
