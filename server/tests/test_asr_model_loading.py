import threading
from collections.abc import Callable
from types import ModuleType
from typing import Any

import pytest

from biri_youyaku.modules._cache import singleflight_singleton


def test_singleflight_singleton_constructs_once_for_concurrent_callers() -> None:
    started = threading.Event()
    release = threading.Event()
    constructed: list[object] = []

    @singleflight_singleton
    def load() -> object:
        constructed.append(object())
        started.set()
        assert release.wait(timeout=1)
        return constructed[0]

    results: list[object] = []
    first = threading.Thread(target=lambda: results.append(load()))
    second = threading.Thread(target=lambda: results.append(load()))
    first.start()
    assert started.wait(timeout=1)
    second.start()
    release.set()
    first.join(timeout=1)
    second.join(timeout=1)

    assert not first.is_alive()
    assert not second.is_alive()
    assert len(constructed) == 1
    assert results == [constructed[0], constructed[0]]


def test_singleflight_singleton_does_not_cache_exceptions() -> None:
    calls = 0

    @singleflight_singleton
    def load() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("temporary load failure")
        return "model"

    with pytest.raises(RuntimeError, match="temporary load failure"):
        load()

    assert load() == "model"
    assert calls == 2
    load.cache_clear()  # type: ignore[attr-defined]
    assert load() == "model"
    assert calls == 3


class _ConcurrentModel:
    def __init__(self, method: str) -> None:
        self.method = method
        self.first_started = threading.Event()
        self.second_started = threading.Event()
        self.release = threading.Event()
        self.calls = 0
        self.lock = threading.Lock()

    def _infer(self, *_args: Any, **_kwargs: Any) -> Any:
        with self.lock:
            self.calls += 1
            started = self.first_started if self.calls == 1 else self.second_started
        started.set()
        assert self.release.wait(timeout=1)
        if self.method == "transcribe":
            return [], object()
        return []

    def transcribe(self, *args: Any, **kwargs: Any) -> Any:
        return self._infer(*args, **kwargs)

    def generate(self, *args: Any, **kwargs: Any) -> Any:
        return self._infer(*args, **kwargs)


@pytest.mark.parametrize(
    ("module_name", "helper_name", "args", "method"),
    [
        ("whisper", "_run_sync", ("audio.wav", None), "transcribe"),
        ("sensevoice", "_generate_sync", ("audio.wav", "zh"), "generate"),
        ("sensevoice_mlx", "_generate_sync", ("audio.wav", "zh"), "generate"),
        ("parakeet_mlx", "_transcribe_sync", ("audio.wav",), "transcribe"),
    ],
)
def test_asr_inference_is_not_serialized_by_model_loading_lock(
    monkeypatch: pytest.MonkeyPatch,
    module_name: str,
    helper_name: str,
    args: tuple[Any, ...],
    method: str,
) -> None:
    module = __import__(f"biri_youyaku.modules.asr.{module_name}", fromlist=[helper_name])
    assert isinstance(module, ModuleType)
    model = _ConcurrentModel(method)

    @singleflight_singleton
    def load() -> _ConcurrentModel:
        return model

    monkeypatch.setattr(module, "_load_model", load)
    helper: Callable[..., Any] = getattr(module, helper_name)

    first = threading.Thread(target=lambda: helper(*args))
    second = threading.Thread(target=lambda: helper(*args))
    first.start()
    assert model.first_started.wait(timeout=1)
    second.start()
    assert model.second_started.wait(timeout=1)
    model.release.set()
    first.join(timeout=1)
    second.join(timeout=1)

    assert not first.is_alive()
    assert not second.is_alive()
