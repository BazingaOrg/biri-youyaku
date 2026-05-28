import pytest

from biri_youyaku.jobs import pipeline
from biri_youyaku.jobs.model import Job, JobOptions, JobStatus
from biri_youyaku.modules.bilibili.subtitle import TranscriptItem
from biri_youyaku.modules.asr.base import TranscribeRequest


@pytest.mark.asyncio
async def test_transcribe_audio_uses_faster_whisper_when_configured(monkeypatch, tmp_path):
    calls = {}

    class FakeWhisperTranscriber:
        async def transcribe(self, request: TranscribeRequest):
            calls["request"] = request
            return [TranscriptItem(start=0, end=1, text="hello")]

    monkeypatch.setattr(pipeline.settings, "asr_model", "faster-whisper")
    monkeypatch.setattr(pipeline, "FasterWhisperTranscriber", FakeWhisperTranscriber)
    monkeypatch.setattr(pipeline.repo, "set_subtitle_source", lambda job_id, source: calls.update(source=(job_id, source)))
    audio_path = tmp_path / "audio.wav"
    job = Job(
        id="job-1",
        url="https://www.bilibili.com/video/BV123",
        status=JobStatus.TRANSCRIBING,
        options=JobOptions(language="zh"),
        created_at=1,
        updated_at=1,
    )

    result = await pipeline.transcribe_audio(job, audio_path)

    assert result[0].text == "hello"
    assert calls["request"].audio_path == audio_path
    assert calls["request"].language == "zh"
    assert calls["source"] == ("job-1", "asr")
