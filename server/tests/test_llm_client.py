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

    assert client.resolve_temperature("gpt-4o-mini") == 0.7


def test_resolve_temperature_defaults_to_zero_point_two(monkeypatch):
    monkeypatch.setattr(client.settings, "llm_temperature", None)

    assert client.resolve_temperature("gpt-4o-mini") == 0.2
    assert client.resolve_temperature("kimi-k2.5") == 1


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
    calls = []

    async def fake_complete_json_summary(fake_client, *, model, prompt, on_usage=None):
        calls.append(prompt)
        if "分段摘要" in prompt:
            return "merged"
        return f"segment-{len(calls)}"

    monkeypatch.setattr(client.settings, "llm_api_key", "key")
    monkeypatch.setattr(client.settings, "llm_chunk_token_threshold", 5)
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
async def test_complete_retries_with_temperature_one_when_provider_requires_it():
    calls = []
    usages = []

    class FakeCompletions:
        async def create(self, **kwargs):
            calls.append(kwargs)
            if kwargs["temperature"] != 1:
                raise RuntimeError("invalid temperature: only 1 is allowed for this model")

            class Message:
                content = '{"summary":"ok"}'

            class Choice:
                message = Message()

            class Response:
                choices = [Choice()]
                usage = None

            return Response()

    async def on_usage(usage):
        usages.append(usage)

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    result = await client._complete(
        FakeClient(),
        model="provider-model",
        messages=[{"role": "user", "content": "hello"}],
        temperature=0.2,
        on_usage=on_usage,
    )

    assert result == '{"summary":"ok"}'
    assert [call["temperature"] for call in calls] == [0.2, 1]
    assert usages == []


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
