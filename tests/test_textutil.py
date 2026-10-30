from textutil import display_date, display_detection, format_region, plural


def test_format_region_upper_and_small_words():
    assert format_region("NOTÍCIAS MUNDIAIS") == "Notícias Mundiais"
    assert format_region("COREIA DO SUL") == "Coreia do Sul"
    assert format_region("estados unidos") == "Estados Unidos"


def test_format_region_keeps_mixed_case_and_empty():
    assert format_region("Brasil") == "Brasil"
    assert format_region("") == ""
    assert format_region(None) == ""


def test_display_date():
    assert display_date("2026-10-01") == "01/10/2026"
    assert display_date(None) == ""
    assert display_date("ontem") == "ontem"


def test_display_detection_converts_utc_to_local():
    from datetime import datetime, timezone
    value = "2026-10-30 12:00:00"
    expected = datetime(2026, 10, 30, 12, tzinfo=timezone.utc).astimezone().strftime("%d/%m/%Y %H:%M")
    assert display_detection(value) == expected
    assert display_detection("lixo") == "lixo"


def test_plural():
    assert plural(1, "notícia", "notícias") == "1 notícia"
    assert plural(0, "notícia", "notícias") == "0 notícias"
