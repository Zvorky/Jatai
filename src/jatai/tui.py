"""Textual-based interactive TUI for Jataí."""

import io
import os
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Optional

import typer
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    RichLog,
    Static,
)

MENU_ITEMS: list[tuple[str, str]] = [
    ("0",  "Init Node"),
    ("1",  "Status"),
    ("2",  "Docs Index"),
    ("3",  "Docs Query"),
    ("4",  "Log Latest"),
    ("5",  "Log All"),
    ("6",  "List"),
    ("7",  "Send File"),
    ("8",  "Read File"),
    ("9",  "Unread File"),
    ("10", "Config Get"),
    ("11", "Config Set"),
    ("12", "Remove Node"),
    ("13", "Clear Processed"),
    ("14", "Start Daemon"),
    ("15", "Stop Daemon"),
    ("b",  "Browse Nodes"),
]


def _capture_call(fn, *args) -> str:
    """Call fn(*args) capturing stdout/stderr and returning the combined output."""
    buf = io.StringIO()
    try:
        with redirect_stdout(buf), redirect_stderr(buf):
            fn(*args)
    except typer.Exit:
        pass
    except SystemExit:
        pass
    except Exception as exc:
        buf.write(f"✗ Error: {exc}\n")
    return buf.getvalue()


class _InputModal(ModalScreen):
    """Generic input modal for collecting one or more prompted values.

    Dismisses with ``list[str]`` on confirm or ``None`` on cancel.
    """

    DEFAULT_CSS = """
    _InputModal {
        align: center middle;
    }
    _InputModal > Static {
        width: 64;
        height: auto;
        border: thick $background;
        background: $surface;
        padding: 1 2;
    }
    _InputModal Label.modal-title {
        text-style: bold;
        margin-bottom: 1;
    }
    _InputModal Input {
        margin-bottom: 1;
    }
    _InputModal Horizontal {
        height: auto;
        margin-top: 1;
    }
    _InputModal Button {
        margin-right: 1;
    }
    """

    BINDINGS = [Binding("escape", "dismiss_none", "Cancel")]

    def __init__(self, title: str, fields: list[tuple[str, str]]) -> None:
        super().__init__()
        self._modal_title = title
        self._fields = fields

    def compose(self) -> ComposeResult:
        with Static():
            yield Label(self._modal_title, classes="modal-title")
            for field_label, placeholder in self._fields:
                yield Label(field_label)
                yield Input(placeholder=placeholder)
            with Horizontal():
                yield Button("OK", id="modal-ok", variant="primary")
                yield Button("Cancel", id="modal-cancel")

    def action_dismiss_none(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "modal-ok":
            self.dismiss([w.value for w in self.query(Input)])
        else:
            self.dismiss(None)

    def on_input_submitted(self, _: Input.Submitted) -> None:
        self.dismiss([w.value for w in self.query(Input)])


class _NodeBrowserModal(ModalScreen):
    """Browse registered Jataí nodes and navigate to one by selecting it."""

    DEFAULT_CSS = """
    _NodeBrowserModal {
        align: center middle;
    }
    _NodeBrowserModal > Static {
        width: 80;
        height: auto;
        border: thick $background;
        background: $surface;
        padding: 1 2;
    }
    _NodeBrowserModal Label.modal-title {
        text-style: bold;
        margin-bottom: 1;
    }
    _NodeBrowserModal ListView {
        height: 10;
        margin-bottom: 1;
    }
    _NodeBrowserModal Horizontal {
        height: auto;
        margin-top: 1;
    }
    _NodeBrowserModal Button {
        margin-right: 1;
    }
    """

    BINDINGS = [Binding("escape", "dismiss_none", "Cancel")]

    def __init__(self, nodes: list[tuple[str, str]]) -> None:
        super().__init__()
        self._nodes = nodes

    def compose(self) -> ComposeResult:
        with Static():
            yield Label("Registered Nodes — select to navigate", classes="modal-title")
            if self._nodes:
                lv = ListView()
                for i, (name, path) in enumerate(self._nodes):
                    lv.append(ListItem(Label(f"{name}  {path}"), id=f"nb-{i}"))
                yield lv
            else:
                yield Label("(no nodes registered — use [0] Init Node first)")
            with Horizontal():
                yield Button("Cancel", id="nb-cancel")

    def action_dismiss_none(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id or ""
        if item_id.startswith("nb-"):
            idx = int(item_id[3:])
            _, path = self._nodes[idx]
            self.dismiss(path)


class JataiApp(App):
    """Jataí TUI — interactive operator control plane."""

    TITLE = "Jataí 🐝"
    SUB_TITLE = "TUI (alpha)"

    CSS = """
    Screen {
        layout: horizontal;
    }
    #menu-pane {
        width: 32;
        height: 100%;
        border-right: solid $accent;
    }
    #menu-pane ListView {
        height: 1fr;
    }
    #menu-pane ListItem {
        padding: 0 1;
    }
    #output-pane {
        width: 1fr;
        height: 100%;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("ctrl+c", "quit", "Quit", show=False),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="menu-pane"):
            lv = ListView()
            for key, label in MENU_ITEMS:
                lv.append(ListItem(Label(f"[{key}] {label}"), id=f"cmd-{key}"))
            yield lv
        yield RichLog(id="output-pane", highlight=True, markup=True)
        yield Footer()

    def on_mount(self) -> None:
        cwd = Path.cwd()
        self.sub_title = str(cwd)
        self._output(
            "Welcome to [bold]Jataí TUI[/bold]. "
            "Select an action from the menu and press [bold]Enter[/bold].\n"
            f"Current directory: [italic]{cwd}[/italic]\n"
            "Press [bold]Q[/bold] to quit."
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _output(self, text: str) -> None:
        self.query_one("#output-pane", RichLog).write(text)

    def _run(self, fn, *args) -> None:
        self._output(_capture_call(fn, *args))

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id or ""
        if item_id.startswith("cmd-"):
            self._dispatch(item_id[len("cmd-"):])

    # ------------------------------------------------------------------
    # Command dispatcher
    # ------------------------------------------------------------------

    def _dispatch(self, key: str) -> None:  # noqa: C901 — linear dispatch table
        from jatai.cli.main import (
            clear as clear_cmd,
            config as config_cmd,
            docs as docs_cmd,
            init as init_cmd,
            list_command,
            log as log_cmd,
            read as read_cmd,
            remove as remove_cmd,
            send as send_cmd,
            start as start_cmd,
            status as status_cmd,
            stop as stop_cmd,
            unread as unread_cmd,
        )

        if key == "0":
            def _on_init(result: Optional[list[str]]) -> None:
                if result is not None:
                    raw_path = result[0].strip() or None
                    self._run(init_cmd, raw_path)

            self.push_screen(
                _InputModal("Init Node", [("Path (empty = current dir):", "")]),
                _on_init,
            )

        elif key == "1":
            self._run(status_cmd)

        elif key == "2":
            def _on_docs_inbox(result: Optional[list[str]]) -> None:
                if result is not None:
                    inbox_flag = result[0].strip().lower() in {"1", "y", "yes", "true"}
                    self._run(docs_cmd, None, inbox_flag)

            self.push_screen(
                _InputModal("Docs Index", [("Export to INBOX? (y/n):", "n")]),
                _on_docs_inbox,
            )

        elif key == "3":
            def _on_query(result: Optional[list[str]]) -> None:
                if result is not None:
                    query = result[0].strip() or None
                    inbox_flag = result[1].strip().lower() in {"1", "y", "yes", "true"}
                    self._run(docs_cmd, query, inbox_flag)

            self.push_screen(
                _InputModal("Docs Query", [
                    ("Query:", "search term"),
                    ("Export to INBOX? (y/n):", "n")
                ]),
                _on_query,
            )

        elif key == "4":
            def _on_log_inbox(result: Optional[list[str]]) -> None:
                if result is not None:
                    inbox_flag = result[0].strip().lower() in {"1", "y", "yes", "true"}
                    self._run(log_cmd, False, inbox_flag)

            self.push_screen(
                _InputModal("Log Latest", [("Export to INBOX? (y/n):", "n")]),
                _on_log_inbox,
            )

        elif key == "5":
            def _on_logall_inbox(result: Optional[list[str]]) -> None:
                if result is not None:
                    inbox_flag = result[0].strip().lower() in {"1", "y", "yes", "true"}
                    self._run(log_cmd, True, inbox_flag)

            self.push_screen(
                _InputModal("Log All", [("Export to INBOX? (y/n):", "n")]),
                _on_logall_inbox,
            )

        elif key == "6":
            def _on_scope(result: Optional[list[str]]) -> None:
                if result is not None:
                    self._run(list_command, result[0].strip() or "inbox")

            self.push_screen(
                _InputModal("List", [("Scope (addrs | inbox | outbox):", "inbox")]),
                _on_scope,
            )

        elif key == "7":
            def _on_send(result: Optional[list[str]]) -> None:
                if result is not None:
                    fp = result[0].strip()
                    move = result[1].strip().lower() in {"1", "y", "yes", "true"}
                    self._run(send_cmd, fp, move)

            self.push_screen(
                _InputModal("Send File", [
                    ("File path:", ""),
                    ("Move source file after send? (y/n):", "n"),
                ]),
                _on_send,
            )

        elif key == "8":
            def _on_read(result: Optional[list[str]]) -> None:
                if result is not None:
                    self._run(read_cmd, result[0].strip())

            self.push_screen(
                _InputModal("Read File", [("INBOX file name:", "")]),
                _on_read,
            )

        elif key == "9":
            def _on_unread(result: Optional[list[str]]) -> None:
                if result is not None:
                    self._run(unread_cmd, result[0].strip())

            self.push_screen(
                _InputModal("Unread File", [("INBOX file name:", "")]),
                _on_unread,
            )

        elif key == "10":
            def _on_config_get(result: Optional[list[str]]) -> None:
                if result is not None:
                    key_val = result[0].strip() or None
                    global_flag = result[1].strip().lower() in {"1", "y", "yes", "true"}
                    inbox_flag = result[2].strip().lower() in {"1", "y", "yes", "true"}
                    self._run(config_cmd, "get", key_val, global_flag, inbox_flag)

            self.push_screen(
                _InputModal("Config Get", [
                    ("Key (empty for full config):", ""),
                    ("Global scope? (y/n):", "n"),
                    ("Export to INBOX? (y/n):", "n"),
                ]),
                _on_config_get,
            )

        elif key == "11":
            def _on_config_set(result: Optional[list[str]]) -> None:
                if result is not None:
                    k = result[0].strip()
                    v = result[1].strip()
                    global_flag = result[2].strip().lower() in {"1", "y", "yes", "true"}
                    self._run(config_cmd, k, v, global_flag, False)

            self.push_screen(
                _InputModal("Config Set", [
                    ("Key:", ""),
                    ("Value:", ""),
                    ("Global scope? (y/n):", "n"),
                ]),
                _on_config_set,
            )

        elif key == "12":
            def _on_remove(result: Optional[list[str]]) -> None:
                if result is not None:
                    raw_path = result[0].strip() or None
                    self._run(remove_cmd, raw_path)

            self.push_screen(
                _InputModal("Remove Node", [("Node path (empty = current dir):", "")]),
                _on_remove,
            )

        elif key == "13":
            def _on_clear(result: Optional[list[str]]) -> None:
                if result is not None:
                    clear_read = result[0].strip().lower() not in {"0", "n", "no", "false"}
                    clear_sent = result[1].strip().lower() not in {"0", "n", "no", "false"}
                    self._run(clear_cmd, clear_read, clear_sent)

            self.push_screen(
                _InputModal("Clear Processed", [
                    ("Clear processed INBOX files? (y/n):", "y"),
                    ("Clear processed OUTBOX files? (y/n):", "y"),
                ]),
                _on_clear,
            )

        elif key == "14":
            self._run(start_cmd, False)

        elif key == "15":
            self._run(stop_cmd)

        elif key == "b":
            from jatai.core.registry import Registry as _Registry

            def _node_path_from_data(data: object) -> str:
                # Backward compatibility: legacy registries may map names directly to strings.
                if isinstance(data, dict):
                    path_value = data.get("path", "")
                elif isinstance(data, str):
                    path_value = data
                else:
                    path_value = ""
                return str(path_value).strip()

            try:
                _reg = _Registry()
                _reg.load()
                _nodes = [
                    (name, _node_path_from_data(data))
                    for name, data in sorted(_reg.nodes.items())
                    if _node_path_from_data(data)
                ]
            except FileNotFoundError:
                _nodes = []
            except Exception as exc:
                _nodes = []
                self._output(f"✗ Unable to read registry for browsing: {exc}")

            def _on_browse(result: Optional[str]) -> None:
                if result is not None:
                    try:
                        os.chdir(result)
                        self.sub_title = result
                        self._output(f"✓ Navigated to [bold]{result}[/bold]")
                    except Exception as exc:
                        self._output(f"✗ Cannot navigate to {result}: {exc}")

            self.push_screen(_NodeBrowserModal(_nodes), _on_browse)
