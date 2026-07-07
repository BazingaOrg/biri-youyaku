from biri_youyaku import db
from biri_youyaku.distill import repo as distill_repo
from biri_youyaku.distill.model import DistillRunStatus


def _init_db(monkeypatch, tmp_path):
    monkeypatch.setattr(db.settings, "db_path", tmp_path / "distill.db")
    db.init_db()


def test_create_run_persists_defaults(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)

    run = distill_repo.create_run(123, video_limit=50, dir_path="data/distill/123")

    loaded = distill_repo.get_run(run.id)
    assert loaded is not None
    assert loaded.mid == 123
    assert loaded.status == DistillRunStatus.PENDING
    assert loaded.video_limit == 50
    assert loaded.dir_path == "data/distill/123"
    assert loaded.counters["videos_total"] == 0
    assert loaded.counters["failed_bvids"] == []
    assert loaded.up_name is None
    assert loaded.dynamics_status is None


def test_find_active_by_mid_ignores_terminal_runs(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)

    run = distill_repo.create_run(1, video_limit=50, dir_path="d")
    assert distill_repo.find_active_by_mid(1) is not None

    distill_repo.update_status(run.id, DistillRunStatus.COMPLETED)
    assert distill_repo.find_active_by_mid(1) is None


def test_status_transitions_and_error(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    run = distill_repo.create_run(1, video_limit=50, dir_path="d")

    distill_repo.update_status(run.id, DistillRunStatus.FETCHING_DYNAMICS)
    assert distill_repo.get_run(run.id).status == DistillRunStatus.FETCHING_DYNAMICS

    distill_repo.update_status(run.id, DistillRunStatus.FAILED, error="boom")
    loaded = distill_repo.get_run(run.id)
    assert loaded.status == DistillRunStatus.FAILED
    assert loaded.error == "boom"


def test_update_counters_merges_partial_updates(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    run = distill_repo.create_run(1, video_limit=50, dir_path="d")

    distill_repo.update_counters(run.id, videos_total=10)
    distill_repo.update_counters(run.id, videos_transcribed=3)

    loaded = distill_repo.get_run(run.id)
    assert loaded.counters["videos_total"] == 10
    assert loaded.counters["videos_transcribed"] == 3


def test_add_failed_bvid_dedupes_and_updates_count(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    run = distill_repo.create_run(1, video_limit=50, dir_path="d")

    distill_repo.add_failed_bvid(run.id, "BV1")
    distill_repo.add_failed_bvid(run.id, "BV1")
    distill_repo.add_failed_bvid(run.id, "BV2")

    loaded = distill_repo.get_run(run.id)
    assert loaded.counters["failed_bvids"] == ["BV1", "BV2"]
    assert loaded.counters["videos_failed"] == 2


def test_set_up_name_and_dynamics_status(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    run = distill_repo.create_run(1, video_limit=50, dir_path="d")

    distill_repo.set_up_name(run.id, "某UP")
    distill_repo.set_dynamics_status(run.id, "unavailable")

    loaded = distill_repo.get_run(run.id)
    assert loaded.up_name == "某UP"
    assert loaded.dynamics_status == "unavailable"


def test_list_unfinished_runs_excludes_terminal(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    running = distill_repo.create_run(1, video_limit=50, dir_path="d1")
    done = distill_repo.create_run(2, video_limit=50, dir_path="d2")
    distill_repo.update_status(done.id, DistillRunStatus.COMPLETED)

    unfinished = distill_repo.list_unfinished_runs()

    assert [run.id for run in unfinished] == [running.id]


def test_latest_by_mid_returns_most_recent(monkeypatch, tmp_path):
    _init_db(monkeypatch, tmp_path)
    # now_ms() 用真实时钟，两次快速 create_run 可能落在同一毫秒——用固定递增值消除
    # 排序平局，让测试确定性地断言"更晚创建的"排在前面。
    clock = iter([1000, 2000, 3000])
    monkeypatch.setattr(distill_repo, "now_ms", lambda: next(clock))

    first = distill_repo.create_run(1, video_limit=50, dir_path="d1")
    distill_repo.update_status(first.id, DistillRunStatus.COMPLETED)
    second = distill_repo.create_run(1, video_limit=50, dir_path="d2")

    latest = distill_repo.latest_by_mid(1)

    assert latest is not None
    assert latest.id == second.id
