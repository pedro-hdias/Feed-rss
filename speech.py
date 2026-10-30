"""Anúncios falados via accessible_output2.

Regras importantes:
* O motor de voz é criado e usado SOMENTE na thread da interface (COM e as DLLs
  dos leitores de tela não são thread-safe). De outras threads, a fala é
  enfileirada com wx.CallAfter.
* Cada mensagem tem um nível ("command", "important" ou "progress") e o modo de
  voz escolhido pelo usuário decide quais níveis falam. No modo "auto", o app só
  fala por conta própria quando há um leitor de tela ativo; se só existe a voz do
  Windows (SAPI), ele fica calado e responde apenas a comandos, para não criar
  uma segunda voz competindo com a do usuário.
"""
from __future__ import annotations

import logging

import wx

from uithread import call_ui, shutting_down

LOGGER = logging.getLogger(__name__)

try:
    from accessible_output2 import outputs
except Exception:  # ImportError, mas também falha ao carregar DLLs/COM
    LOGGER.exception("accessible_output2 indisponível; o aplicativo ficará sem voz")
    outputs = None

COMMAND, IMPORTANT, PROGRESS = "command", "important", "progress"


class Announcer:
    def __init__(self, get_mode):
        self._get_mode = get_mode  # callable -> "auto" | "important" | "full" | "commands" | "off"
        self._engine = None
        self._failed = False

    # -- API pública (qualquer thread) ------------------------------------
    def say(self, message: str, level: str = IMPORTANT, interrupt: bool = False) -> None:
        LOGGER.info("Voz[%s]: %s", level, message)
        if outputs is None or shutting_down.is_set():
            return
        if wx.IsMainThread():
            self._say_now(message, level, interrupt)
        else:
            call_ui(self._say_now, message, level, interrupt)

    # -- somente thread da interface --------------------------------------
    def _ensure_engine(self):
        if self._engine is None and not self._failed:
            try:
                self._engine = outputs.auto.Auto()
            except Exception:
                LOGGER.exception("Não foi possível iniciar a saída de voz")
                self._failed = True
        return self._engine

    def _active_output(self):
        engine = self._ensure_engine()
        if engine is None:
            return None
        try:
            return engine.get_first_available_output()
        except Exception:
            LOGGER.exception("Falha ao consultar a saída de voz ativa")
            return None

    def screen_reader_active(self) -> bool:
        """True se a saída ativa é um leitor de tela (e não a voz do sistema)."""
        out = self._active_output()
        return out is not None and not out.is_system_output()

    def active_output_name(self) -> str:
        if outputs is None:
            return "indisponível"
        out = self._active_output()
        return "nenhuma" if out is None else str(getattr(out, "name", type(out).__name__))

    def _allowed(self, level: str) -> bool:
        mode = self._get_mode()
        if mode == "off":
            return False
        if mode == "commands":
            return level == COMMAND
        if mode == "important":
            return level in (COMMAND, IMPORTANT)
        if mode == "full":
            return True
        # auto
        if self.screen_reader_active():
            return level in (COMMAND, IMPORTANT)
        return level == COMMAND

    def _say_now(self, message: str, level: str, interrupt: bool) -> None:
        if shutting_down.is_set() or not self._allowed(level):
            return
        engine = self._ensure_engine()
        if engine is None:
            return
        try:
            engine.output(message, interrupt=interrupt)
        except Exception:
            LOGGER.exception("Não foi possível verbalizar a mensagem")
