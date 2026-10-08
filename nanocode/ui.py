"""A responsive terminal interface without extra dependencies."""

import difflib
import os
import re
import shutil
import sys
import threading
import time
import unicodedata
from pathlib import Path

CONTROL = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\))|[\x00-\x08\x0b-\x1f\x7f]")
ACCENT = "38;5;216"
DIM = "38;5;245"
LOGO = (
    "█▄ █ ▄▀█ █▄ █ █▀█   █▀▀ █▀█ █▀▄ █▀▀",
    "█ ▀█ █▀█ █ ▀█ █▄█   █▄▄ █▄█ █▄▀ ██▄",
)


def clean(text):
    return CONTROL.sub("", str(text))


def interactive():
    return sys.stdout.isatty() and os.environ.get("TERM") != "dumb"


def animated():
    return interactive() and "NO_COLOR" not in os.environ and "NANOCODE_NO_ANIMATION" not in os.environ


def styled(text, color):
    if interactive() and "NO_COLOR" not in os.environ:
        return f"\033[{color}m{clean(text)}\033[0m"
    return clean(text)


def note(text, error=False):
    print(styled(f"  {'!' if error else '·'} {text}", "31" if error else DIM), flush=True)


def width_of(text):
    return sum(0 if unicodedata.combining(char) else 2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1 for char in text)


def fit(text, width):
    text = clean(text).replace("\n", " ").replace("\t", " ")
    if width_of(text) <= width:
        return text + " " * (width - width_of(text))
    result = ""
    for char in text:
        if width_of(result + char) > width - 1:
            break
        result += char
    return result + "…" + " " * max(0, width - width_of(result) - 1)


def row(text, width, color="37"):
    print(styled("  │ ", ACCENT) + styled(fit(text, width - 6), color) + styled(" │", ACCENT))


def welcome(model, auto_yes=False):
    width = min(shutil.get_terminal_size().columns, 88)
    if animated():
        try:
            sys.stdout.write("\033[?25l")
            for spark in ("·", "✧", "✦", "✧", "✦", "✧", "✦"):
                sys.stdout.write("\r" + styled(f"  {spark}  Opening your workspace", ACCENT))
                sys.stdout.flush()
                time.sleep(0.075)
        finally:
            sys.stdout.write("\r\033[2K\033[?25h")
            sys.stdout.flush()
    print()
    if width < 38:
        print(styled("  ✦ NANOCODE", "1;" + ACCENT))
        note(fit(str(Path.cwd()), max(1, width - 4)).rstrip())
        note(fit(model, max(1, width - 4)).rstrip())
    else:
        title = " NANOCODE · terminal agent "
        print(styled("  ╭─" + title + "─" * max(0, width - 5 - width_of(title)) + "╮", ACCENT))
        row("", width)
        if width >= 48:
            for line in LOGO:
                row(line, width, "1;" + ACCENT)
        else:
            row("✦  N A N O C O D E", width, "1;" + ACCENT)
        row("", width)
        row("Small footprint. Real work.", width, DIM)
        row("", width)
        row("Workspace   " + Path.cwd().name, width)
        row("Directory   " + str(Path.cwd()), width, DIM)
        row("Model       " + model, width)
        row("Permissions " + ("auto-approve enabled" if auto_yes else "ask before edits and commands"), width, DIM)
        row("", width)
        print(styled("  ╰" + "─" * (width - 4) + "╯", ACCENT))
    print()
    print(styled("  Start with a question or a task", "1;37"))
    print(styled("  › Explain this project", DIM))
    print(styled("  › Find bugs without changing files", DIM))
    print(styled("  › Fix this error: [paste your error]", DIM))
    print()
    if width >= 72:
        note("/help commands  ·  /plan read-only  ·  /model switch  ·  /exit quit")
    else:
        note("/help · /plan · /model · /exit")
    print()


def prompt(plan_mode=False, auto_yes=False):
    width = min(shutil.get_terminal_size().columns, 88)
    mode = "PLAN · read only" if plan_mode else "BUILD · " + ("auto-approve" if auto_yes else "ask before changes")
    print(styled("  " + "─" * max(1, width - 2), DIM))
    print(styled("  " + mode, "33" if plan_mode else DIM))
    text = styled("  ❯ ", "1;" + ACCENT)
    # Tell readline that ANSI color codes do not occupy screen columns.
    text = re.sub(r"\x1b\[[0-9;]*m", lambda match: "\001" + match.group() + "\002", text)
    return input(text)


class Spinner:
    """Animate the waiting period; stop before printing streamed content."""

    def __init__(self, label="Thinking"):
        self.label = label
        self.event = threading.Event()
        self.thread = None
        self.started = 0.0

    def __enter__(self):
        self.started = time.monotonic()
        if animated():
            self.thread = threading.Thread(target=self._animate, daemon=True)
            self.thread.start()
        else:
            note(self.label + "…")
        return self

    def _animate(self):
        frames = ("✶", "✸", "✹", "✺", "✹", "✸")
        index = 0
        while not self.event.is_set():
            elapsed = time.monotonic() - self.started
            sys.stdout.write("\r\033[2K" + styled(f"  {frames[index % len(frames)]} {self.label} · {elapsed:.0f}s", ACCENT))
            sys.stdout.flush()
            index += 1
            self.event.wait(0.12)

    def stop(self):
        self.event.set()
        if self.thread is not None:
            self.thread.join()
            sys.stdout.write("\r\033[2K")
            sys.stdout.flush()
            self.thread = None

    def __exit__(self, *exc):
        self.stop()


def tool_started(name, args):
    detail = args.get("path") or args.get("command") or args.get("query") or args.get("url") or ""
    print(styled(f"  ↳ {name}", ACCENT) + ("  " + clean(detail).replace("\n", " ")[:160] if detail else ""), flush=True)


def tool_finished(name, result):
    if name == "todo_write":
        print(clean(result))
    else:
        first = result.splitlines()[0] if result else "Done"
        note(first[:180], error=result.startswith("Error:"))


def approve(name, args):
    print(styled(f"\n  ◇ Approval required · {name}", "1;33"))
    if name in {"write_file", "edit_file"}:
        path = Path(args["path"])
        before = path.read_text(encoding="utf-8") if path.exists() else ""
        if name == "write_file":
            after = args["content"]
        else:
            after = before.replace(args["old_string"], args["new_string"], 1)
        diff = difflib.unified_diff(before.splitlines(), after.splitlines(), fromfile=str(path), tofile=str(path), lineterm="")
        for line in diff:
            print(styled(line, "32" if line.startswith("+") else "31" if line.startswith("-") else DIM))
    else:
        for key, value in args.items():
            print(f"  {clean(key)}: {clean(value)}")
    if not sys.stdin.isatty():
        note("Approval needs an interactive terminal. Use -y only for trusted tasks.", error=True)
        return False
    try:
        return input("  Allow this action? [y/N] ").strip().lower() in {"y", "yes"}
    except EOFError:
        return False
