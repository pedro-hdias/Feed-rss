from __future__ import annotations

import logging

import wx
import wx.adv

from appinfo import resource_path

LOGGER = logging.getLogger(__name__)


def load_icon(size: int = 16) -> wx.Icon:
    path = resource_path("assets/icon.ico")
    try:
        icon = wx.Icon(str(path), wx.BITMAP_TYPE_ICO, size, size)
        if icon.IsOk():
            return icon
    except Exception:
        LOGGER.debug("Ícone não carregado de %s", path, exc_info=True)
    return wx.ArtProvider.GetIcon(wx.ART_INFORMATION, wx.ART_OTHER, (size, size))


class TrayIcon(wx.adv.TaskBarIcon):
    """Ícone persistente para manter o coletor funcionando em segundo plano."""

    def __init__(self, frame):
        super().__init__()
        self.frame = frame
        self._icon = load_icon(16)
        self.update_tooltip(None)
        self.Bind(wx.adv.EVT_TASKBAR_LEFT_UP, lambda e: self.frame.restore_from_tray())

    def update_tooltip(self, unread: int | None):
        text = "JW Notícias" if unread is None else f"JW Notícias — {unread} não lida(s)"
        self.SetIcon(self._icon, text)

    def CreatePopupMenu(self):
        menu = wx.Menu()
        show = menu.Append(wx.ID_ANY, "Mostrar janela")
        status = menu.Append(wx.ID_ANY, "Falar status")
        sync = menu.Append(wx.ID_ANY, "Sincronizar agora")
        menu.AppendSeparator()
        quit_item = menu.Append(wx.ID_EXIT, "Sair")
        self.Bind(wx.EVT_MENU, lambda e: self.frame.restore_from_tray(), show)
        self.Bind(wx.EVT_MENU, lambda e: self.frame.speak_status(), status)
        self.Bind(wx.EVT_MENU, lambda e: self.frame.on_sync(), sync)
        self.Bind(wx.EVT_MENU, lambda e: self.frame.exit_app(), quit_item)
        return menu
