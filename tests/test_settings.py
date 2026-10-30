import pytest

from settings import Settings, format_hotkey, parse_hotkey


def test_roundtrip(tmp_path):
    path = tmp_path / "s.json"
    s = Settings(interval_minutes=15, voice_mode="full", close_to_tray=True)
    s.save(path)
    loaded = Settings.load(path)
    assert loaded.interval_minutes == 15 and loaded.voice_mode == "full" and loaded.close_to_tray


def test_missing_and_corrupt_files_use_defaults(tmp_path):
    assert Settings.load(tmp_path / "nao-existe.json") == Settings()
    bad = tmp_path / "bad.json"
    bad.write_text("{ isto não é json", encoding="utf-8")
    assert Settings.load(bad) == Settings()


def test_invalid_values_are_normalized(tmp_path):
    path = tmp_path / "s.json"
    path.write_text('{"interval_minutes": 99999, "voice_mode": "gritando", "site_lang": "xx", "notifications": "sim"}',
                    encoding="utf-8")
    s = Settings.load(path)
    assert s.interval_minutes == 1440
    assert s.voice_mode == "auto"
    assert s.site_lang == "pt"
    assert s.notifications is True  # tipo errado é ignorado


def test_parse_hotkey_ok():
    spec = parse_hotkey("Ctrl+Alt+j")
    assert spec["ctrl"] and spec["alt"] and not spec["shift"] and spec["vk"] == ord("J")
    assert parse_hotkey("ctrl + shift + F5")["vk"] == 0x74
    assert format_hotkey(parse_hotkey("alt+ctrl+j")) == "Ctrl+Alt+J"


@pytest.mark.parametrize("text", ["", "J", "Ctrl", "Shift+J", "Ctrl+Alt+JJ", "Foo+J", "Ctrl+F13", "Ctrl+Ç"])
def test_parse_hotkey_invalid(text):
    with pytest.raises(ValueError):
        parse_hotkey(text)
