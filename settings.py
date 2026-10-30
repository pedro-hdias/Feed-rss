"""Configurações do usuário, gravadas em JSON em %APPDATA%\\JWNoticiasFeed."""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from jw_feed import SITE_LANGS

LOGGER = logging.getLogger(__name__)

# auto: fala com leitor de tela, mas não com a voz do sistema (SAPI)
# important: eventos importantes; full: inclui progresso;
# commands: só respostas a comandos (Ctrl+E, copiar...); off: nada.
VOICE_MODES = ("auto", "important", "full", "commands", "off")


@dataclass
class Settings:
    interval_minutes: int = 60
    voice_mode: str = "auto"
    notifications: bool = True
    status_first: bool = True
    close_to_tray: bool = False
    hotkey_enabled: bool = True
    hotkey: str = "Ctrl+Alt+J"
    site_lang: str = "pt"
    first_run_done: bool = False

    def normalize(self) -> None:
        self.interval_minutes = max(0, min(1440, int(self.interval_minutes)))
        if self.voice_mode not in VOICE_MODES:
            self.voice_mode = "auto"
        if self.site_lang not in SITE_LANGS:
            self.site_lang = "pt"

    @classmethod
    def load(cls, path: Path) -> "Settings":
        settings = cls()
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except FileNotFoundError:
            return settings
        except (OSError, ValueError):
            LOGGER.exception("Configurações ilegíveis; usando o padrão")
            return settings
        if not isinstance(data, dict):
            return settings
        for f in fields(cls):
            if f.name not in data:
                continue
            value, default = data[f.name], getattr(settings, f.name)
            if isinstance(default, bool):
                ok = isinstance(value, bool)
            elif isinstance(default, int):
                ok = isinstance(value, int) and not isinstance(value, bool)
            else:
                ok = isinstance(value, str)
            if ok:
                setattr(settings, f.name, value)
        settings.normalize()
        return settings

    def save(self, path: Path) -> None:
        self.normalize()
        path = Path(path)
        tmp = path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, path)
        except OSError:
            LOGGER.exception("Não foi possível salvar as configurações")


_MODIFIERS = {"ctrl": "ctrl", "control": "ctrl", "alt": "alt", "shift": "shift", "win": "win", "windows": "win"}


def parse_hotkey(text: str) -> dict:
    """'Ctrl+Alt+J' -> {'ctrl': True, ..., 'key': 'J', 'vk': 74}. Levanta ValueError se inválido."""
    parts = [p for p in (text or "").replace(" ", "").split("+") if p]
    if len(parts) < 2:
        raise ValueError("Informe modificadores e uma tecla, por exemplo Ctrl+Alt+J.")
    *mods, key = parts
    spec = {"ctrl": False, "alt": False, "shift": False, "win": False}
    for m in mods:
        name = _MODIFIERS.get(m.lower())
        if name is None:
            raise ValueError(f"Modificador desconhecido: {m}. Use Ctrl, Alt, Shift ou Win.")
        spec[name] = True
    if not (spec["ctrl"] or spec["alt"] or spec["win"]):
        raise ValueError("O atalho precisa de Ctrl, Alt ou Win; só com Shift ele atrapalharia a digitação.")
    k = key.upper()
    if re.fullmatch(r"[A-Z0-9]", k):
        vk = ord(k)
    elif re.fullmatch(r"F([1-9]|1[0-2])", k):
        vk = 0x70 + int(k[1:]) - 1  # VK_F1 = 0x70
    else:
        raise ValueError("A tecla deve ser uma letra, um número ou F1 a F12.")
    spec["key"], spec["vk"] = k, vk
    return spec


def format_hotkey(spec: dict) -> str:
    names = [n.capitalize() for n in ("ctrl", "alt", "shift", "win") if spec[n]]
    return "+".join(names + [spec["key"]])
