"""Command-line entry point and interactive session."""

import argparse
import sys

from nanocode import ui
from nanocode.agent import Agent, build_system_prompt
from nanocode.config import Config

HELP = """  /help       Show these commands
  /plan       Toggle read-only planning
  /model [ID] Show or switch the model (starts a fresh conversation)
  /clear      Start a fresh conversation
  /exit       Quit

  Ctrl+C cancels the current task. Ctrl+D exits at the prompt.
  Example: Find bugs in this project. Explain them before making changes."""


def new_messages(plan_mode=False):
    return [{"role": "system", "content": build_system_prompt(plan_mode)}]


def repl(agent, stream=True, auto_yes=False, plan_mode=False):
    # Native line editing/history, kept in memory rather than written to disk.
    try:
        import readline  # noqa: F401
    except ImportError:
        pass
    ui.welcome(agent.model, auto_yes)
    messages = new_messages(plan_mode)
    if plan_mode:
        ui.note("Plan mode on · file changes and shell commands are blocked.")
    while True:
        try:
            text = ui.prompt(plan_mode, auto_yes).strip()
        except EOFError:
            print("\n  Goodbye.\n")
            return 0
        except KeyboardInterrupt:
            print()
            continue
        if not text:
            continue
        command, _, argument = text.partition(" ")
        if command in {"/exit", "/quit"}:
            print("\n  Goodbye.\n")
            return 0
        if command == "/help":
            print(HELP)
        elif command == "/plan":
            plan_mode = not plan_mode
            ui.note(f"Plan mode {'on · changes and commands blocked' if plan_mode else ('off · auto-approval enabled' if auto_yes else 'off · changes require approval') }.")
        elif command == "/clear":
            messages = new_messages(plan_mode)
            ui.note("Fresh conversation.")
        elif command == "/model":
            if argument.strip():
                agent.model = argument.strip()
                messages = new_messages(plan_mode)
                ui.note(f"Model: {agent.model} · fresh conversation.")
            else:
                ui.note(agent.model)
        elif text.startswith("/"):
            ui.note("Unknown command. Type /help.", error=True)
        else:
            messages.append({"role": "user", "content": text})
            agent.run(messages, plan_mode=plan_mode, stream=stream, auto_yes=auto_yes)
        print()


def main():
    parser = argparse.ArgumentParser(prog="nanocode", description="A small terminal coding agent powered by OpenRouter.")
    parser.add_argument("-p", "--prompt", help="Run one task and exit.")
    parser.add_argument("-y", "--yes", action="store_true", help="Approve all edits and shell commands automatically.")
    parser.add_argument("--plan", action="store_true", help="Start in read-only planning mode.")
    parser.add_argument("--model", help="OpenRouter model ID (overrides MODEL).")
    parser.add_argument("--no-stream", action="store_true", help="Print complete replies instead of streaming.")
    parser.add_argument("--repl", action="store_true", help=argparse.SUPPRESS)  # Older invocations still work.
    args = parser.parse_args()
    if args.prompt is None and not sys.stdin.isatty():
        parser.error("Use -p 'your task' for non-interactive input.")
    try:
        config = Config(args.model)
        agent = Agent(config)
        if args.prompt is not None:
            if not args.prompt.strip():
                parser.error("The prompt must not be empty.")
            messages = new_messages(args.plan)
            messages.append({"role": "user", "content": args.prompt})
            return 0 if agent.run(messages, plan_mode=args.plan, stream=not args.no_stream, auto_yes=args.yes) else 1
        return repl(agent, stream=not args.no_stream, auto_yes=args.yes, plan_mode=args.plan)
    except (ValueError, OSError) as exc:
        ui.note(str(exc), error=True)
        return 1
    finally:
        if "config" in locals():
            config.client.close()


if __name__ == "__main__":
    sys.exit(main())
