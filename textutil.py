"""Formatação de textos exibidos/falados (sem dependência de wxPython)."""
from __future__ import annotations

import re
from datetime import datetime, timezone

_SMALL_WORDS = {"de", "da", "do", "das", "dos", "e"}


def format_region(value: str | None) -> str:
    """'NOTÍCIAS MUNDIAIS' -> 'Notícias Mundiais'. Leitores de tela costumam
    soletrar texto todo em maiúsculas, então a região é normalizada."""
    if not value:
        return ""
    text = re.sub(r"\s+", " ", value).strip()
    if text != text.upper() and text != text.lower():
        return text  # já tem caixa mista: respeita
    words = text.lower().split(" ")
    out = [w if (i > 0 and w in _SMALL_WORDS) else w[:1].upper() + w[1:] for i, w in enumerate(words)]
    return " ".join(out)


def display_date(value: str | None) -> str:
    if not value:
        return ""
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return value


def utc_to_local(value: str) -> datetime:
    """Converte 'YYYY-MM-DD HH:MM:SS' (UTC, como o SQLite grava) para a hora local."""
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc).astimezone()


def display_detection(value: str | None) -> str:
    if not value:
        return ""
    try:
        return utc_to_local(value).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return value


def now_utc_string() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def plural(n: int, singular: str, plural_: str) -> str:
    return f"{n} {singular if n == 1 else plural_}"
