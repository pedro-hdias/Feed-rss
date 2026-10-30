"""Utilidades para falar com a thread da interface de qualquer lugar."""
from __future__ import annotations

import logging
import threading

import wx

LOGGER = logging.getLogger(__name__)

shutting_down = threading.Event()


def call_ui(func, *args) -> None:
    """wx.CallAfter que não explode se o aplicativo já estiver fechando."""
    if shutting_down.is_set():
        return
    try:
        wx.CallAfter(func, *args)
    except Exception:
        LOGGER.debug("CallAfter ignorado", exc_info=True)
