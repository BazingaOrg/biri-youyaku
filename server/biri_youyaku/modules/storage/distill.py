"""作者蒸馏语料包的目录 helpers：`data/distill/<mid>/`。

目录解析方式与 `storage/summary.py` 一致：纯 `settings` 驱动，不做别的推断。
布局：
  data/distill/<mid>/
    manifest.json      # assembler.py 写，断点续跑的运行时依据是 distill_runs 表 + 下面这些文件是否存在
    videos/<bvid>.md    # 单视频观点提取（frontmatter + 正文）
    dynamics.md         # 清洗后的动态时间线
    corpus.md           # 组装后的单文件语料包
"""

from __future__ import annotations

import json
from pathlib import Path

from biri_youyaku.config import settings


def run_dir(mid: int) -> Path:
    return Path(settings.distill_storage_dir) / str(mid)


def videos_dir(mid: int) -> Path:
    return run_dir(mid) / "videos"


def video_path(mid: int, bvid: str) -> Path:
    return videos_dir(mid) / f"{bvid}.md"


def dynamics_path(mid: int) -> Path:
    return run_dir(mid) / "dynamics.md"


def corpus_path(mid: int) -> Path:
    return run_dir(mid) / "corpus.md"


def manifest_path(mid: int) -> Path:
    return run_dir(mid) / "manifest.json"


def ensure_dirs(mid: int) -> None:
    videos_dir(mid).mkdir(parents=True, exist_ok=True)


def video_exists(mid: int, bvid: str) -> bool:
    return video_path(mid, bvid).exists()


def save_video(mid: int, bvid: str, content: str) -> Path:
    ensure_dirs(mid)
    path = video_path(mid, bvid)
    path.write_text(content, encoding="utf-8")
    return path


def read_video(mid: int, bvid: str) -> str | None:
    path = video_path(mid, bvid)
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def list_video_bvids(mid: int) -> list[str]:
    directory = videos_dir(mid)
    if not directory.exists():
        return []
    return sorted(path.stem for path in directory.glob("*.md"))


def save_dynamics(mid: int, content: str) -> Path:
    ensure_dirs(mid)
    path = dynamics_path(mid)
    path.write_text(content, encoding="utf-8")
    return path


def read_dynamics(mid: int) -> str | None:
    path = dynamics_path(mid)
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def save_corpus(mid: int, content: str) -> Path:
    ensure_dirs(mid)
    path = corpus_path(mid)
    path.write_text(content, encoding="utf-8")
    return path


def read_corpus(mid: int) -> str | None:
    path = corpus_path(mid)
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def save_manifest(mid: int, manifest: dict) -> Path:
    ensure_dirs(mid)
    path = manifest_path(mid)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def read_manifest(mid: int) -> dict | None:
    path = manifest_path(mid)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
