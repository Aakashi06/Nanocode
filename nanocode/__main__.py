import argparse
import os
import shlex
import subprocess
import sys

from nanocode.agent import run_agent, system_prompt, tools

BANNER = """
┌─────────────────────────────────────────┐
│  nanocode · tiny coding agent           │
│  /plan          toggle plan mode        │
│  ctrl-c / ctrl-d  quit                  │
└─────────────────────────────────────────┘
""".strip()


def spawn_new_terminal():
    if sys.platform != "darwin":
        return False

    venv_activate = ""
    if os.environ.get("VIRTUAL_ENV"):
        venv_activate = f"source {shlex.quote(os.environ['VIRTUAL_ENV'])}/bin/activate && "

    command = (
        f"cd {shlex.quote(os.getcwd())} && "
        f"{venv_activate}{shlex.quote(sys.executable)} -m nanocode --repl"
    )
    escaped = command.replace("\\", "\\\\").replace('"', '\\"')

    subprocess.Popen([
        "osascript",
        "-e",
        'tell application "Terminal" to activate',
        "-e",
        f'tell application "Terminal" to do script "{escaped}"',
    ])
    return True


def repl(stream, auto_yes):
    print(BANNER)
    print()

    plan_mode = False
    messages = [{"role": "system", "content": system_prompt}]

    while True:
        try:
            user_input = input("plan › " if plan_mode else "› ")
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(0)

        if not user_input.strip():
            continue

        if user_input.strip() == "/plan":
            plan_mode = not plan_mode
            print(f"  plan mode {'on' if plan_mode else 'off'}\n")
            continue

        messages.append({"role": "user", "content": user_input})
        run_agent(messages, tools, plan_mode=plan_mode, stream=stream, auto_yes=auto_yes)
        print()


def main():
    parser = argparse.ArgumentParser(prog="nanocode", description="A minimal terminal coding agent.")
    parser.add_argument("--no-stream", action="store_true", help="Disable streaming output.")
    parser.add_argument("-y", "--yes", action="store_true", help="Auto-approve non-read-only tools.")
    parser.add_argument("-p", "--prompt", help="Run a single prompt and exit.")
    parser.add_argument("--repl", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    stream = not args.no_stream

    if args.prompt:
        messages = [{"role": "system", "content": system_prompt}]
        messages.append({"role": "user", "content": args.prompt})
        run_agent(messages, tools, stream=stream, auto_yes=args.yes)
        return

    if not args.repl:
        if spawn_new_terminal():
            return
        if not sys.stdin.isatty():
            print("nanocode: run in an interactive terminal.", file=sys.stderr)
            sys.exit(1)

    repl(stream=stream, auto_yes=args.yes)


if __name__ == "__main__":
    main()
