from biri_youyaku.distill import assembler
from biri_youyaku.distill.model import DistillRun, DistillRunStatus, default_counters
from biri_youyaku.modules.storage import distill as distill_storage


def _patch_storage_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(distill_storage.settings, "distill_storage_dir", tmp_path)


def _make_run(mid: int) -> DistillRun:
    counters = default_counters()
    counters["dynamics_count"] = 4
    return DistillRun(
        id="run-1",
        mid=mid,
        status=DistillRunStatus.ASSEMBLING,
        video_limit=50,
        dir_path=str(distill_storage.run_dir(mid)),
        created_at=0,
        updated_at=0,
        up_name="某UP",
        dynamics_status="ok",
        counters=counters,
    )


def test_build_manifest_fields(monkeypatch, tmp_path):
    _patch_storage_dir(monkeypatch, tmp_path)
    run = _make_run(1)
    videos = [
        {
            "bvid": "BV_A",
            "title": "视频A",
            "pubdate": 200,
            "duration": 60,
            "play": 10,
            "status": "extracted",
        },
        {
            "bvid": "BV_B",
            "title": "视频B",
            "pubdate": 100,
            "duration": 90,
            "play": 20,
            "status": "failed",
        },
    ]

    manifest = assembler.build_manifest(run, videos)

    assert manifest["mid"] == 1
    assert manifest["up_name"] == "某UP"
    assert manifest["video_limit"] == 50
    assert manifest["dynamics_status"] == "ok"
    assert manifest["dynamics_count"] == 4
    assert manifest["videos"]["total"] == 2
    assert manifest["videos"]["extracted"] == 1
    assert manifest["videos"]["failed"] == ["BV_B"]
    assert {item["bvid"] for item in manifest["videos"]["items"]} == {"BV_A", "BV_B"}
    assert manifest["date_range"] == {"from": 100, "to": 200}


def test_build_corpus_orders_by_pubdate_and_appends_dynamics(monkeypatch, tmp_path):
    _patch_storage_dir(monkeypatch, tmp_path)
    run = _make_run(2)
    distill_storage.save_video(2, "BV_NEW", "---\ntitle: 新\n---\n\n新视频正文")
    distill_storage.save_video(2, "BV_OLD", "---\ntitle: 旧\n---\n\n旧视频正文")
    distill_storage.save_dynamics(2, "- [2024-01-01][文字] 一条动态")

    videos = [
        {
            "bvid": "BV_NEW",
            "title": "新视频",
            "pubdate": 200,
            "duration": 60,
            "play": 10,
            "status": "extracted",
        },
        {
            "bvid": "BV_OLD",
            "title": "旧视频",
            "pubdate": 100,
            "duration": 90,
            "play": 20,
            "status": "extracted",
        },
    ]

    corpus = assembler.build_corpus(run, videos)

    old_pos = corpus.index("旧视频正文")
    new_pos = corpus.index("新视频正文")
    dynamics_pos = corpus.index("一条动态")
    assert old_pos < new_pos < dynamics_pos
    assert "# 动态时间线" in corpus


def test_assemble_writes_manifest_and_corpus_files(monkeypatch, tmp_path):
    _patch_storage_dir(monkeypatch, tmp_path)
    run = _make_run(3)
    distill_storage.save_video(3, "BV1", "---\ntitle: 只有一条\n---\n\n正文")
    videos = [
        {
            "bvid": "BV1",
            "title": "只有一条",
            "pubdate": 1,
            "duration": 1,
            "play": 1,
            "status": "extracted",
        },
    ]

    manifest, corpus = assembler.assemble(run, videos)

    assert distill_storage.read_manifest(3) == manifest
    assert distill_storage.read_corpus(3) == corpus
    assert "正文" in corpus


def test_build_corpus_skips_failed_videos(monkeypatch, tmp_path):
    _patch_storage_dir(monkeypatch, tmp_path)
    run = _make_run(4)
    videos = [
        {
            "bvid": "BV_FAIL",
            "title": "失败视频",
            "pubdate": 1,
            "duration": 1,
            "play": 1,
            "status": "failed",
        },
    ]

    corpus = assembler.build_corpus(run, videos)

    assert "失败视频" not in corpus.split("## 目录")[1]
