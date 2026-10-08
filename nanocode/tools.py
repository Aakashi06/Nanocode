"""Bounded file, shell, and optional web tools."""

import json
import os
import re
import signal
import subprocess
import tempfile
import urllib.request
from pathlib import Path

MAX_OUTPUT = 16000
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".mypy_cache", ".pytest_cache", "dist", "build"}


def bounded(text, limit=MAX_OUTPUT):
    text = str(text)
    return text if len(text) <= limit else text[:limit] + "\n[Output truncated; request a smaller range or narrower search.]"


def validate(value, schema, location="arguments"):
    kind = schema.get("type")
    types = {"object": dict, "array": list, "string": str, "integer": int}
    if kind in types and (not isinstance(value, types[kind]) or kind == "integer" and isinstance(value, bool)):
        raise ValueError(f"{location} must be {kind}")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{location} must be one of {schema['enum']}")
    if kind == "object":
        for key in schema.get("required", []):
            if key not in value:
                raise ValueError(f"Missing {location}.{key}")
        for key, item in value.items():
            if key not in schema.get("properties", {}):
                raise ValueError(f"Unknown {location}.{key}")
            validate(item, schema["properties"][key], f"{location}.{key}")
    if kind == "array":
        for i, item in enumerate(value):
            validate(item, schema["items"], f"{location}[{i}]")
    if kind == "integer" and not schema.get("minimum", value) <= value <= schema.get("maximum", value):
        raise ValueError(f"{location} is outside the allowed range")


class Tool:
    is_read_only = True

    def __init__(self, name, description, properties, required, execute, read_only=True):
        self.name = name
        self.description = description
        self.parameters = {"type": "object", "properties": properties, "required": required, "additionalProperties": False}
        self.execute = execute
        self.is_read_only = read_only

    def to_openai(self):
        return {"type": "function", "function": {"name": self.name, "description": self.description, "parameters": self.parameters}}


def read_file(args):
    start, count = args.get("start_line", 1), args.get("max_lines", 200)
    lines, size, more = [], 0, False
    try:
        with open(args["path"], encoding="utf-8") as file:
            for number, line in enumerate(file, 1):
                if number < start:
                    continue
                if len(lines) >= count or size >= MAX_OUTPUT:
                    more = True
                    break
                if "\x00" in line:
                    raise ValueError("Binary files cannot be read as text")
                rendered = f"{number}: {line.rstrip()}"
                lines.append(rendered)
                size += len(rendered)
        result = "\n".join(lines) or "File is empty or the requested range is past the end."
        if more:
            result += f"\n[More lines available; continue at start_line={start + len(lines)}.]"
        return bounded(result)
    except UnicodeError as exc:
        # Handle encoding errors gracefully (e.g., invalid UTF-8 sequences)
        raise ValueError(f"File contains invalid text: {exc}") from exc


def write_text(path, content):
    """Replace a text file atomically; preserve permissions and symlink targets."""
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as file:
            temporary = Path(file.name)
            file.write(content)
        temporary.chmod(mode)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def write_file(args):
    write_text(args["path"], args["content"])
    return f"Wrote {args['path']}"


def edit_file(args):
    path = Path(args["path"])
    content = path.read_text(encoding="utf-8")
    old = args["old_string"]
    if not old:
        raise ValueError("old_string must not be empty")
    count = content.count(old)
    if count != 1:
        raise ValueError(f"old_string matched {count} times; provide a unique exact string")
    write_text(path, content.replace(old, args["new_string"], 1))
    return f"Edited {path}"


def grep(args):
    try:
        pattern = re.compile(args["pattern"])
    except re.error as exc:
        raise ValueError(f"Invalid search regex: {exc}") from exc
    path = Path(args.get("path", "."))
    if not path.exists():
        raise FileNotFoundError(f"Path does not exist: {path}")
    if path.is_file():
        files = iter([path])
    else:
        def walk():
            for root, dirs, names in os.walk(path):
                dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.endswith(".egg-info"))
                for name in sorted(names):
                    # Secrets are only read when explicitly requested via read_file.
                    if name.startswith(".env"):
                        continue
                    yield Path(root) / name
        files = walk()
    matches, size = [], 0
    for file in files:
        if file.is_symlink():
            continue
        try:
            with file.open(encoding="utf-8") as handle:
                for number, line in enumerate(handle, 1):
                    if "\x00" in line:
                        break
                    if pattern.search(line):
                        rendered = f"{file}:{number}:{line.rstrip()}"
                        matches.append(rendered)
                        size += len(rendered)
                        if len(matches) >= 100 or size >= MAX_OUTPUT:
                            return bounded("\n".join(matches) + "\n[Search limited; narrow the pattern or path.]")
        except (OSError, UnicodeError):
            continue
    return "\n".join(matches) or "No matches found."


def bash(args):
    timeout = args.get("timeout", 60)
    # Spool output to disk so verbose commands cannot fill process memory.
    with tempfile.TemporaryFile() as output:
        process = subprocess.Popen(args["command"], shell=True, stdin=subprocess.DEVNULL,
                                   stdout=output, stderr=subprocess.STDOUT,
                                   start_new_session=os.name == "posix")
        try:
            process.wait(timeout=timeout)
        except (subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
            if os.name == "posix":
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            else:
                process.kill()
            process.wait()
            if isinstance(exc, KeyboardInterrupt):
                raise
            output.seek(0)
            text = output.read(MAX_OUTPUT).decode("utf-8", errors="replace")
            return f"Error: command timed out after {timeout}s\n{text}"
        output.seek(0)
        text = output.read(MAX_OUTPUT + 1).decode("utf-8", errors="replace")
    return f"Exit code: {process.returncode}\n{bounded(text)}"


def todo_write(args):
    marks = {"pending": "[ ]", "in_progress": "[~]", "done": "[x]"}
    return "\n".join(f"{marks[item['status']]} {item['content']}" for item in args["items"])


def web_request(key, endpoint, payload):
    request = urllib.request.Request(
        f"https://api.firecrawl.dev/{endpoint}", data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def build_tools(firecrawl_key=None):
    string = {"type": "string"}
    path = {"path": string}
    instances = [
        Tool("read_file", "Read numbered lines from a UTF-8 file. Use start_line to continue reading.",
             {**path, "start_line": {"type": "integer", "minimum": 1}, "max_lines": {"type": "integer", "minimum": 1, "maximum": 500}}, ["path"], read_file),
        Tool("write_file", "Create or overwrite a UTF-8 file. Read existing files first.",
             {**path, "content": string}, ["path", "content"], write_file, False),
        Tool("edit_file", "Replace one unique exact string. Include enough surrounding text to identify it.",
             {**path, "old_string": string, "new_string": string}, ["path", "old_string", "new_string"], edit_file, False),
        Tool("grep", "Search text files by regex, skipping dependencies and Git internals. Returns at most 100 matches.",
             {**path, "pattern": string}, ["pattern"], grep),
        Tool("bash", "Run a non-interactive shell command. Returns exit code and output; cwd changes do not persist.",
             {"command": string, "timeout": {"type": "integer", "minimum": 1, "maximum": 300}}, ["command"], bash, False),
        Tool("todo_write", "Display a concise task checklist.", {"items": {"type": "array", "items": {
             "type": "object", "properties": {"content": string, "status": {"type": "string", "enum": ["pending", "in_progress", "done"]}},
             "required": ["content", "status"]}}}, ["items"], todo_write),
    ]
    if firecrawl_key:
        def fetch(args):
            result = web_request(firecrawl_key, "v1/scrape", {"url": args["url"]})
            return bounded(result["data"]["markdown"])

        def search(args):
            result = web_request(firecrawl_key, "v2/search", {"query": args["query"], "limit": 5, "sources": ["web"]})
            return bounded("\n\n".join(f"{item['title']}\n{item['url']}\n{item.get('description', '')}" for item in result["data"]["web"]))

        instances.extend([
            Tool("web_fetch", "Fetch a URL as readable text using Firecrawl.", {"url": string}, ["url"], fetch),
            Tool("web_search", "Search the web using Firecrawl.", {"query": string}, ["query"], search),
        ])
    return {tool.name: tool for tool in instances}
