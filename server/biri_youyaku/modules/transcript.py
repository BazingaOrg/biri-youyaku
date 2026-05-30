"""项目级 transcript 领域类型。

`TranscriptItem` 原本住在 `modules/bilibili/subtitle.py`，但 asr / llm / 字幕上传
等多处都要用它，让它绑定在 bilibili 模块里是个倒灌的依赖方向。这里把它升到独立
模块，原路径继续 re-export 保持兼容。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TranscriptItem:
    start: float
    end: float
    text: str
