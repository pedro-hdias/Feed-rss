from __future__ import annotations

import logging
import threading
import webbrowser

import wx
import wx.adv

import startup
from appinfo import APP_NAME, APP_TITLE, __version__, data_dir, open_folder
from database import NewsDatabase
from dialogs import ReaderDialog, SettingsDialog, TextDialog, shortcuts_text
from jw_feed import fetch_all
from settings import Settings, parse_hotkey
from speech import COMMAND, IMPORTANT, PROGRESS, Announcer
from textutil import display_date, display_detection, now_utc_string, plural
from tray import TrayIcon, load_icon
from uithread import call_ui, shutting_down

LOGGER = logging.getLogger(__name__)

ALL = "Todas"
HOTKEY_ID = 0x4A57  # RegisterHotKey exige um inteiro entre 0 e 0xBFFF
COLUMNS = {"state": ("Estado", 90), "title": ("Título", 650), "date": ("Data", 100), "region": ("Região", 160)}


class MainFrame(wx.Frame):
    def __init__(self, settings: Settings, settings_path, announcer: Announcer):
        super().__init__(None, title=APP_TITLE, size=(1050, 650))
        self.settings = settings
        self.settings_path = settings_path
        self.announcer = announcer
        self.db = NewsDatabase()
        self.rows: list = []
        self.region_values = [ALL]
        self._region_labels: list[str] = []
        self.tray: TrayIcon | None = None
        self.syncing = False
        self.failures = 0
        self.last_error = ""
        self.notify_unread_after_sync = False
        self._closing = False
        self._exiting = False
        self._notification = None
        self._sync_timer_id = wx.NewIdRef()
        self._search_timer_id = wx.NewIdRef()

        self.SetIcon(load_icon(32))
        self._build_menu()
        self._build_ui()
        self.CreateStatusBar()
        self.set_status("Pronto. Use Ctrl+S para sincronizar.")

        self.Bind(wx.EVT_CHAR_HOOK, self.on_key)
        self.Bind(wx.EVT_ICONIZE, self.on_iconize)
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.Bind(wx.EVT_HOTKEY, self.on_hotkey, id=HOTKEY_ID)

        self.sync_timer = wx.Timer(self, self._sync_timer_id)
        self.search_timer = wx.Timer(self, self._search_timer_id)
        self.Bind(wx.EVT_TIMER, lambda e: self.on_sync(automatic=True), id=self._sync_timer_id)
        self.Bind(wx.EVT_TIMER, lambda e: self.apply_filters(), id=self._search_timer_id)
        self.restart_sync_timer()

        self.build_columns()
        self.refresh()
        self.apply_hotkey()

    # ------------------------------------------------------------------
    # Construção da interface
    # ------------------------------------------------------------------
    def _item(self, menu, label, handler, help_text=""):
        item = menu.Append(wx.ID_ANY, label, help_text)
        self.Bind(wx.EVT_MENU, handler, item)
        return item

    def _build_menu(self):
        bar = wx.MenuBar()

        file_menu = wx.Menu()
        self._item(file_menu, "&Sincronizar agora\tCtrl+S", lambda e: self.on_sync())
        self._item(file_menu, "Marcar &todas como lidas\tCtrl+Shift+R", lambda e: self.mark_all_read())
        self._item(file_menu, "Marcar a &região atual como lida", lambda e: self.mark_region_read())
        file_menu.AppendSeparator()
        self._item(file_menu, "&Opções…\tCtrl+O", lambda e: self.show_settings())
        self._item(file_menu, "&Enviar para a bandeja\tCtrl+M", lambda e: self.hide_to_tray())
        file_menu.AppendSeparator()
        self._item(file_menu, "Sa&ir\tCtrl+Q", lambda e: self.exit_app())
        bar.Append(file_menu, "&Arquivo")

        news_menu = wx.Menu()
        self._item(news_menu, "&Ler notícia (Enter na lista)", lambda e: self.read_selected())
        self._item(news_menu, "&Abrir no navegador\tCtrl+Enter", lambda e: self.open_in_browser())
        self._item(news_menu, "Al&ternar lida/não lida (Espaço na lista)", lambda e: self.toggle_read())
        self._item(news_menu, "&Copiar título e link (Ctrl+C na lista)", lambda e: self.copy_selected())
        self._item(news_menu, "Copiar &link", lambda e: self.copy_selected(link_only=True))
        news_menu.AppendSeparator()
        self._item(news_menu, "&Próxima não lida\tF8", lambda e: self.goto_unread(1))
        self._item(news_menu, "Não lida a&nterior\tShift+F8", lambda e: self.goto_unread(-1))
        bar.Append(news_menu, "No&tícia")

        view_menu = wx.Menu()
        self._item(view_menu, "Ir para a &busca\tCtrl+F", lambda e: self.focus_search())
        self._item(view_menu, "Ir para a &lista\tCtrl+L", lambda e: self.focus_list())
        self._item(view_menu, "&Falar status\tCtrl+E", lambda e: self.speak_status())
        bar.Append(view_menu, "&Exibir")

        help_menu = wx.Menu()
        self._item(help_menu, "&Atalhos de teclado\tF1", lambda e: self.show_shortcuts())
        self._item(help_menu, "Abrir pasta de &logs", lambda e: open_folder(data_dir()))
        self._item(help_menu, "&Sobre", lambda e: self.show_about())
        bar.Append(help_menu, "A&juda")
        self.SetMenuBar(bar)

    def _build_ui(self):
        panel = wx.Panel(self)
        root = wx.BoxSizer(wx.VERTICAL)

        bar = wx.BoxSizer(wx.HORIZONTAL)
        self.search = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER)
        self.search.SetHint("Pesquisar título ou resumo")
        self.region = wx.Choice(panel, choices=[ALL])
        self.region.SetSelection(0)
        self.read = wx.Choice(panel, choices=["Todas", "Não lidas", "Lidas"])
        self.read.SetSelection(0)
        self.sort = wx.Choice(panel, choices=["Mais recentes", "Mais antigas", "Não lidas primeiro", "Título"])
        self.sort.SetSelection(0)
        self.sync = wx.Button(panel, label="&Sincronizar")
        self.read_btn = wx.Button(panel, label="&Ler notícia")
        # O rótulo vem imediatamente antes do controle (é assim que os leitores de
        # tela associam o nome ao campo); o & cria o atalho Alt+letra.
        for label, control in (("&Buscar", self.search), ("&Região", self.region),
                               ("&Mostrar", self.read), ("&Ordenar", self.sort)):
            bar.Add(wx.StaticText(panel, label=label), 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 6)
            bar.Add(control, 1, wx.ALL, 4)
        bar.Add(self.sync, 0, wx.ALL, 4)
        bar.Add(self.read_btn, 0, wx.ALL, 4)
        root.Add(bar, 0, wx.EXPAND)

        root.Add(wx.StaticText(panel, label="&Notícias"), 0, wx.LEFT | wx.TOP, 10)
        self.list = wx.ListCtrl(panel, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_SUNKEN)
        root.Add(self.list, 1, wx.ALL | wx.EXPAND, 8)
        panel.SetSizer(root)

        self.search.Bind(wx.EVT_TEXT, lambda e: self.search_timer.StartOnce(300))  # espera parar de digitar
        self.search.Bind(wx.EVT_TEXT_ENTER, self.on_search_enter)
        for choice in (self.region, self.read, self.sort):
            choice.Bind(wx.EVT_CHOICE, lambda e: self.apply_filters())
        self.sync.Bind(wx.EVT_BUTTON, lambda e: self.on_sync())
        self.read_btn.Bind(wx.EVT_BUTTON, lambda e: self.read_selected())
        self.list.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda e: self.read_selected())
        self.list.Bind(wx.EVT_CONTEXT_MENU, self.on_context_menu)

    # ------------------------------------------------------------------
    # Status e anúncios
    # ------------------------------------------------------------------
    def set_status(self, text: str):
        if not self._closing:
            self.SetStatusText(text)

    def announce(self, message: str, level: str = IMPORTANT, interrupt: bool = False):
        self.announcer.say(message, level, interrupt)

    def status_summary(self) -> str:
        total, unread = self.db.count(), self.db.unread_count()
        last = self.db.get_meta("last_sync")
        parts = [f"{plural(len(self.rows), 'notícia exibida', 'notícias exibidas')} de {total}",
                 plural(unread, "não lida", "não lidas")]
        parts.append(f"Última sincronização em {display_detection(last)}" if last else "Ainda não sincronizado")
        if self.syncing:
            parts.append("Sincronização em andamento")
        elif self.failures and self.last_error:
            parts.append("A última sincronização falhou")
        return ". ".join(parts) + "."

    def speak_status(self):
        summary = self.status_summary()
        self.set_status(summary)
        self.announce(summary, COMMAND, interrupt=True)

    def announce_count(self):
        n = len(self.rows)
        self.announce("Nenhuma notícia." if n == 0 else plural(n, "notícia.", "notícias."), IMPORTANT, interrupt=True)

    # ------------------------------------------------------------------
    # Lista
    # ------------------------------------------------------------------
    def column_keys(self) -> list[str]:
        return ["state", "title", "date", "region"] if self.settings.status_first else ["title", "date", "region", "state"]

    def build_columns(self):
        self.list.DeleteAllColumns()
        for i, key in enumerate(self.column_keys()):
            label, width = COLUMNS[key]
            self.list.InsertColumn(i, label, width=width)

    def cell_text(self, row, key: str) -> str:
        if key == "state":
            return "Lida" if row["is_read"] else "Não lida"
        if key == "title":
            return row["title"]
        if key == "date":
            return display_date(row["published"]) or f"Sem data — detectada em {display_detection(row['first_seen'])}"
        return row["region"] or "Geral"

    def selected_row(self):
        i = self.list.GetFirstSelected()
        return self.rows[i] if 0 <= i < len(self.rows) else None

    def selected_region(self) -> str:
        i = self.region.GetSelection()
        return self.region_values[i] if 0 <= i < len(self.region_values) else ALL

    def rebuild_regions(self):
        """Atualiza a lista de regiões (com contagem de não lidas) preservando a escolha."""
        current = self.selected_region()
        values, labels = [ALL], [ALL]
        for region, _total, unread in self.db.region_counts():
            values.append(region)
            labels.append(f"{region}, {plural(unread, 'não lida', 'não lidas')}" if unread else region)
        if labels != self._region_labels:
            self.region_values, self._region_labels = values, labels
            self.region.SetItems(labels)
        index = self.region_values.index(current) if current in self.region_values else 0
        self.region.SetSelection(index)

    def refresh(self, select_url: str | None = None):
        """Recarrega a lista mantendo a seleção (importante para leitores de tela)."""
        previous = self.list.GetFirstSelected()
        if select_url is None and 0 <= previous < len(self.rows):
            select_url = self.rows[previous]["url"]

        self.rebuild_regions()
        keys = self.column_keys()
        self.list.Freeze()
        try:
            self.list.DeleteAllItems()
            self.rows = list(self.db.list(self.search.GetValue(), self.selected_region(),
                                          self.read.GetStringSelection(), self.sort.GetStringSelection()))
            for row in self.rows:
                i = self.list.InsertItem(self.list.GetItemCount(), self.cell_text(row, keys[0]))
                for col, key in enumerate(keys[1:], start=1):
                    self.list.SetItem(i, col, self.cell_text(row, key))
        finally:
            self.list.Thaw()

        target = next((i for i, r in enumerate(self.rows) if r["url"] == select_url), None)
        if target is None and self.rows:
            # A notícia saiu do filtro (ex.: marcada como lida em "Não lidas"):
            # fica na mesma posição, ou na última.
            target = min(max(previous, 0), len(self.rows) - 1)
        if target is not None:
            self.list.Select(target)
            self.list.Focus(target)

        unread = self.db.unread_count()
        self.set_status(f"{plural(len(self.rows), 'notícia exibida', 'notícias exibidas')}. "
                        f"{plural(unread, 'não lida', 'não lidas')} no total.")
        if self.tray:
            self.tray.update_tooltip(unread)

    def apply_filters(self):
        if self._closing:
            return
        self.refresh()
        self.announce_count()

    def on_search_enter(self, _event):
        self.search_timer.Stop()
        self.apply_filters()
        self.focus_list()

    def focus_search(self):
        self.search.SetFocus()
        self.search.SelectAll()

    def focus_list(self):
        self.list.SetFocus()

    def goto_unread(self, step: int):
        n = len(self.rows)
        start = self.list.GetFirstSelected()
        idx = start if start >= 0 else (-1 if step > 0 else 0)
        for _ in range(n):
            idx = (idx + step) % n
            if not self.rows[idx]["is_read"]:
                self.list.SetFocus()
                if start >= 0:
                    self.list.Select(start, False)
                self.list.Select(idx)
                self.list.Focus(idx)
                self.list.EnsureVisible(idx)
                return
        self.announce("Não há notícias não lidas na lista.", COMMAND, interrupt=True)

    # ------------------------------------------------------------------
    # Teclado e menus
    # ------------------------------------------------------------------
    def on_key(self, event):
        # Estas teclas só valem dentro da lista; antes elas "roubavam" o Espaço da
        # caixa de busca e o Enter dos botões. Os demais atalhos são aceleradores
        # de menu, que o Windows e os leitores de tela descobrem pela barra de menus.
        if self.FindFocus() is self.list:
            code, mods = event.GetKeyCode(), event.GetModifiers()
            if mods == wx.MOD_NONE and code in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
                self.read_selected()
                return
            if mods == wx.MOD_NONE and code == wx.WXK_SPACE:
                self.toggle_read()
                return
            if mods == wx.MOD_CONTROL and code == ord("C"):
                self.copy_selected()
                return
        event.Skip()

    def on_context_menu(self, event):
        index = self.list.GetFirstSelected()
        if index < 0:
            return
        row = self.rows[index]
        menu = wx.Menu()
        self._item(menu, "Ler notícia", lambda e: self.read_selected())
        self._item(menu, "Abrir no navegador", lambda e: self.open_in_browser())
        self._item(menu, "Marcar como não lida" if row["is_read"] else "Marcar como lida", lambda e: self.toggle_read())
        self._item(menu, "Copiar título e link", lambda e: self.copy_selected())
        self._item(menu, "Copiar link", lambda e: self.copy_selected(link_only=True))
        pos = event.GetPosition()
        if pos == wx.DefaultPosition:  # aberto pelo teclado: abre sobre o item, não onde está o mouse
            rect = self.list.GetItemRect(index)
            pos = wx.Point(rect.x + 20, rect.y + rect.height)
        else:
            pos = self.list.ScreenToClient(pos)
        self.list.PopupMenu(menu, pos)
        menu.Destroy()

    # ------------------------------------------------------------------
    # Ações sobre notícias
    # ------------------------------------------------------------------
    def read_selected(self):
        index = self.list.GetFirstSelected()
        if not (0 <= index < len(self.rows)):
            self.announce("Nenhuma notícia selecionada.", COMMAND, interrupt=True)
            return
        dialog = ReaderDialog(self, list(self.rows), index)
        try:
            dialog.ShowModal()
            url = dialog.current["url"]
        finally:
            dialog.Destroy()
        self.refresh(select_url=url)
        self.list.SetFocus()

    def open_in_browser(self):
        row = self.selected_row()
        if row is None:
            return
        self.db.set_read(row["url"], True)
        webbrowser.open(row["url"])
        self.refresh(select_url=row["url"])

    def toggle_read(self):
        row = self.selected_row()
        if row is None:
            return
        new_state = not row["is_read"]
        self.db.set_read(row["url"], new_state)
        self.refresh(select_url=row["url"])
        self.announce("Marcada como lida." if new_state else "Marcada como não lida.", COMMAND, interrupt=True)

    def copy_text(self, text: str, what: str):
        if wx.TheClipboard.Open():
            try:
                wx.TheClipboard.SetData(wx.TextDataObject(text))
                wx.TheClipboard.Flush()
            finally:
                wx.TheClipboard.Close()
            self.announce(f"{what} copiado.", COMMAND, interrupt=True)
        else:
            self.announce("Não foi possível acessar a área de transferência.", COMMAND, interrupt=True)

    def copy_selected(self, link_only: bool = False):
        row = self.selected_row()
        if row is None:
            return
        if link_only:
            self.copy_text(row["url"], "Link")
        else:
            self.copy_text(f"{row['title']}\n{row['url']}", "Título e link")

    def mark_all_read(self):
        answer = wx.MessageBox("Marcar todas as notícias como lidas?", APP_NAME, wx.YES_NO | wx.ICON_QUESTION, self)
        if answer == wx.YES:
            self.db.mark_all_read()
            self.refresh()
            self.announce("Todas as notícias foram marcadas como lidas.", COMMAND, interrupt=True)

    def mark_region_read(self):
        region = self.selected_region()
        if region == ALL:
            self.mark_all_read()
            return
        changed = self.db.mark_region_read(region)
        self.refresh()
        self.announce(f"{plural(changed, 'notícia marcada', 'notícias marcadas')} como lida em {region}.",
                      COMMAND, interrupt=True)

    # ------------------------------------------------------------------
    # Sincronização
    # ------------------------------------------------------------------
    def restart_sync_timer(self):
        self.sync_timer.Stop()
        if self.settings.interval_minutes > 0:
            self.sync_timer.Start(self.settings.interval_minutes * 60 * 1000)

    def on_sync(self, _event=None, automatic: bool = False):
        if self.syncing:  # o menu da bandeja também chama isto: evita duas threads gravando
            if not automatic:
                self.announce("Já existe uma sincronização em andamento.", COMMAND, interrupt=True)
            return
        self.syncing = True
        self.sync.Enable(False)
        self.set_status("Sincronizando…")
        LOGGER.info("Sincronização %s iniciada", "automática" if automatic else "manual")
        if not automatic:
            self.announce("Sincronização iniciada.", IMPORTANT)
        lang = self.settings.site_lang
        threading.Thread(target=self._sync_worker, args=(automatic, lang), name="sync", daemon=True).start()

    def _sync_worker(self, automatic: bool, lang: str):
        total = 0
        new_count = 0
        ok = False
        notify_unread = self.notify_unread_after_sync
        self.notify_unread_after_sync = False
        try:
            was_empty = self.db.count() == 0

            def save_batch(batch):
                nonlocal total, new_count
                new_count += self.db.upsert_many(batch)
                total += len(batch)
                call_ui(self.set_status, f"Sincronizando… {total} notícias coletadas até agora.")
                if not automatic:
                    self.announce(f"{total} coletadas.", PROGRESS)

            # Sincronizações automáticas só olham as páginas mais recentes.
            max_pages = 2 if (automatic and not was_empty) else 20
            articles = fetch_all(max_pages=max_pages, on_batch=save_batch, lang=lang)
            self.db.set_meta("last_sync", now_utc_string())
            self.db.prune(365)
            message = (f"Sincronização concluída. {plural(len(articles), 'notícia coletada', 'notícias coletadas')}, "
                       f"{plural(new_count, 'nova', 'novas')}.")
            LOGGER.info(message)
            ok = True
            if notify_unread:
                call_ui(self.notify_unread_count)
            elif new_count and not was_empty:
                call_ui(self.notify_new_articles, new_count)
        except Exception as exc:
            LOGGER.exception("Erro ao sincronizar")
            message = f"Erro ao sincronizar: {exc}"
        finally:
            self.db.close_thread()
        call_ui(self.finish_sync, ok, message, automatic, total)

    def finish_sync(self, ok: bool, message: str, automatic: bool, saved: int):
        self.syncing = False
        self.sync.Enable(True)
        self.refresh()
        self.set_status(message)
        if ok:
            self.failures, self.last_error = 0, ""
            if not automatic:
                self.announce(message, IMPORTANT, interrupt=True)
            return
        self.failures += 1
        self.last_error = message
        if automatic:
            if self.failures in (1, 3):  # avisa na primeira falha e de novo na terceira, sem spam
                self.notify("Falha na sincronização automática. Abra o programa e use Ctrl+E para detalhes.")
            return
        self.announce(f"A sincronização encontrou um erro. {plural(saved, 'notícia já foi salva', 'notícias já foram salvas')}.",
                      IMPORTANT, interrupt=True)
        if self.IsShown():
            dialog = wx.MessageDialog(self, f"{message}\n\nOs detalhes técnicos estão no arquivo de log.",
                                      APP_NAME, wx.YES_NO | wx.ICON_ERROR)
            dialog.SetYesNoLabels("Abrir pasta de &logs", "&Fechar")
            if dialog.ShowModal() == wx.ID_YES:
                open_folder(data_dir())
            dialog.Destroy()
            self.list.SetFocus()
        else:
            self.notify(message)

    # ------------------------------------------------------------------
    # Notificações
    # ------------------------------------------------------------------
    def notify(self, message: str):
        if not self.settings.notifications or self._closing:
            return
        try:
            if self.tray is not None and hasattr(wx.adv.NotificationMessage, "UseTaskBarIcon"):
                # Reaproveita o ícone da bandeja em vez de criar um ícone interno
                # que pode ficar "fantasma" se o programa fechar com o aviso aberto.
                wx.adv.NotificationMessage.UseTaskBarIcon(self.tray)
            note = wx.adv.NotificationMessage(APP_NAME, message, parent=self)
            note.Show(timeout=wx.adv.NotificationMessage.Timeout_Auto)
            self._notification = note  # mantém referência enquanto o aviso é exibido
        except Exception:
            LOGGER.exception("Falha ao exibir notificação")

    def notify_new_articles(self, count: int):
        self.notify(f"{count} nova notícia encontrada." if count == 1 else f"{count} novas notícias encontradas.")

    def notify_unread_count(self):
        count = self.db.unread_count()
        if count:
            self.notify(f"Você tem {count} notícia não lida." if count == 1 else f"Você tem {count} notícias não lidas.")

    # ------------------------------------------------------------------
    # Opções, ajuda e primeira execução
    # ------------------------------------------------------------------
    def show_settings(self):
        dialog = SettingsDialog(self, self.settings, self.announcer.active_output_name())
        try:
            if dialog.ShowModal() != wx.ID_OK:
                return
            new = dialog.result()
            autostart = dialog.autostart_wanted()
        finally:
            dialog.Destroy()
        old, self.settings = self.settings, new
        self.settings.save(self.settings_path)
        if startup.supported() and autostart != startup.is_enabled():
            if not startup.set_enabled(autostart):
                self.announce("Não foi possível alterar a inicialização com o Windows.", COMMAND)
        self.restart_sync_timer()
        if new.status_first != old.status_first:
            self.build_columns()
        if (new.hotkey, new.hotkey_enabled) != (old.hotkey, old.hotkey_enabled):
            self.apply_hotkey()
        self.refresh()
        self.announce("Opções salvas.", COMMAND, interrupt=True)

    def show_shortcuts(self, title: str = "Atalhos de teclado"):
        dialog = TextDialog(self, title, shortcuts_text(self.settings), label="&Atalhos")
        dialog.ShowModal()
        dialog.Destroy()
        self.list.SetFocus()

    def show_about(self):
        wx.MessageBox(
            f"{APP_NAME} {__version__}\n\nAplicativo desktop acessível para acompanhar as notícias do JW.ORG.\n"
            "Projeto pessoal e independente: não é um produto oficial das Testemunhas de Jeová.",
            "Sobre", wx.OK | wx.ICON_INFORMATION, self)

    def first_run(self):
        """Primeira execução com a janela visível: apresenta os atalhos e já sincroniza."""
        if self.settings.first_run_done:
            return
        self.settings.first_run_done = True
        self.settings.save(self.settings_path)
        self.show_shortcuts("Bem-vindo ao JW Notícias — atalhos de teclado")
        if self.db.count() == 0:
            self.on_sync()

    # ------------------------------------------------------------------
    # Bandeja, atalho global e ciclo de vida
    # ------------------------------------------------------------------
    def apply_hotkey(self):
        if not hasattr(self, "RegisterHotKey"):
            return
        try:
            self.UnregisterHotKey(HOTKEY_ID)
        except Exception:
            LOGGER.debug("UnregisterHotKey ignorado", exc_info=True)
        if not self.settings.hotkey_enabled:
            return
        try:
            spec = parse_hotkey(self.settings.hotkey)
            mods = ((wx.MOD_CONTROL if spec["ctrl"] else 0) | (wx.MOD_ALT if spec["alt"] else 0)
                    | (wx.MOD_SHIFT if spec["shift"] else 0) | (wx.MOD_WIN if spec["win"] else 0))
            registered = self.RegisterHotKey(HOTKEY_ID, mods, spec["vk"])
        except Exception:
            LOGGER.exception("Falha ao registrar o atalho global")
            registered = False
        if not registered:
            LOGGER.warning("Atalho global %s não pôde ser registrado", self.settings.hotkey)
            self.set_status(f"Não foi possível registrar o atalho global {self.settings.hotkey} (talvez já esteja em uso).")
            self.announce(f"Não foi possível registrar o atalho global {self.settings.hotkey}.", COMMAND)

    def on_hotkey(self, _event):
        if self.IsShown() and not self.IsIconized() and self.IsActive():
            self.hide_to_tray()
        else:
            self.restore_from_tray()

    def on_iconize(self, event):
        if event.IsIconized() and self.tray is not None and not self._closing:
            wx.CallAfter(self.Hide)  # minimizar = ir para a bandeja
        event.Skip()

    def hide_to_tray(self):
        if self.tray is not None:
            self.Hide()
            self.announce("Janela enviada para a bandeja.", COMMAND)
        else:
            self.Iconize(True)

    def restore_from_tray(self):
        if self._closing:
            return
        if self.IsIconized():
            self.Iconize(False)
        self.Show()
        self.Raise()
        self.list.SetFocus()

    def on_close(self, event):
        if (self.settings.close_to_tray and not self._exiting and self.tray is not None
                and event.CanVeto()):
            event.Veto()
            self.hide_to_tray()
            return
        self.shutdown()
        event.Skip()

    def exit_app(self):
        self._exiting = True
        self.Close(True)

    def shutdown(self):
        """Libera o ícone da bandeja e para as tarefas. Seguro para chamar mais de uma vez."""
        if self._closing:
            return
        self._closing = True
        shutting_down.set()
        for timer in (self.sync_timer, self.search_timer):
            try:
                timer.Stop()
            except Exception:
                LOGGER.debug("Falha ao parar o timer", exc_info=True)
        try:
            self.UnregisterHotKey(HOTKEY_ID)
        except Exception:
            LOGGER.debug("Falha ao liberar o atalho global", exc_info=True)
        tray, self.tray = self.tray, None
        if tray is not None:
            try:
                tray.RemoveIcon()
                tray.Destroy()
            except Exception:
                LOGGER.debug("Falha ao remover o ícone da bandeja", exc_info=True)
