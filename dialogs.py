"""Diálogos: leitura da notícia, opções e ajuda de atalhos.

Todos seguem as mesmas regras de acessibilidade: o rótulo de cada campo é um
StaticText imediatamente antes dele (é assim que os leitores de tela associam
o nome), todos os botões têm mnemônicos (Alt+letra) e Esc fecha.
"""
from __future__ import annotations

import logging
import threading
import webbrowser
from dataclasses import replace

import wx

import startup
from appinfo import APP_NAME, data_dir, open_folder
from jw_feed import SITE_LANGS, fetch_article_text
from settings import Settings, format_hotkey, parse_hotkey
from textutil import display_date, display_detection
from uithread import call_ui

LOGGER = logging.getLogger(__name__)


def shortcuts_text(settings: Settings) -> str:
    try:
        hotkey = format_hotkey(parse_hotkey(settings.hotkey)) if settings.hotkey_enabled else None
    except ValueError:
        hotkey = None
    tray = ("Minimizar envia o programa para a bandeja. Para voltar: clique no ícone, "
            + (f"use {hotkey} (atalho global), " if hotkey else "")
            + "ou abra o programa de novo (a janela aparece).")
    return "\n".join([
        "Na lista de notícias:",
        "  Enter: ler a notícia (resumo e texto completo)",
        "  Ctrl+Enter: abrir no navegador",
        "  Espaço: alternar lida / não lida",
        "  Ctrl+C: copiar título e link",
        "  Tecla Aplicativos ou Shift+F10: menu da notícia",
        "  F8 e Shift+F8: próxima e anterior não lida",
        "",
        "Em qualquer lugar da janela:",
        "  Ctrl+S: sincronizar",
        "  Ctrl+F: ir para a busca (Enter na busca leva à lista)",
        "  Ctrl+L: ir para a lista",
        "  Ctrl+E: falar o status (exibidas, não lidas, última sincronização)",
        "  Ctrl+Shift+R: marcar todas como lidas",
        "  Ctrl+O: opções",
        "  Ctrl+M: enviar para a bandeja",
        "  Ctrl+Q: sair",
        "  F1: esta ajuda",
        "  Alt+B, Alt+R, Alt+M, Alt+O, Alt+N: buscar, região, mostrar, ordenar, lista",
        "",
        "Ao ler uma notícia:",
        "  Alt+A e Alt+P: anterior e próxima",
        "  Alt+N: abrir no navegador; Alt+C: baixar o texto completo",
        "  Alt+L: marcar como lida ou não lida; Alt+I: copiar o link",
        "  Esc: fechar",
        "",
        tray,
    ])


class TextDialog(wx.Dialog):
    """Texto somente leitura num campo focável, para leitores de tela lerem linha a linha."""

    def __init__(self, parent, title: str, text: str, label: str = "&Conteúdo"):
        super().__init__(parent, title=title, size=(760, 560), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(wx.StaticText(self, label=label), 0, wx.ALL, 8)
        self.text = wx.TextCtrl(self, value=text, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2)
        sizer.Add(self.text, 1, wx.LEFT | wx.RIGHT | wx.EXPAND, 8)
        close = wx.Button(self, wx.ID_CANCEL, "&Fechar")
        sizer.Add(close, 0, wx.ALL | wx.ALIGN_RIGHT, 8)
        self.SetSizer(sizer)
        self.text.SetInsertionPoint(0)
        self.text.SetFocus()


class ReaderDialog(wx.Dialog):
    """Leitura de uma notícia dentro do app, sem tirar o foco para o navegador."""

    def __init__(self, frame, rows, index: int):
        super().__init__(frame, title="Notícia", size=(820, 620), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.frame = frame
        self.rows = rows
        self.index = index
        self.is_read = True
        self._closed = False

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(wx.StaticText(self, label="&Texto da notícia"), 0, wx.ALL, 8)
        self.text = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2)
        sizer.Add(self.text, 1, wx.LEFT | wx.RIGHT | wx.EXPAND, 8)

        buttons = wx.WrapSizer(wx.HORIZONTAL)
        self.prev_btn = wx.Button(self, label="&Anterior")
        self.next_btn = wx.Button(self, label="&Próxima")
        self.browser_btn = wx.Button(self, label="Abrir no &navegador")
        self.full_btn = wx.Button(self, label="Texto &completo")
        self.toggle_btn = wx.Button(self, label="Marcar como não &lida")
        self.link_btn = wx.Button(self, label="Copiar l&ink")
        self.close_btn = wx.Button(self, wx.ID_CANCEL, "&Fechar")
        for b in (self.prev_btn, self.next_btn, self.browser_btn, self.full_btn, self.toggle_btn,
                  self.link_btn, self.close_btn):
            buttons.Add(b, 0, wx.ALL, 4)
        sizer.Add(buttons, 0, wx.ALL | wx.EXPAND, 4)
        self.SetSizer(sizer)

        self.prev_btn.Bind(wx.EVT_BUTTON, lambda e: self.go(-1))
        self.next_btn.Bind(wx.EVT_BUTTON, lambda e: self.go(1))
        self.browser_btn.Bind(wx.EVT_BUTTON, self.on_browser)
        self.full_btn.Bind(wx.EVT_BUTTON, self.on_full_text)
        self.toggle_btn.Bind(wx.EVT_BUTTON, self.on_toggle)
        self.link_btn.Bind(wx.EVT_BUTTON, lambda e: self.frame.copy_text(self.current["url"], "Link"))
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.load(index)

    @property
    def current(self):
        return self.rows[self.index]

    # -- conteúdo ----------------------------------------------------------
    def _compose(self, row, body: str | None) -> str:
        date = display_date(row["published"]) or f"sem data (detectada em {display_detection(row['first_seen'])})"
        lines = [f"Título: {row['title']}", f"Data: {date}", f"Região: {row['region'] or 'Geral'}",
                 f"Link: {row['url']}", ""]
        if body:
            lines += ["Texto completo:", "", body]
        else:
            lines += ["Resumo:", "", row["summary"] or "Esta notícia não tem resumo.",
                      "", "Use Alt+C para baixar o texto completo."]
        return "\n".join(lines)

    def load(self, index: int) -> None:
        self.index = index
        row = self.current
        self.frame.db.set_read(row["url"], True)
        self.is_read = True
        body = self.frame.db.get_body(row["url"])
        self.text.SetValue(self._compose(row, body))
        self.text.SetInsertionPoint(0)
        self.SetTitle(f"Notícia {index + 1} de {len(self.rows)}")
        self.prev_btn.Enable(index > 0)
        self.next_btn.Enable(index < len(self.rows) - 1)
        self.full_btn.Enable(not body)
        self._update_toggle_label()
        self.text.SetFocus()  # a leitura continua de onde o leitor de tela espera

    def _update_toggle_label(self) -> None:
        self.toggle_btn.SetLabel("Marcar como não &lida" if self.is_read else "Marcar como &lida")

    # -- ações -------------------------------------------------------------
    def go(self, step: int) -> None:
        target = self.index + step
        if 0 <= target < len(self.rows):
            self.load(target)
            self.frame.announcer.say(f"Notícia {target + 1} de {len(self.rows)}. {self.current['title']}",
                                     level="command", interrupt=True)

    def on_browser(self, _event) -> None:
        webbrowser.open(self.current["url"])

    def on_toggle(self, _event) -> None:
        self.is_read = not self.is_read
        self.frame.db.set_read(self.current["url"], self.is_read)
        self._update_toggle_label()
        self.frame.announcer.say("Marcada como lida." if self.is_read else "Marcada como não lida.",
                                 level="command", interrupt=True)

    def on_full_text(self, _event) -> None:
        url = self.current["url"]
        self.full_btn.Enable(False)
        self.frame.announcer.say("Baixando o texto completo.", level="command", interrupt=True)
        threading.Thread(target=self._fetch_worker, args=(url,), name="article", daemon=True).start()

    def _fetch_worker(self, url: str) -> None:
        text, error = None, None
        try:
            text = fetch_article_text(url)
            self.frame.db.set_body(url, text)
        except Exception as exc:
            LOGGER.exception("Falha ao baixar o texto completo")
            error = str(exc) or exc.__class__.__name__
        finally:
            self.frame.db.close_thread()
        call_ui(self._fetched, url, error)

    def _fetched(self, url: str, error: str | None) -> None:
        if self._closed or self.current["url"] != url:
            return
        if error:
            self.full_btn.Enable(True)
            wx.MessageBox(f"Não foi possível baixar o texto completo.\n\n{error}", APP_NAME,
                          wx.OK | wx.ICON_ERROR, self)
            return
        self.load(self.index)
        self.frame.announcer.say("Texto completo carregado.", level="command", interrupt=True)

    def on_close(self, event) -> None:
        self._closed = True
        event.Skip()


class SettingsDialog(wx.Dialog):
    VOICE_CHOICES = [
        ("auto", "Automática (recomendado)"),
        ("important", "Eventos importantes"),
        ("full", "Completa, com progresso"),
        ("commands", "Só quando eu pedir (Ctrl+E e confirmações)"),
        ("off", "Desligada"),
    ]

    def __init__(self, parent, settings: Settings, detected_output: str):
        super().__init__(parent, title="Opções", style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.original = settings
        grid = wx.FlexGridSizer(cols=2, vgap=8, hgap=12)
        grid.AddGrowableCol(1)

        def row(label, control):
            grid.Add(wx.StaticText(self, label=label), 0, wx.ALIGN_CENTER_VERTICAL)
            grid.Add(control, 1, wx.EXPAND)

        self.interval = wx.SpinCtrl(self, min=0, max=1440, initial=settings.interval_minutes)
        row("&Sincronizar automaticamente a cada (minutos; 0 desativa)", self.interval)

        self.voice = wx.Choice(self, choices=[label for _, label in self.VOICE_CHOICES])
        self.voice.SetSelection(next((i for i, (k, _) in enumerate(self.VOICE_CHOICES) if k == settings.voice_mode), 0))
        row(f"&Voz do programa (saída detectada agora: {detected_output})", self.voice)

        self.langs = list(SITE_LANGS.items())
        self.lang = wx.Choice(self, choices=[label for _, label in self.langs])
        self.lang.SetSelection(next((i for i, (k, _) in enumerate(self.langs) if k == settings.site_lang), 0))
        row("&Idioma do site (notícias já salvas da outra variante continuam na lista)", self.lang)

        self.hotkey_text = wx.TextCtrl(self, value=settings.hotkey)
        row("&Tecla do atalho global (por exemplo Ctrl+Alt+J)", self.hotkey_text)

        box = wx.BoxSizer(wx.VERTICAL)
        self.notifications = wx.CheckBox(self, label="Mostrar &notificações do Windows")
        self.notifications.SetValue(settings.notifications)
        self.status_first = wx.CheckBox(self, label="Mostrar o &estado (lida/não lida) antes do título na lista")
        self.status_first.SetValue(settings.status_first)
        self.close_to_tray = wx.CheckBox(self, label="Fechar a janela (X) envia para a &bandeja em vez de sair")
        self.close_to_tray.SetValue(settings.close_to_tray)
        self.hotkey_enabled = wx.CheckBox(self, label="Usar atalho &global para mostrar ou esconder a janela")
        self.hotkey_enabled.SetValue(settings.hotkey_enabled)
        self.autostart = wx.CheckBox(self, label="Iniciar com o &Windows (minimizado na bandeja)")
        self.autostart.SetValue(startup.is_enabled())
        if not startup.supported():
            self.autostart.Disable()
            self.autostart.SetLabel("Iniciar com o &Windows (disponível só na versão instalada)")
        for c in (self.notifications, self.status_first, self.close_to_tray, self.hotkey_enabled, self.autostart):
            box.Add(c, 0, wx.TOP, 6)

        self.logs_btn = wx.Button(self, label="Abrir pasta de &logs")
        self.logs_btn.Bind(wx.EVT_BUTTON, lambda e: open_folder(data_dir()))
        self.hotkey_enabled.Bind(wx.EVT_CHECKBOX, lambda e: self._sync_hotkey_state())
        self._sync_hotkey_state()

        root = wx.BoxSizer(wx.VERTICAL)
        root.Add(grid, 0, wx.ALL | wx.EXPAND, 12)
        root.Add(box, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, 12)
        root.Add(self.logs_btn, 0, wx.ALL, 12)
        root.Add(self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL), 0, wx.ALL | wx.ALIGN_RIGHT, 12)
        self.SetSizerAndFit(root)
        self.SetMinSize((640, -1))
        self.Fit()
        self.Bind(wx.EVT_BUTTON, self.on_ok, id=wx.ID_OK)
        self.interval.SetFocus()

    def _sync_hotkey_state(self) -> None:
        self.hotkey_text.Enable(self.hotkey_enabled.GetValue())

    def on_ok(self, event) -> None:
        if self.hotkey_enabled.GetValue():
            try:
                parse_hotkey(self.hotkey_text.GetValue())
            except ValueError as exc:
                wx.MessageBox(str(exc), APP_NAME, wx.OK | wx.ICON_WARNING, self)
                self.hotkey_text.SetFocus()
                return
        event.Skip()

    def result(self) -> Settings:
        return replace(
            self.original,
            interval_minutes=self.interval.GetValue(),
            voice_mode=self.VOICE_CHOICES[max(self.voice.GetSelection(), 0)][0],
            site_lang=self.langs[max(self.lang.GetSelection(), 0)][0],
            notifications=self.notifications.GetValue(),
            status_first=self.status_first.GetValue(),
            close_to_tray=self.close_to_tray.GetValue(),
            hotkey_enabled=self.hotkey_enabled.GetValue(),
            hotkey=self.hotkey_text.GetValue().strip() or self.original.hotkey,
        )

    def autostart_wanted(self) -> bool:
        return self.autostart.GetValue()
