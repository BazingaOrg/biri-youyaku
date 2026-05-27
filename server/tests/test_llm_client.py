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


@pytest.mark.asyncio
async def test_complete_retries_with_temperature_one_when_provider_requires_it():
    calls = []

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

            return Response()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    result = await client._complete(
        FakeClient(),
        model="provider-model",
        messages=[{"role": "user", "content": "hello"}],
        temperature=0.2,
    )

    assert result == '{"summary":"ok"}'
    assert [call["temperature"] for call in calls] == [0.2, 1]
