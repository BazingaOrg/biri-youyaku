from biri_youyaku.modules.asr.sensevoice import clean_transcription_text


def test_clean_transcription_text_removes_sensevoice_tags_and_markers():
    text = "<|zh|><|ANGRY|><|BGM|><|woitn|>说说你的优点吧我跳过龙你跳过我"

    assert clean_transcription_text(text) == "说说你的优点吧我跳过龙你跳过我"


def test_clean_transcription_text_collapses_whitespace():
    assert clean_transcription_text("  你好   世界  ") == "你好 世界"
