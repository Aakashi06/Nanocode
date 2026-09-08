import json
import os
import re
import subprocess
import urllib.request

import requests

from abc import ABC, abstractmethod


class Tool(ABC):
    name: str
    description: str
    parameters: dict
    is_read_only: bool

    @abstractmethod
    def execute(self, args: dict) -> str:
        pass

    def to_openai(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ReadFileTool(Tool):
    name = "read_file"
    description = "Read a file from disk and return its contents."
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the file to read.",
            },
        },
        "required": ["path"],
    }
    is_read_only = True

    def execute(self, args: dict) -> str:
        path = args["path"]

        if not os.path.exists(path):
            return f"Error: file not found: '{path}'"

        if os.path.isdir(path):
            return f"Error: '{path}' is a directory, not a file."

        try:
            with open(path, "rb") as f:
                chunk = f.read(8192)
        except OSError as e:
            return f"Error: cannot read '{path}': {e}"

        if b"\x00" in chunk:
            return f"Error: '{path}' is not a UTF-8 text file and cannot be read as plain text."

        try:
            with open(path, encoding="utf-8") as f:
                return f.read()
        except UnicodeDecodeError:
            return f"Error: '{path}' is not a UTF-8 text file and cannot be read as plain text."
        except OSError as e:
            return f"Error: cannot read '{path}': {e}"


class WriteFileTool(Tool):
    name = "write_file"
    description = "Write content to a file."
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the file to write.",
            },
            "content": {
                "type": "string",
                "description": "Content to write to the file.",
            },
        },
        "required": ["path", "content"],
    }
    is_read_only = False

    def execute(self, args: dict) -> str:
        with open(args["path"], "w") as f:
            f.write(args["content"])
        return f"Wrote {args['path']}"


class EditFileTool(Tool):
    name = "edit_file"
    description = "Replace an exact old string with a new string in a file."
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the file to edit.",
            },
            "old_string": {
                "type": "string",
                "description": "Exact string to find in the file.",
            },
            "new_string": {
                "type": "string",
                "description": "String to replace it with.",
            },
        },
        "required": ["path", "old_string", "new_string"],
    }
    is_read_only = False

    def execute(self, args: dict) -> str:
        with open(args["path"]) as f:
            content = f.read()
        if args["old_string"] not in content:
            return "Error: old_string not found in file."
        content = content.replace(args["old_string"], args["new_string"])
        with open(args["path"], "w") as f:
            f.write(content)
        return f"Edited {args['path']}"


class GrepTool(Tool):
    name = "grep"
    description = "Search files for a regex pattern."
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Regex pattern to search for.",
            },
            "path": {
                "type": "string",
                "description": "File or directory to search.",
            },
        },
        "required": ["pattern", "path"],
    }
    is_read_only = True

    def execute(self, args: dict) -> str:
        pattern = re.compile(args["pattern"])
        path = args["path"]

        if os.path.isfile(path):
            files = [path]
        else:
            files = []
            for root, _, filenames in os.walk(path):
                for filename in filenames:
                    files.append(os.path.join(root, filename))

        matches = []
        for filepath in files:
            with open(filepath) as f:
                for line_num, line in enumerate(f, 1):
                    if pattern.search(line):
                        matches.append(f"{filepath}:{line_num}:{line.rstrip()}")

        return "\n".join(matches) if matches else "No matches found."


class BashTool(Tool):
    name = "bash"
    description = "Run a shell command."
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Shell command to run.",
            },
        },
        "required": ["command"],
    }
    is_read_only = False

    def execute(self, args: dict) -> str:
        result = subprocess.run(
            args["command"],
            shell=True,
            capture_output=True,
            text=True,
        )
        return result.stdout + result.stderr


class TodoWriteTool(Tool):
    name = "todo_write"
    description = "Store and update a todo list."
    parameters = {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string"},
                        "status": {
                            "type": "string",
                            "enum": ["pending", "in_progress", "done"],
                        },
                    },
                    "required": ["content", "status"],
                },
            },
        },
        "required": ["items"],
    }
    is_read_only = True

    def __init__(self):
        self.items = []

    def execute(self, args: dict) -> str:
        self.items = args["items"]
        lines = []
        for item in self.items:
            if item["status"] == "done":
                mark = "[x]"
            elif item["status"] == "in_progress":
                mark = "[~]"
            else:
                mark = "[ ]"
            lines.append(f"{mark} {item['content']}")
        return "\n".join(lines)


class SpawnAgentTool(Tool):
    name = "task"
    description = "Spawn a sub-agent to work on a task."
    parameters = {
        "type": "object",
        "properties": {
            "description": {
                "type": "string",
                "description": "Short description of the task.",
            },
            "prompt": {
                "type": "string",
                "description": "Prompt for the sub-agent.",
            },
        },
        "required": ["description", "prompt"],
    }
    is_read_only = False

    def __init__(self, system_prompt, tools, openai_tools, run_agent):
        self.system_prompt = system_prompt
        self.tools = tools
        self.openai_tools = openai_tools
        self.run_agent = run_agent

    def execute(self, args: dict) -> str:
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": args["prompt"]},
        ]
        return self.run_agent(messages, self.tools, self.openai_tools, auto_approve=True)


class WebFetchTool(Tool):
    name = "web_fetch"
    description = "Fetch a URL and return readable text."
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "URL to fetch.",
            },
        },
        "required": ["url"],
    }
    is_read_only = True

    def __init__(self, api_key):
        self.api_key = api_key

    def execute(self, args: dict) -> str:
        body = json.dumps({"url": args["url"]}).encode()
        req = urllib.request.Request(
            "https://api.firecrawl.dev/v1/scrape",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
        text = result["data"]["markdown"]
        return text[:4000]


class WebSearchTool(Tool):
    name = "web_search"
    description = "Search the web and return titles, URLs, and descriptions."
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query.",
            },
        },
        "required": ["query"],
    }
    is_read_only = True

    def __init__(self, api_key):
        self.api_key = api_key

    def execute(self, args: dict) -> str:
        response = requests.post(
            "https://api.firecrawl.dev/v2/search",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"query": args["query"], "limit": 5, "sources": ["web"]},
        )
        response.raise_for_status()
        results = response.json()["data"]["web"]
        return "\n\n".join(
            f"{r['title']}\n{r['url']}\n{r.get('description', '')}"
            for r in results
        )
