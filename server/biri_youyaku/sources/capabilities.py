from importlib.util import find_spec
import shutil

from biri_youyaku.config import settings
from biri_youyaku.sources.uploads import ALLOWED_SUFFIXES


def _installed(module: str) -> bool:
    try:
        return find_spec(module) is not None
    except (ImportError, ValueError, ModuleNotFoundError):
        return False


def capabilities() -> dict:
    model = settings.asr_model.lower()
    modules = {
        "sensevoice": ("funasr",),
        "sensevoice-mlx": ("mlx_audio",),
        "sensevoice_mlx": ("mlx_audio",),
        "mlx-sensevoice": ("mlx_audio",),
        "parakeet-mlx": ("parakeet_mlx",),
        "parakeet_mlx": ("parakeet_mlx",),
        "parakeet": ("parakeet_mlx",),
        "faster-whisper": ("faster_whisper",),
        "auto": ("mlx_audio", "funasr"),
    }
    return {
        "providers": ["bilibili", "youtube", "upload"],
        "upload": {"max_bytes": settings.upload_max_bytes, "extensions": sorted(ALLOWED_SUFFIXES)},
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "ffprobe": shutil.which("ffprobe") is not None,
        "asr": {
            "installed": any(_installed(m) for m in modules.get(model, ("funasr",))),
            "model": settings.asr_model,
        },
        "youtube": _installed("yt_dlp"),
    }
