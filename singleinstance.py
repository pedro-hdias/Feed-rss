"""Instância única + pedido para a primeira instância aparecer.

No Windows usa um evento nomeado (ctypes, sem dependências nem servidor local):
a segunda instância sinaliza o evento e sai; a primeira, que escuta o evento
numa thread, restaura a janela. Fora do Windows só garante instância única.
"""
from __future__ import annotations

import logging
import sys
import threading

from uithread import call_ui, shutting_down

LOGGER = logging.getLogger(__name__)

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _k32.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
    _k32.CreateEventW.restype = wintypes.HANDLE
    _k32.SetEvent.argtypes = [wintypes.HANDLE]
    _k32.SetEvent.restype = wintypes.BOOL
    _k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    _k32.WaitForSingleObject.restype = wintypes.DWORD
    _k32.CloseHandle.argtypes = [wintypes.HANDLE]
    _k32.CloseHandle.restype = wintypes.BOOL
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _user32.AllowSetForegroundWindow.argtypes = [wintypes.DWORD]
    _user32.AllowSetForegroundWindow.restype = wintypes.BOOL
    _ERROR_ALREADY_EXISTS = 183
    _ASFW_ANY = 0xFFFFFFFF


class SingleInstance:
    def __init__(self, name: str):
        self.name = name
        self._handle = None
        self._checker = None

    def acquire(self) -> bool:
        """True se esta é a primeira instância."""
        if sys.platform == "win32":
            handle = _k32.CreateEventW(None, False, False, f"Local\\{self.name}")
            if not handle:
                LOGGER.error("Não foi possível criar o evento de instância única")
                return True  # na dúvida, deixa executar
            already = ctypes.get_last_error() == _ERROR_ALREADY_EXISTS
            self._handle = handle
            return not already
        import wx
        self._checker = wx.SingleInstanceChecker(self.name)
        return not self._checker.IsAnotherRunning()

    def notify_existing(self) -> None:
        """Pede à primeira instância que mostre a janela."""
        if sys.platform == "win32" and self._handle:
            _user32.AllowSetForegroundWindow(_ASFW_ANY)
            _k32.SetEvent(self._handle)

    def listen(self, callback) -> None:
        if sys.platform != "win32" or not self._handle:
            return
        handle = self._handle

        def loop():
            while not shutting_down.is_set():
                if _k32.WaitForSingleObject(handle, 1000) == 0:  # WAIT_OBJECT_0
                    call_ui(callback)

        threading.Thread(target=loop, name="show-signal", daemon=True).start()

    def close(self) -> None:
        if sys.platform == "win32" and self._handle:
            _k32.CloseHandle(self._handle)
            self._handle = None
