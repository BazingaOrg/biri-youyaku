import asyncio

import pytest

from biri_youyaku.modules.llm import client


def test_extract_summary_json_returns_summary_markdown():
    assert client._extract_summary_json('{"summary":"## Title\\nBody"}') == "## Title\nBody"


def test_extract_summary_json_rejects_non_summary_payload():
    with pytest.raises(ValueError):
        client._extract_summary_json('{"text":"missing"}')


def test_render_prompt_replaces_supported_placeholders():
    rendered = client.render_prompt(
        "{{language}} {{title}} {{author}} {{url}} {{transcript}} {{subtitles}} {{segment}} {{subtitle_source}}",
        language="中文",
        title="Title",
        author="Author",
        url="https://example.com",
        transcript="Transcript",
        subtitle_source="官方字幕",
    )

    assert rendered == (
        "中文 Title Author https://example.com Transcript Transcript Transcript 官方字幕"
    )


def test_resolve_temperature_uses_settings_override(monkeypatch):
    monkeypatch.setattr(client.settings, "llm_temperature", 0.7)

    assert client.resolve_temperature() == 0.7


def test_resolve_temperature_defaults_to_zero_point_two(monkeypatch):
    monkeypatch.setattr(client.settings, "llm_temperature", None)

    assert client.resolve_temperature() == 0.2


def test_build_create_kwargs_non_deepseek_passes_temperature(monkeypatch):
    monkeypatch.setattr(client.settings, "llm_thinking_enabled", False)
    kw = client._build_create_kwargs("gpt-4o-mini", 0.2, messages=[])
    assert kw["temperature"] == 0.2
    assert "extra_body" not in kw


def test_build_create_kwargs_deepseek_v4_thinking_disabled(monkeypatch):
    monkeypatch.setattr(client.settings, "llm_thinking_enabled", False)
    kw = client._build_create_kwargs("deepseek-v4-flash", 0.2, messages=[])
    assert kw["temperature"] == 0.2
    assert kw["extra_body"] == {"thinking": {"type": "disabled"}}


def test_build_create_kwargs_deepseek_v4_thinking_enabled_drops_temperature(monkeypatch):
    monkeypatch.setattr(client.settings, "llm_thinking_enabled", True)
    kw = client._build_create_kwargs("deepseek-v4-pro", 0.2, messages=[])
    # 思考模式会静默忽略 temperature，索性不传更干净
    assert "temperature" not in kw
    assert kw["extra_body"] == {"thinking": {"type": "enabled"}}


def test_usage_to_dict_normalizes_openai_usage():
    class Usage:
        prompt_tokens = 10
        completion_tokens = 5
        total_tokens = 15

    assert client._usage_to_dict(Usage()) == {
        "input_tokens": 10,
        "output_tokens": 5,
        "total_tokens": 15,
        "cost_estimate": None,
    }


@pytest.mark.asyncio
async def test_summarize_chunked_summarizes_segments_then_merges(monkeypatch):
    """段级总结改 markdown 直出 + 并行（_summarize_segment_markdown），合并阶段仍走
    JSON wrap（_complete_json_summary）。两路 stub 都拦。"""
    calls = []

    async def fake_segment_markdown(fake_client, *, model, prompt, on_usage=None):
        calls.append(prompt)
        return f"segment-{len(calls)}"

    async def fake_complete_json_summary(fake_client, *, model, prompt, on_usage=None):
        calls.append(prompt)
        return "merged"

    monkeypatch.setattr(client.settings, "llm_api_key", "key")
    monkeypatch.setattr(client.settings, "llm_chunk_token_threshold", 5)
    # 并发=1 让段级调用顺序稳定可断言
    monkeypatch.setattr(client.settings, "llm_segment_concurrency", 1)
    monkeypatch.setattr(client, "_summarize_segment_markdown", fake_segment_markdown)
    monkeypatch.setattr(client, "_complete_json_summary", fake_complete_json_summary)

    result = await client.summarize(
        [
            client.TranscriptItem(start=0, end=1, text="aaaa"),
            client.TranscriptItem(start=1, end=2, text="bbbb"),
        ],
        client.VideoMeta(
            url="https://example.com",
            bvid="BV123",
            cid=1,
            title="Title",
            author="Author",
            duration=10,
        ),
        client.JobOptions(),
    )

    assert result == "merged"
    assert len(calls) == 3
    assert "分段 1" in calls[0]
    assert "分段 2" in calls[1]
    assert "segment-1" in calls[2]
    assert "segment-2" in calls[2]


@pytest.mark.asyncio
async def test_summarize_chunked_cancels_sibling_segments_on_failure(monkeypatch):
    started_sibling = asyncio.Event()
    canceled_sibling = asyncio.Event()

    async def fake_segment_markdown(fake_client, *, model, prompt, on_usage=None):
        if "分段 1" in prompt:
            await started_sibling.wait()
            raise RuntimeError("segment failed")
        started_sibling.set()
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            canceled_sibling.set()
            raise
        return "should not finish"

    monkeypatch.setattr(client.settings, "llm_chunk_token_threshold", 5)
    monkeypatch.setattr(client.settings, "llm_segment_concurrency", 2)
    monkeypatch.setattr(client, "_summarize_segment_markdown", fake_segment_markdown)

    with pytest.raises(RuntimeError, match="segment failed"):
        await client._summarize_chunked(
            object(),
            items=[
                client.TranscriptItem(start=0, end=1, text="aaaa"),
                client.TranscriptItem(start=1, end=2, text="bbbb"),
            ],
            meta=client.VideoMeta(
                url="https://example.com",
                bvid="BV123",
                cid=1,
                title="Title",
                author="Author",
                duration=10,
            ),
            model="provider-model",
            language="中文简体",
            subtitle_source="platform",
        )

    assert canceled_sibling.is_set()


@pytest.mark.asyncio
async def test_complete_stream_publishes_accumulated_chunks():
    calls = []
    chunks = []

    class Delta:
        def __init__(self, content):
            self.content = content

    class Choice:
        def __init__(self, content):
            self.delta = Delta(content)

    class Chunk:
        def __init__(self, content, usage=None):
            self.choices = [Choice(content)]
            self.usage = usage

    class Usage:
        prompt_tokens = 3
        completion_tokens = 2
        total_tokens = 5

    class UsageChunk:
        choices = []
        usage = Usage()

    class FakeStream:
        def __aiter__(self):
            self.items = iter([Chunk("hel"), Chunk("lo"), UsageChunk()])
            return self

        async def __anext__(self):
            try:
                return next(self.items)
            except StopIteration as exc:
                raise StopAsyncIteration from exc

    class FakeCompletions:
        async def create(self, **kwargs):
            calls.append(kwargs)
            return FakeStream()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    async def on_chunk(text):
        chunks.append(text)

    usages = []

    async def on_usage(usage):
        usages.append(usage)

    result = await client._complete_stream(
        FakeClient(),
        model="provider-model",
        messages=[{"role": "user", "content": "hello"}],
        temperature=0.2,
        on_chunk=on_chunk,
        on_usage=on_usage,
    )

    assert result == "hello"
    assert chunks == ["hel", "hello"]
    assert calls[0]["stream"] is True
    assert calls[0]["stream_options"] == {"include_usage": True}
    assert usages == [{"input_tokens": 3, "output_tokens": 2, "total_tokens": 5, "cost_estimate": None}]
