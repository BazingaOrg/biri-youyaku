"""生成 distill run 的最终产物：

- `manifest.json`：作者信息、参数、数量、时间范围、per-video 状态、failed 列表、
  dynamics_status——断点续跑的「人可读」快照（运行时续跑实际依据见
  `orchestrator.py` 模块docstring：`distill_runs` 表行 + 文件是否存在）。
- `corpus.md`：作者概览 + 目录，然后按发布时间升序拼所有 `videos/<bvid>.md` 全文，
  末尾附 `dynamics.md` 全文。只组装，不做有损压缩——压缩是项目外蒸馏阶段的职责。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from biri_youyaku.distill.model import DistillRun
from biri_youyaku.jobs.repo import now_ms
from biri_youyaku.modules.storage import distill as distill_storage


def _format_ts(ts: int | None) -> str:
    if not ts:
        return "未知日期"
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().strftime("%Y-%m-%d")


def build_manifest(run: DistillRun, videos: list[dict[str, Any]]) -> dict[str, Any]:
    extracted = [video for video in videos if video["status"] == "extracted"]
    failed = [video["bvid"] for video in videos if video["status"] == "failed"]
    pubdates = [video["pubdate"] for video in videos if video.get("pubdate")]

    return {
        "mid": run.mid,
        "up_name": run.up_name,
        "video_limit": run.video_limit,
        "generated_at": now_ms(),
        "dynamics_status": run.dynamics_status,
        "dynamics_count": run.counters.get("dynamics_count", 0),
        "videos": {
            "total": len(videos),
            "extracted": len(extracted),
            "failed": failed,
            "items": [
                {
                    "bvid": video["bvid"],
                    "title": video.get("title"),
                    "pubdate": video.get("pubdate"),
                    "duration": video.get("duration"),
                    "play": video.get("play"),
                    "status": video["status"],
                }
                for video in videos
            ],
        },
        "date_range": {
            "from": min(pubdates) if pubdates else None,
            "to": max(pubdates) if pubdates else None,
        },
    }


def build_corpus(run: DistillRun, videos: list[dict[str, Any]]) -> str:
    extracted = sorted(
        (video for video in videos if video["status"] == "extracted"),
        key=lambda video: video.get("pubdate") or 0,
    )

    lines: list[str] = [
        f"# {run.up_name or run.mid} 蒸馏语料包",
        "",
        f"- mid: {run.mid}",
        f"- 视频数：{len(extracted)}/{len(videos)}（成功提取/总数）",
        f"- 动态状态：{run.dynamics_status or '未抓取'}",
        "",
        "## 目录",
    ]
    for video in extracted:
        title = video.get("title") or video["bvid"]
        lines.append(f"- [{_format_ts(video.get('pubdate'))}] {title}（{video['bvid']}）")
    lines.append("")

    for video in extracted:
        body = distill_storage.read_video(run.mid, video["bvid"]) or ""
        lines.append("---")
        lines.append(body.rstrip())
        lines.append("")

    dynamics_body = distill_storage.read_dynamics(run.mid)
    if dynamics_body:
        lines.append("---")
        lines.append("# 动态时间线")
        lines.append("")
        lines.append(dynamics_body.rstrip())
        lines.append("")

    return "\n".join(lines)


def assemble(run: DistillRun, videos: list[dict[str, Any]]) -> tuple[dict[str, Any], str]:
    manifest = build_manifest(run, videos)
    distill_storage.save_manifest(run.mid, manifest)
    corpus = build_corpus(run, videos)
    distill_storage.save_corpus(run.mid, corpus)
    return manifest, corpus
