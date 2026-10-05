"""
One-Editor Lite
MIT License

Copyright (c) 2026 Aoan2011

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
import asyncio
import os
import sys
from pathlib import Path

from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.geometry import Offset
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, OptionList, RichLog, Static, TextArea
from textual.widgets.option_list import Option

from lsp import LANG_SERVERS, LspClient, path_to_uri

VERSION = "1.1.0-lite"

# --------------------------------------------------------------------------- #
# 语言识别
# --------------------------------------------------------------------------- #
LANGUAGE_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cc": "cpp",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".swift": "swift",
    ".kt": "kotlin",
}


def detect_language(path) -> str | None:
    return LANGUAGE_MAP.get(Path(path).suffix.lower())


# --------------------------------------------------------------------------- #
# 补全菜单
# --------------------------------------------------------------------------- #
class CompletionMenu(OptionList):
    DEFAULT_CSS = """
    CompletionMenu {
        layer: autocomplete;
        display: none;
        height: auto;
        max-height: 8;
        width: auto;
        min-width: 30;
        max-width: 60;
        border: round $accent;
        background: $surface;
        padding: 0;
    }
    """

    can_focus = False

    def __init__(self):
        super().__init__(id="completion-menu")
        self.items = []

    def show(self, items, offset):
        self.items = items
        self.clear_options()
        for item in items:
            self.add_option(Option(item["label"]))
        self.styles.offset = Offset(offset[0], offset[1])
        self.display = True
        self.highlighted = 0

    def hide(self):
        self.display = False
        self.items = []

    @property
    def visible(self) -> bool:
        return self.display and len(self.items) > 0

    def move_up(self):
        if self.highlighted is not None and self.highlighted > 0:
            self.highlighted -= 1

    def move_down(self):
        if self.highlighted is not None and self.highlighted < self.option_count - 1:
            self.highlighted += 1

    def selected_item(self):
        idx = self.highlighted
        if idx is not None and idx < len(self.items):
            return self.items[idx]
        return None


# --------------------------------------------------------------------------- #
# 编辑器
# --------------------------------------------------------------------------- #
class LiteEditor(TextArea):
    """TextArea 子类：拦截补全菜单的导航按键。"""

    async def _on_key(self, event: events.Key) -> None:
        menu = getattr(self.app, "completion_menu", None)
        if menu is not None and menu.visible:
            if event.key == "up":
                menu.move_up()
                event.prevent_default()
                event.stop()
                return
            if event.key == "down":
                menu.move_down()
                event.prevent_default()
                event.stop()
                return
            if event.key == "tab":
                item = menu.selected_item()
                if item:
                    self.app._insert_completion(item)
                menu.hide()
                event.prevent_default()
                event.stop()
                return
            if event.key == "escape":
                menu.hide()
                event.prevent_default()
                event.stop()
                return
            if event.key == "enter":
                # 回车确认补全
                item = menu.selected_item()
                if item:
                    self.app._insert_completion(item)
                menu.hide()
                event.prevent_default()
                event.stop()
                return
        await super()._on_key(event)


# --------------------------------------------------------------------------- #
# 模态窗口
# --------------------------------------------------------------------------- #
class AboutScreen(ModalScreen):
    CSS = """
    AboutScreen {
        align: center middle;
        background: rgba(0, 0, 0, 0.6);
    }
    #about-box {
        width: 52;
        height: auto;
        background: $surface;
        border: round $accent;
        padding: 1 2;
    }
    #about-box Label {
        width: 100%;
        text-align: center;
        margin: 0 0 1 0;
    }
    #about-title {
        text-style: bold;
        color: $accent;
    }
    #about-box Button {
        width: 100%;
        margin-top: 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Container(id="about-box"):
            yield Label("One-Editor Lite", id="about-title")
            yield Label(f"版本 {VERSION}")
            yield Label("轻量级 · 命令行 · LSP 补全 · 语法检查")
            yield Label("作者: @Aoan2011")
            yield Button("关闭", id="about-close", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "about-close":
            self.dismiss()

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            self.dismiss()


class PathInputScreen(ModalScreen):
    """简易文件路径输入窗口。"""

    CSS = """
    PathInputScreen {
        align: center middle;
        background: rgba(0, 0, 0, 0.6);
    }
    #path-box {
        width: 64;
        height: auto;
        background: $surface;
        border: round $accent;
        padding: 1 2;
    }
    #path-input {
        margin: 1 0;
    }
    #path-box Horizontal {
        height: auto;
    }
    #path-box Button {
        width: 1fr;
        margin: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Container(id="path-box"):
            yield Label("输入文件路径：")
            yield Input(placeholder="/path/to/file.py", id="path-input")
            with Horizontal():
                yield Button("打开", id="path-open", variant="primary")
                yield Button("取消", id="path-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "path-open":
            self._submit()
        else:
            self.dismiss()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._submit()

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            self.dismiss()

    def _submit(self) -> None:
        value = self.query_one("#path-input", Input).value.strip()
        self.dismiss()
        if value:
            self.app.load_path(value)


class DiagnosticsScreen(ModalScreen):
    """语法检查结果列表。"""

    CSS = """
    DiagnosticsScreen {
        align: center middle;
        background: rgba(0, 0, 0, 0.6);
    }
    #diag-box {
        width: 76;
        height: auto;
        max-height: 80%;
        background: $surface;
        border: round $accent;
        padding: 1 2;
    }
    #diag-title {
        width: 100%;
        text-align: center;
        text-style: bold;
        margin: 0 0 1 0;
    }
    #diag-box Button {
        width: 100%;
        height: auto;
        min-height: 1;
        margin: 0 0 1 0;
    }
    """

    def __init__(self, diagnostics):
        super().__init__()
        self.diagnostics = diagnostics

    def compose(self) -> ComposeResult:
        with Container(id="diag-box"):
            yield Label(f"语法检查 ({len(self.diagnostics)})", id="diag-title")
            if not self.diagnostics:
                yield Label("未发现问题 🎉")
            else:
                for i, diag in enumerate(self.diagnostics):
                    severity = diag.get("severity", 1)
                    message = diag.get("message", "")
                    start = diag.get("range", {}).get("start", {})
                    line = start.get("line", 0) + 1
                    col = start.get("character", 0) + 1
                    icon = "🔴" if severity <= 1 else "🟡"
                    btn = Button(f"{icon} 行 {line}:{col}   {message}", id=f"diag-{i}")
                    btn._target_line = line - 1
                    btn._target_col = col - 1
                    yield btn
            yield Button("关闭", id="diag-close", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid == "diag-close":
            self.dismiss()
        elif bid.startswith("diag-"):
            line = getattr(event.button, "_target_line", 0)
            col = getattr(event.button, "_target_col", 0)
            self.dismiss()
            self.app.editor.cursor_location = (line, col)
            self.app.editor.focus()


# --------------------------------------------------------------------------- #
# 主程序
# --------------------------------------------------------------------------- #
class OneEditorLite(App):
    TITLE = "One-Editor Lite"

    CSS = """
    Screen {
        background: $surface;
    }

    #top-bar {
        height: 1;
        background: $primary;
        color: $text;
        dock: top;
    }

    #top-title {
        width: 1fr;
        content-align: left middle;
        padding: 0 1;
        text-style: bold;
    }

    #top-bar Button {
        height: 1;
        min-width: 7;
        width: auto;
        border: none;
        background: $primary;
        color: $text;
        padding: 0 1;
        margin: 0;
        content-align: center middle;
    }

    #top-bar Button:hover {
        background: $accent;
    }

    #editor-container {
        height: 1fr;
        layers: base autocomplete;
    }

    #editor {
        height: 1fr;
        border: none;
        background: $surface;
    }
    #editor #line-numbers {
        background: $panel;
        color: $text-muted;
        padding: 0 1;
    }
    #output-panel {
        height: 10;
        display: none;
        border-top: solid $primary;
        background: $surface;
    }

    #output-title {
        height: 1;
        background: $panel;
        color: $text;
        padding: 0 1;
    }

    #output-log {
        height: 1fr;
        background: $surface;
        border: none;
    }

    #command-bar {
        height: 3;
        display: none;
        background: $surface;
        padding: 0 1;
        border-top: solid $primary;
    }

    #command-bar Label {
        width: auto;
        content-align: left middle;
        padding: 0 1;
        color: $accent;
        text-style: bold;
    }

    #command-bar Input {
        width: 1fr;
    }

    #status-bar {
        height: 1;
        background: $primary;
        color: $text;
        padding: 0 1;
        dock: bottom;
    }
    """

    BINDINGS = [
        Binding("ctrl+s", "save", "保存"),
        Binding("ctrl+o", "open_file", "打开"),
        Binding("f5", "run_command", "命令行"),
        Binding("f8", "show_diagnostics", "语法检查"),
        Binding("ctrl+space", "force_completion", "补全"),
        Binding("ctrl+q", "quit_app", "退出"),
    ]

    def __init__(self, filepath: str | None = None):
        super().__init__()
        self.filepath: Path | None = None
        self._pending_path = filepath
        self.lsp = LspClient()
        self.lsp.set_diagnostics_callback(self._on_diagnostics)
        self.current_language: str | None = None
        self.diagnostics: list = []
        self._completion_timer = None
        self._modified = False
        self._just_loaded = False

    # ------------------------------------------------------------------ #
    # 界面构建
    # ------------------------------------------------------------------ #
    def compose(self) -> ComposeResult:
        with Horizontal(id="top-bar"):
            yield Label("One-Editor Lite", id="top-title")
            yield Button("关于", id="btn-about")
            yield Button("✓", id="btn-save")
            yield Button("×", id="btn-quit")

        with Container(id="editor-container"):
            self.editor = LiteEditor(id="editor")
            yield self.editor
            self.completion_menu = CompletionMenu()
            yield self.completion_menu

        with Container(id="output-panel"):
            yield Static("命令输出", id="output-title")
            self.output_log = RichLog(id="output-log", highlight=False, markup=False)
            yield self.output_log

        with Horizontal(id="command-bar"):
            yield Label("$")
            yield Input(placeholder="输入命令并回车执行...", id="command-input")

        yield Static("就绪", id="status-bar")

    # ------------------------------------------------------------------ #
    # 生命周期
    # ------------------------------------------------------------------ #
    def on_mount(self) -> None:
        self.editor.indent_width = 4
        self.editor.tab_behavior = "indent"
        self.editor.show_line_numbers = True
        self.editor.focus()

        if self._pending_path:
            self.load_path(self._pending_path)
            self._pending_path = None

        self.update_status()

    async def on_unmount(self) -> None:
        try:
            if self.lsp.running:
                await self.lsp.stop()
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # 文件加载
    # ------------------------------------------------------------------ #
    def load_path(self, path: str) -> None:
        p = Path(path).expanduser()
        if not p.is_absolute():
            p = (Path.cwd() / p).resolve()
        if not p.exists() or not p.is_file():
            self.notify(f"文件不存在: {path}", severity="error")
            return
        self.load_file(p)

    def load_file(self, path: Path) -> None:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception as exc:  # noqa: BLE001
            self.notify(f"无法读取文件: {exc}", severity="error")
            return

        self.filepath = path.resolve()
        self._just_loaded = True
        self.editor.text = text
        self._modified = False

        lang = detect_language(str(path))
        self.editor.language = lang  # 语法高亮

        self.title = f"{path.name} — One-Editor Lite"
        self.diagnostics = []
        self.run_worker(self._start_lsp(), exclusive=True, group="lsp")
        self.update_status()
        self.notify(f"已打开: {path.name}", severity="information")

    # ------------------------------------------------------------------ #
    # LSP
    # ------------------------------------------------------------------ #
    async def _start_lsp(self) -> None:
        if not self.filepath:
            return

        lang = detect_language(str(self.filepath))
        if not lang or lang not in LANG_SERVERS:
            if self.lsp.running:
                await self.lsp.stop()
            self.current_language = None
            self.update_status()
            return

        if self.lsp.running and self.current_language == lang:
            self.lsp.did_open(str(self.filepath), self.editor.text)
            self.update_status()
            return

        await self.lsp.stop()
        ok = await self.lsp.start(lang, str(self.filepath.parent))
        if ok:
            self.current_language = lang
            self.lsp.did_open(str(self.filepath), self.editor.text)
            self.notify(
                f"LSP 已启动: {LANG_SERVERS[lang][0]}", severity="information"
            )
        else:
            self.current_language = None
            self.notify(
                f"LSP 启动失败（未安装 {LANG_SERVERS[lang][0]}？）",
                severity="warning",
            )
        self.update_status()

    def _on_diagnostics(self, uri: str, diagnostics: list) -> None:
        if not self.filepath:
            return
        if uri != path_to_uri(str(self.filepath)):
            return
        self.diagnostics = diagnostics or []
        self.update_status()

    # ------------------------------------------------------------------ #
    # 状态栏
    # ------------------------------------------------------------------ #
    def update_status(self, **_kwargs) -> None:
        name = self.filepath.name if self.filepath else "未命名"
        mark = " ●" if self._modified else ""

        row, col = self.editor.cursor_location
        line = row + 1
        column = col + 1
        total = len(self.editor.text.splitlines()) or 1

        lang = self.current_language or "纯文本"

        if self.current_language:
            server = LANG_SERVERS.get(self.current_language, ["?"])[0]
            lsp_state = "已连接" if self.lsp.running else "未连接"
            lsp_text = f"{server} ({lsp_state})"
        else:
            lsp_text = "—"

        errors = sum(1 for d in self.diagnostics if d.get("severity", 1) <= 1)
        warnings = sum(1 for d in self.diagnostics if d.get("severity", 1) == 2)

        self.query_one("#status-bar", Static).update(
            f"{name}{mark}   |   {lang}   |   行 {line}/{total}  列 {column}"
            f"   |   LSP: {lsp_text}   |   🔴 {errors}  🟡 {warnings}"
        )

    # ------------------------------------------------------------------ #
    # 事件
    # ------------------------------------------------------------------ #
    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if event.text_area is not self.editor:
            return
        if self._just_loaded:
            self._just_loaded = False
            self._modified = False
            self.update_status()
            return
        self._modified = True
        self.update_status()
        self._schedule_completion()

    def on_text_area_selection_changed(
        self, event: TextArea.SelectionChanged
    ) -> None:
        if event.text_area is self.editor:
            self.update_status()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn-about":
            self.push_screen(AboutScreen())
        elif bid == "btn-save":
            self.action_quit_app()
        elif bid == "btn-quit":
            self.action_quit_app()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "command-input":
            return
        cmd = event.value.strip()
        event.input.value = ""
        if cmd:
            self.run_worker(self._execute_command(cmd), exclusive=False, group="cmd")

    # ------------------------------------------------------------------ #
    # 补全
    # ------------------------------------------------------------------ #
    def _schedule_completion(self) -> None:
        if self._completion_timer:
            self._completion_timer.stop()
        self._completion_timer = self.set_timer(0.15, self._trigger_completion)

    def _trigger_completion(self) -> None:
        self._completion_timer = None
        if not self.lsp.running or not self.current_language:
            return

        ed = self.editor
        row, col = ed.cursor_location
        lines = ed.text.splitlines()
        if row >= len(lines) or col == 0:
            self.completion_menu.hide()
            return

        ch = lines[row][col - 1]
        if not (ch.isalnum() or ch in ("_", ".")):
            self.completion_menu.hide()
            return

        self.lsp.did_change(ed.text)
        self.run_worker(
            self._fetch_completions(row, col), exclusive=True, group="completion"
        )

    async def _fetch_completions(self, row: int, col: int) -> None:
        items = await self.lsp.complete(row, col)
        if not items:
            self.completion_menu.hide()
            return

        try:
            cursor_offset = self.editor.cursor_screen_offset
            container_region = self.query_one("#editor-container").region
            x = cursor_offset.x - container_region.x
            y = cursor_offset.y - container_region.y + 1
        except Exception:
            x, y = 5, 5

        self.completion_menu.show(items, (x, y))

    def _insert_completion(self, item) -> None:
        ed = self.editor
        self.completion_menu.hide()

        additional = item.get("additionalTextEdits")
        if additional:
            for edit in reversed(additional):
                rng = edit.get("range", {})
                start = rng.get("start", {})
                end = rng.get("end", {})
                ed.replace(
                    edit.get("newText", ""),
                    (start.get("line", 0), start.get("character", 0)),
                    (end.get("line", 0), end.get("character", 0)),
                )

        insert = item.get("insertText") or item.get("label", "")
        row, col = ed.cursor_location
        lines = ed.text.splitlines()
        line = lines[row] if row < len(lines) else ""

        word_start = col
        while word_start > 0 and (
            line[word_start - 1].isalnum() or line[word_start - 1] == "_"
        ):
            word_start -= 1

        clean = insert.split("(")[0] if "(" in insert else insert
        ed.replace(clean, (row, word_start), (row, col))
        ed.focus()

    # ------------------------------------------------------------------ #
    # 动作
    # ------------------------------------------------------------------ #
    def action_save(self) -> None:
        if not self.filepath:
            self.notify("没有文件路径，无法保存", severity="warning")
            return
        try:
            self.filepath.write_text(self.editor.text, encoding="utf-8")
            self._modified = False
            self.update_status()
            self.notify(f"已保存: {self.filepath.name}", severity="information")
        except Exception as exc:  # noqa: BLE001
            self.notify(f"保存失败: {exc}", severity="error")
    def _save_and_quit(self) -> None:
    # 有路径就写盘，没路径就提示一下但依然退出
        if self.filepath:
            try:
                self.filepath.write_text(self.editor.text, encoding="utf-8")
                self._modified = False
                self.update_status()
                self.notify(f"已保存: {self.filepath.name}", severity="information")
            except Exception as exc:  # noqa: BLE001
                self.notify(f"保存失败: {exc}", severity="error")
                # 保存失败时不退出，避免丢数据
                return
        self.run_worker(self._async_quit(), exclusive=True, group="quit")

    def action_open_file(self) -> None:
        self.push_screen(PathInputScreen())

    def action_run_command(self) -> None:
        self.query_one("#command-bar").display = True
        self.query_one("#command-input", Input).focus()

    def action_show_diagnostics(self) -> None:
        if not self.lsp.running:
            self.notify("LSP 未运行，无法进行语法检查", severity="warning")
            return
        self.push_screen(DiagnosticsScreen(self.diagnostics))

    def action_force_completion(self) -> None:
        if not self.lsp.running:
            self.notify("LSP 未运行，补全不可用", severity="warning")
            return
        ed = self.editor
        self.lsp.did_change(ed.text)
        row, col = ed.cursor_location
        self.run_worker(
            self._fetch_completions(row, col), exclusive=True, group="completion"
        )

    def action_quit_app(self) -> None:
        self.run_worker(self._async_quit(), exclusive=True, group="quit")

    async def _async_quit(self) -> None:
        try:
            if self.lsp.running:
                await self.lsp.stop()
        except Exception:
            pass
        self.exit()

    # ------------------------------------------------------------------ #
    # 命令行执行
    # ------------------------------------------------------------------ #
    async def _execute_command(self, cmd: str) -> None:
        panel = self.query_one("#output-panel")
        panel.display = True
        log = self.output_log
        log.write(f"$ {cmd}")

        cwd = str(self.filepath.parent) if self.filepath else os.getcwd()

        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=cwd,
            )
        except Exception as exc:  # noqa: BLE001
            log.write(f"[启动失败] {exc}")
            return

        assert proc.stdout is not None
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            try:
                text = line.decode("utf-8")
            except UnicodeDecodeError:
                text = line.decode("utf-8", errors="replace")
            log.write(text.rstrip("\n"))

        await proc.wait()
        log.write(f"[退出码: {proc.returncode}]")
        self.editor.focus()


# --------------------------------------------------------------------------- #
# 入口
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else None
    OneEditorLite(target).run()