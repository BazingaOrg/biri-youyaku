"""作者蒸馏语料包的目录 helpers：`data/distill/<mid>/`。

目录解析方式与 `storage/summary.py` 一致：纯 `settings` 驱动，不做别的推断。
布局：
  data/distill/<mid>/
    manifest.json      # assembler.py 写，断点续跑的运行时依据是 distill_runs 表 + 下面这些文件是否存在
    videos/<bvid>.md    # 单视频观点提取（frontmatter + 正文）
    corpus.md           # 组装后的单文件语料包（video-only）
  （遗留 dynamics.md 若存在则保留，本模块不再读写。）
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from biri_youyaku.config import settings


def run_dir(mid: int) -> Path:
    return Path(settings.distill_storage_dir) / str(mid)


def videos_dir(mid: int) -> Path:
    return run_dir(mid) / "videos"


def video_path(mid: int, bvid: str) -> Path:
    return videos_dir(mid) / f"{bvid}.md"


def corpus_path(mid: int) -> Path:
    return run_dir(mid) / "corpus.md"


def manifest_path(mid: int) -> Path:
    return run_dir(mid) / "manifest.json"


def ensure_dirs(mid: int) -> None:
    videos_dir(mid).mkdir(parents=True, exist_ok=True)


def _atomic_write_text(path: Path, content: str) -> None:
    """写入同目录临时文件后原子替换，避免中断时破坏已有语料。"""
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as file:
            temp_path = Path(file.name)
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_path, path)
    except Exception:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise


def video_exists(mid: int, bvid: str) -> bool:
    return video_path(mid, bvid).exists()


def save_video(mid: int, bvid: str, content: str) -> Path:
    ensure_dirs(mid)
    path = video_path(mid, bvid)
    _atomic_write_text(path, content)
    return path


def read_video(mid: int, bvid: str) -> str | None:
    path = video_path(mid, bvid)
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def save_corpus(mid: int, content: str) -> Path:
    ensure_dirs(mid)
    path = corpus_path(mid)
    _atomic_write_text(path, content)
    return path


def read_corpus(mid: int) -> str | None:
    path = corpus_path(mid)
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def save_manifest(mid: int, manifest: dict) -> Path:
    ensure_dirs(mid)
    path = manifest_path(mid)
    _atomic_write_text(path, json.dumps(manifest, ensure_ascii=False, indent=2))
    return path


def read_manifest(mid: int) -> dict | None:
    path = manifest_path(mid)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
