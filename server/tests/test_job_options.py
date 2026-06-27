from biri_youyaku.config import Settings
from biri_youyaku.jobs.model import JobOptions


def test_job_options_from_settings_uses_env_defaults():
    settings = Settings(
        asr_language_default="zh",
        summary_language="English",
        email_enabled=False,
        email_default_recipient="default@example.com",
        email_subject_template="Subject {{title}}",
        llm_base_url="https://llm.example/v1",
        llm_model="model-a",
    )

    options = JobOptions.from_settings(settings)

    assert options.as_dict() == {
        "task_type": "summary",
        "language": "zh",
        "force_asr": False,
        "summary_language": "English",
        "email_enabled": False,
        "email_subject_template": "Subject {{title}}",
        "llm_base_url": "https://llm.example/v1",
        "llm_model": "model-a",
        "prompt_template": None,
    }


def test_job_options_from_overrides_keeps_defaults_for_unset_fields():
    settings = Settings(
        email_enabled=True,
        email_default_recipient="default@example.com",
    )

    options = JobOptions.from_overrides(
        {
            "task_type": "audio",
            "email_enabled": False,
            "llm_model": "model-b",
            "summary_words": 1200,
            "unknown": "ignored",
        },
        settings,
    )

    assert options.task_type == "audio"
    assert options.email_enabled is False
    assert options.llm_model == "model-b"
    assert "summary_words" not in options.as_dict()
