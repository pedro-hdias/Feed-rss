from __future__ import annotations

import argparse
import re
import sys

from appinfo import APP_NAME, data_dir
from logsetup import setup_logging

LOGGER = setup_logging()  # antes dos demais imports: falhas de importação também vão para o log

import wx  # noqa: E402

from frame import MainFrame  # noqa: E402
from settings import Settings  # noqa: E402
from singleinstance import SingleInstance  # noqa: E402
from speech import Announcer  # noqa: E402
from tray import TrayIcon  # noqa: E402


class FeedApp(wx.App):
    def __init__(self, background: bool = False, interval: int | None = None):
        self.background = background
        self.interval = interval
        self.already_running = False
        self.single: SingleInstance | None = None
        self.frame: MainFrame | None = None
        super().__init__(False)

    def OnInit(self):
        self.SetAppName("JWNoticiasFeed")
        user = re.sub(r"[^A-Za-z0-9_.-]", "_", wx.GetUserId() or "user")
        self.single = SingleInstance(f"JWNoticiasFeed-{user}")
        if not self.single.acquire():
            LOGGER.info("Outra instância já está em execução; pedindo para ela aparecer.")
            self.already_running = True
            self.single.notify_existing()
            if sys.platform != "win32" and not self.background:
                wx.MessageBox("O JW Notícias já está em execução.", APP_NAME, wx.OK | wx.ICON_INFORMATION)
            return True

        settings_path = data_dir() / "settings.json"
        settings = Settings.load(settings_path)
        if self.interval is not None:
            settings.interval_minutes = max(0, self.interval)
        announcer = Announcer(lambda: self.frame.settings.voice_mode if self.frame else settings.voice_mode)

        self.frame = MainFrame(settings, settings_path, announcer)
        self.frame.tray = TrayIcon(self.frame)
        self.frame.refresh()  # atualiza o texto do ícone com o total de não lidas
        self.single.listen(self.frame.restore_from_tray)  # 2ª instância -> traz esta janela
        self.SetTopWindow(self.frame)
        self.frame.Show(not self.background)
        if self.background:
            self.frame.notify_unread_after_sync = True
            self.frame.on_sync(automatic=True)
        else:
            wx.CallAfter(self.frame.first_run)
        return True

    def cleanup(self):
        if self.frame is not None:
            try:
                self.frame.shutdown()
            except Exception:
                LOGGER.debug("Falha na limpeza final", exc_info=True)
        if self.single is not None:
            self.single.close()


def main():
    parser = argparse.ArgumentParser(description="Feed acessível de notícias do JW.ORG")
    parser.add_argument("--background", action="store_true", help="inicia minimizado na bandeja")
    parser.add_argument("--interval", type=int, default=None,
                        help="minutos entre sincronizações automáticas nesta execução (0 desativa)")
    args = parser.parse_args()
    LOGGER.info("Iniciando (background=%s, intervalo=%s)", args.background, args.interval)
    app = FeedApp(args.background, args.interval)
    if app.already_running:
        app.cleanup()
        return
    try:
        app.MainLoop()
    finally:
        app.cleanup()
        LOGGER.info("Encerrado")


if __name__ == "__main__":
    main()
