from __future__ import annotations

import threading
import webbrowser
import argparse
import logging
import os
from pathlib import Path
from datetime import datetime
import wx
import wx.adv
try:
    from accessible_output2 import outputs
except ImportError:
    outputs = None

from database import NewsDatabase
from jw_feed import fetch_all

LOG_DIR = Path(os.environ.get("APPDATA", Path.home())) / "JWNoticiasFeed"
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(filename=LOG_DIR / "feed.log", level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                    encoding="utf-8")
LOGGER = logging.getLogger(__name__)


def speak(message: str) -> None:
    """Fala sem impedir o funcionamento caso não haja saída de voz instalada."""
    LOGGER.info("Voz: %s", message)
    if outputs is None:
        return
    try:
        if not hasattr(speak, "engine"):
            speak.engine = outputs.auto.Auto()
        speak.engine.output(message, interrupt=False)
    except Exception:
        LOGGER.exception("Não foi possível verbalizar a mensagem")


def display_date(value: str | None) -> str:
    if not value:
        return ""
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return value


def display_detection(value: str | None) -> str:
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return value


class MainFrame(wx.Frame):
    def __init__(self):
        super().__init__(None, title="JW Notícias — Feed acessível", size=(1050, 650))
        self.db = NewsDatabase(); self.rows = []
        panel = wx.Panel(self); root = wx.BoxSizer(wx.VERTICAL)
        self.status = wx.StaticText(panel, label="Pronto. Use Ctrl+S para sincronizar.")
        root.Add(self.status, 0, wx.ALL | wx.EXPAND, 8)
        bar = wx.BoxSizer(wx.HORIZONTAL)
        self.search = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER); self.search.SetHint("Pesquisar título ou resumo")
        self.region = wx.ComboBox(panel, choices=["Todas"] + self.db.regions(), style=wx.CB_READONLY); self.region.SetSelection(0)
        self.read = wx.ComboBox(panel, choices=["Todas", "Não lidas", "Lidas"], style=wx.CB_READONLY); self.read.SetSelection(0)
        self.sort = wx.ComboBox(panel, choices=["Mais recentes", "Mais antigas", "Não lidas primeiro", "Título"], style=wx.CB_READONLY); self.sort.SetSelection(0)
        self.sync = wx.Button(panel, label="Sincronizar (Ctrl+S)"); self.open_btn = wx.Button(panel, label="Abrir (Enter)")
        for label, control in (("Buscar", self.search), ("Região", self.region), ("Leitura", self.read), ("Ordenar", self.sort)):
            bar.Add(wx.StaticText(panel, label=label), 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 6); bar.Add(control, 1, wx.ALL, 4)
        bar.Add(self.sync, 0, wx.ALL, 4); bar.Add(self.open_btn, 0, wx.ALL, 4); root.Add(bar, 0, wx.EXPAND)
        self.list = wx.ListCtrl(panel, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_SUNKEN)
        for i, label in enumerate(("Título", "Data", "Região", "Estado")): self.list.InsertColumn(i, label)
        self.list.SetColumnWidth(0, 650); self.list.SetColumnWidth(1, 100); self.list.SetColumnWidth(2, 150); self.list.SetColumnWidth(3, 90)
        root.Add(self.list, 1, wx.ALL | wx.EXPAND, 8); panel.SetSizer(root)
        self.sync.Bind(wx.EVT_BUTTON, self.on_sync); self.open_btn.Bind(wx.EVT_BUTTON, self.on_open); self.list.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.on_open)
        self.search.Bind(wx.EVT_TEXT, lambda e: self.refresh()); self.region.Bind(wx.EVT_COMBOBOX, lambda e: self.refresh()); self.read.Bind(wx.EVT_COMBOBOX, lambda e: self.refresh()); self.sort.Bind(wx.EVT_COMBOBOX, lambda e: self.refresh())
        self.list.Bind(wx.EVT_CONTEXT_MENU, self.on_context_menu)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key); self.refresh()

    def refresh(self):
        self.list.DeleteAllItems(); self.rows = list(self.db.list(self.search.GetValue(), self.region.GetValue(), self.read.GetValue(), self.sort.GetValue()))
        for row in self.rows:
            published = display_date(row["published"]) or f"Sem data — detectada em {display_detection(row['first_seen'])}"
            i = self.list.InsertItem(self.list.GetItemCount(), row["title"]); self.list.SetItem(i, 1, published); self.list.SetItem(i, 2, row["region"] or "Geral"); self.list.SetItem(i, 3, "Lida" if row["is_read"] else "Não lida")
        self.status.SetLabel(f"{len(self.rows)} notícia(s) exibida(s).")

    def on_key(self, event):
        code = event.GetKeyCode(); mods = event.GetModifiers()
        if code == ord("S") and mods == wx.MOD_CONTROL: self.on_sync(None)
        elif code == wx.WXK_RETURN: self.on_open(None)
        elif code == wx.WXK_SPACE and self.list.GetFirstSelected() >= 0:
            row = self.rows[self.list.GetFirstSelected()]; self.db.set_read(row["url"], not row["is_read"]); self.refresh()
        elif code == ord("R") and mods == (wx.MOD_CONTROL | wx.MOD_SHIFT): self.db.mark_all_read(); self.refresh()
        else: event.Skip()

    def on_open(self, _):
        i = self.list.GetFirstSelected()
        if i < 0: return
        row = self.rows[i]; self.db.set_read(row["url"], True); webbrowser.open(row["url"]); self.refresh()

    def on_context_menu(self, event):
        index = self.list.GetFirstSelected()
        if index < 0:
            return
        row = self.rows[index]
        menu = wx.Menu()
        label = "Marcar como não lida" if row["is_read"] else "Marcar como lida"
        toggle = menu.Append(wx.ID_ANY, label)
        open_item = menu.Append(wx.ID_ANY, "Abrir no navegador")
        self.Bind(wx.EVT_MENU, lambda e: (self.db.set_read(row["url"], not row["is_read"]), self.refresh()), toggle)
        self.Bind(wx.EVT_MENU, lambda e: self.on_open(None), open_item)
        self.list.PopupMenu(menu)
        menu.Destroy()

    def on_sync(self, _):
        self.sync.Enable(False); self.status.SetLabel("Sincronizando…")
        LOGGER.info("Sincronização iniciada")
        speak("Sincronização iniciada. Vou consultar as notícias do JW ponto ORG.")
        def work():
            try:
                total = 0
                was_empty = self.db.count() == 0
                new_count = 0
                def save_batch(batch):
                    nonlocal total, new_count
                    new_count += self.db.upsert_many(batch)
                    total += len(batch)
                    message = f"Página processada. {total} notícias coletadas até agora."
                    wx.CallAfter(self.status.SetLabel, message)
                    speak(message)
                articles = fetch_all(max_pages=20, on_batch=save_batch)
                msg = f"Sincronização concluída. {len(articles)} notícias coletadas e salvas."
                LOGGER.info("Sincronização concluída: %s artigos", len(articles))
                speak(msg)
                if new_count and not was_empty:
                    wx.CallAfter(self.notify_new_articles, new_count)
                if getattr(self, "background_mode", False):
                    wx.CallAfter(self.notify_unread_count, self.db.unread_count())
            except Exception as exc:
                LOGGER.exception("Erro ao sincronizar")
                msg = f"Erro ao sincronizar: {exc} (detalhes em {LOG_DIR / 'feed.log'})"
                speak(f"A sincronização encontrou um erro. {total} notícias já foram salvas.")
            wx.CallAfter(self.finish_sync, msg)
        threading.Thread(target=work, daemon=True).start()

    def finish_sync(self, message):
        self.sync.Enable(True); self.status.SetLabel(message); self.region.SetItems(["Todas"] + self.db.regions()); self.region.SetSelection(0); self.refresh()

    def notify_new_articles(self, count):
        title = "JW Notícias"
        message = f"{count} nova notícia encontrada." if count == 1 else f"{count} novas notícias encontradas."
        notification = wx.adv.NotificationMessage(title, message, parent=self)
        notification.Show(timeout=wx.adv.NotificationMessage.Timeout_Auto)

    def notify_unread_count(self, count):
        message = f"Você tem {count} notícia não lida." if count == 1 else f"Você tem {count} notícias não lidas."
        notification = wx.adv.NotificationMessage("JW Notícias", message, parent=self)
        notification.Show(timeout=wx.adv.NotificationMessage.Timeout_Auto)


class TrayIcon(wx.adv.TaskBarIcon):
    """Ícone persistente para manter o coletor funcionando em segundo plano."""
    def __init__(self, frame):
        super().__init__(); self.frame = frame
        self.SetIcon(wx.ArtProvider.GetIcon(wx.ART_INFORMATION, wx.ART_OTHER, (16, 16)), "JW Notícias Feed")

    def CreatePopupMenu(self):
        menu = wx.Menu()
        show = menu.Append(wx.ID_ANY, "Mostrar janela")
        sync = menu.Append(wx.ID_ANY, "Sincronizar agora")
        menu.AppendSeparator(); quit_item = menu.Append(wx.ID_EXIT, "Sair")
        self.Bind(wx.EVT_MENU, lambda e: (self.frame.Show(), self.frame.Raise()), show)
        self.Bind(wx.EVT_MENU, lambda e: self.frame.on_sync(None), sync)
        self.Bind(wx.EVT_MENU, lambda e: self.frame.exit_app(), quit_item)
        return menu


class FeedApp(wx.App):
    def __init__(self, background=False):
        self.background = background
        self.keep_running = True
        super().__init__(False)

    def OnInit(self):
        self.frame = MainFrame(); self.tray = TrayIcon(self.frame)
        self.frame.background_mode = self.background
        self.frame.Bind(wx.EVT_CLOSE, self.on_close)
        self.frame.Show(not self.background)
        if self.background:
            self.frame.on_sync(None)
        return True

    def on_close(self, event):
        # Fechar a janela encerra de fato o aplicativo. O modo --background
        # apenas inicia oculto; não transforma o X em minimizar.
        self.keep_running = False
        if getattr(self, "tray", None):
            self.tray.RemoveIcon()
            self.tray.Destroy()
            self.tray = None
        event.Skip()

    def exit_app(self):
        self.keep_running = False
        self.frame.Close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Feed acessível de notícias do JW.ORG")
    parser.add_argument("--background", action="store_true", help="inicia minimizado na bandeja")
    args = parser.parse_args()
    app = FeedApp(args.background); app.MainLoop()
