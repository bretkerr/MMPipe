#!/usr/bin/env python3
"""
mmtui — Full-screen TUI for MMPipe v2.

MMP/1.0 contract implemented:
  The File Browser selects source files which are fed into `mcat` (the UMPP
  emitter). The Pipeline Builder assembles the downstream command chain.
  Each command must either consume + re-emit a UMPP envelope (e.g. mmkitty)
  or consume a UMPP envelope and produce plain UTF-8 text (e.g. analyze_vision).
  The pipeline is executed as a shell pipeline and output is streamed live
  into the Output panel.

Layout:
  ┌─────────────────────────────────────────────────────┐
  │ MMPipe TUI v2                                        │
  ├──────────────────┬──────────────────┬───────────────┤
  │  File Browser    │ Pipeline Builder │    Output     │
  │  (DirectoryTree) │ (command list)   │  (live log)   │
  └──────────────────┴──────────────────┴───────────────┘
  │ Space/Ctrl+A: attach  Ctrl+R: run  Ctrl+X: clear   │
  └─────────────────────────────────────────────────────┘

Keyboard shortcuts:
  Space / Ctrl+A   Attach highlighted file as pipeline source
  Ctrl+R           Run pipeline
  Ctrl+X           Clear output panel
  a                Add a new command to the pipeline (prompts inline)
  d                Delete selected pipeline step
  u                Move selected step up
  j                Move selected step down

Requirements: pip install textual
"""

import asyncio
import os
import sys
from pathlib import Path

try:
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal, Vertical
    from textual.widgets import (
        DirectoryTree,
        Footer,
        Header,
        Input,
        Label,
        ListItem,
        ListView,
        RichLog,
    )
    from textual.reactive import reactive
except ImportError:
    print("mmtui requires textual: pip install textual", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Resolve paths relative to this file
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
_MMPY = _HERE.parent / "mm.py"
_MMKITTY = _HERE.parent / "bridge" / "mmkitty.py"

_DEFAULT_PIPELINE = [
    f"python3 {_MMPY} analyze_vision",
]


class PipelineItem(ListItem):
    """A single command in the Pipeline Builder."""

    def __init__(self, command: str) -> None:
        self.command = command
        super().__init__(Label(command))

    def refresh_label(self) -> None:
        self.query_one(Label).update(self.command)


class MMPipeTUI(App):
    """MMPipe v2 TUI — File Browser | Pipeline Builder | Output."""

    CSS = """
    Screen {
        background: $surface;
    }
    #browser {
        width: 1fr;
        border: solid $primary;
        padding: 0 1;
    }
    #pipeline-panel {
        width: 1fr;
        border: solid $accent;
        padding: 0 1;
    }
    #output-panel {
        width: 2fr;
        border: solid $success;
        padding: 0 1;
    }
    #pipeline-list {
        height: 1fr;
    }
    #cmd-input {
        dock: bottom;
        display: none;
    }
    #cmd-input.visible {
        display: block;
    }
    #panel-label {
        text-style: bold;
        color: $text-muted;
        padding: 0 0 1 0;
    }
    #source-label {
        color: $accent;
        padding: 0 0 1 0;
    }
    """

    BINDINGS = [
        Binding("ctrl+r", "run_pipeline", "Run", show=True),
        Binding("ctrl+a", "attach_file", "Attach", show=True),
        Binding("ctrl+x", "clear_output", "Clear", show=True),
        Binding("space", "attach_file", "Attach", show=False),
        Binding("a", "add_command", "Add cmd", show=True),
        Binding("d", "delete_step", "Delete step", show=False),
        Binding("u", "move_up", "Move up", show=False),
        Binding("j", "move_down", "Move down", show=False),
    ]

    source_file: reactive[str | None] = reactive(None)

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(id="browser"):
                yield Label("File Browser", id="panel-label")
                yield DirectoryTree(Path.home(), id="filetree")
            with Vertical(id="pipeline-panel"):
                yield Label("Pipeline Builder", id="panel-label")
                yield Label("source: (none)", id="source-label")
                yield ListView(
                    *[PipelineItem(cmd) for cmd in _DEFAULT_PIPELINE],
                    id="pipeline-list",
                )
                yield Input(placeholder="command to add...", id="cmd-input")
            with Vertical(id="output-panel"):
                yield Label("Output", id="panel-label")
                yield RichLog(highlight=True, markup=True, id="output-log")
        yield Footer()

    # ------------------------------------------------------------------
    # Reactive watcher
    # ------------------------------------------------------------------

    def watch_source_file(self, path: str | None) -> None:
        label = self.query_one("#source-label", Label)
        if path:
            label.update(f"source: [bold]{Path(path).name}[/bold]")
        else:
            label.update("source: (none)")

    # ------------------------------------------------------------------
    # File browser events
    # ------------------------------------------------------------------

    def on_directory_tree_file_selected(
        self, event: DirectoryTree.FileSelected
    ) -> None:
        """Highlight the clicked file (doesn't attach yet)."""
        self._highlighted_path = str(event.path)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_attach_file(self) -> None:
        path = getattr(self, "_highlighted_path", None)
        if not path:
            self._log_info("[yellow]Select a file in the browser first.[/yellow]")
            return
        self.source_file = path
        self._log_info(f"[green]Attached:[/green] {path}")

    def action_add_command(self) -> None:
        inp = self.query_one("#cmd-input", Input)
        inp.add_class("visible")
        inp.focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        cmd = event.value.strip()
        inp = self.query_one("#cmd-input", Input)
        inp.remove_class("visible")
        inp.value = ""
        if cmd:
            lv = self.query_one("#pipeline-list", ListView)
            lv.append(PipelineItem(cmd))
        self.query_one("#filetree", DirectoryTree).focus()

    def action_delete_step(self) -> None:
        lv = self.query_one("#pipeline-list", ListView)
        if lv.highlighted_child is not None:
            lv.highlighted_child.remove()

    def action_move_up(self) -> None:
        lv = self.query_one("#pipeline-list", ListView)
        idx = lv.index
        if idx is not None and idx > 0:
            items = list(lv.query(PipelineItem))
            items[idx - 1], items[idx] = items[idx], items[idx - 1]
            self._rebuild_list(items)

    def action_move_down(self) -> None:
        lv = self.query_one("#pipeline-list", ListView)
        idx = lv.index
        items = list(lv.query(PipelineItem))
        if idx is not None and idx < len(items) - 1:
            items[idx], items[idx + 1] = items[idx + 1], items[idx]
            self._rebuild_list(items)

    def _rebuild_list(self, items: list[PipelineItem]) -> None:
        lv = self.query_one("#pipeline-list", ListView)
        commands = [item.command for item in items]
        lv.clear()
        for cmd in commands:
            lv.append(PipelineItem(cmd))

    def action_clear_output(self) -> None:
        self.query_one("#output-log", RichLog).clear()

    def action_run_pipeline(self) -> None:
        if not self.source_file:
            self._log_info("[yellow]No source file attached. Use Space or Ctrl+A.[/yellow]")
            return
        pipeline_items = list(self.query("#pipeline-list PipelineItem"))
        commands = [item.command for item in pipeline_items]
        if not commands:
            self._log_info("[yellow]Pipeline is empty. Add commands with 'a'.[/yellow]")
            return
        self.run_worker(self._execute_pipeline(self.source_file, commands), exclusive=True)

    # ------------------------------------------------------------------
    # Pipeline execution
    # ------------------------------------------------------------------

    async def _execute_pipeline(self, source: str, commands: list[str]) -> None:
        log = self.query_one("#output-log", RichLog)
        log.clear()
        log.write(f"[dim]Running pipeline on {Path(source).name}...[/dim]")

        # Build shell pipeline: mcat source | cmd1 | cmd2 | ...
        mcat_cmd = f"python3 {_MMPY} mcat {_shell_quote(source)}"
        full_pipeline = " | ".join([mcat_cmd] + commands)

        log.write(f"[dim]$ {full_pipeline}[/dim]\n")

        try:
            proc = await asyncio.create_subprocess_shell(
                full_pipeline,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ},
            )

            async def stream_to_log(stream, style: str) -> None:
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    text = line.decode("utf-8", errors="replace").rstrip()
                    if text:
                        log.write(f"[{style}]{text}[/{style}]")

            await asyncio.gather(
                stream_to_log(proc.stdout, "white"),
                stream_to_log(proc.stderr, "dim yellow"),
            )
            await proc.wait()

            if proc.returncode == 0:
                log.write("\n[green]✓ Pipeline complete.[/green]")
            else:
                log.write(f"\n[red]Pipeline exited with code {proc.returncode}.[/red]")

        except Exception as exc:
            log.write(f"[red]Error: {exc}[/red]")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _log_info(self, markup: str) -> None:
        self.query_one("#output-log", RichLog).write(markup)


def _shell_quote(path: str) -> str:
    """Minimal shell quoting — wraps path in single quotes, escaping any single quotes."""
    return "'" + path.replace("'", "'\\''") + "'"


def main() -> None:
    MMPipeTUI().run()


if __name__ == "__main__":
    main()
