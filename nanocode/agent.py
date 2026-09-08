import json
import os
import platform
import time

from openai import APIError, RateLimitError

from nanocode.config import FIRECRAWL_API_KEY, MODEL, client
from nanocode.tools import (
    BashTool,
    EditFileTool,
    GrepTool,
    ReadFileTool,
    SpawnAgentTool,
    TodoWriteTool,
    WebFetchTool,
    WebSearchTool,
    WriteFileTool,
)

COMPACT_THRESHOLD = 16000
KEEP_RECENT = 6


def build_system_prompt(plan_mode=False):
    lines = [
        "You are nanocode, a terminal coding agent. Be concise. Prefer tools over guessing.",
        f"Model: {MODEL}",
        "Use todo_write to plan any task with more than a couple of steps.",
    ]
    if plan_mode:
        lines.append(
            "Plan mode: use todo_write to outline your plan first. "
            "Only use read-only tools until the user confirms the plan."
        )

    lines.extend([
        "",
        "Environment:",
        f"  cwd: {os.getcwd()}",
        f"  os:  {platform.system()}",
        "  files:",
    ])
    for name in sorted(os.listdir()):
        lines.append(f"    {name}")

    if os.path.exists("NANOCODE.md"):
        with open("NANOCODE.md") as f:
            lines.extend(["", "Project instructions:", f.read()])

    return "\n".join(lines)


def message_size(messages):
    return sum(len(json.dumps(m)) for m in messages)


def compact(messages):
    if message_size(messages) < COMPACT_THRESHOLD:
        return

    old = messages[1:-KEEP_RECENT]
    if not old:
        return

    transcript = "\n".join(
        f"{m['role']}: {m.get('content') or ''}" for m in old
    )

    try:
        response = call_with_retry(
            lambda: client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": "Summarize this conversation briefly for context."},
                    {"role": "user", "content": transcript},
                ],
            )
        )
    except (RateLimitError, APIError):
        return

    summary = response.choices[0].message.content
    messages[:] = [
        messages[0],
        {"role": "user", "content": f"[Compacted history]\n{summary}"},
        *messages[-KEEP_RECENT:],
    ]


def call_with_retry(fn, retries=3):
    for attempt in range(retries):
        try:
            return fn()
        except RateLimitError:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)


def stream_completion(messages, openai_tools):
    tool_calls = {}
    content = ""
    finish_reason = None

    stream = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        tools=openai_tools,
        stream=True,
    )

    for chunk in stream:
        finish_reason = chunk.choices[0].finish_reason
        delta = chunk.choices[0].delta

        if delta.content:
            print(delta.content, end="", flush=True)
            content += delta.content

        if delta.tool_calls:
            for tc in delta.tool_calls:
                i = tc.index
                if i not in tool_calls:
                    tool_calls[i] = {
                        "id": "",
                        "type": "function",
                        "function": {"name": "", "arguments": ""},
                    }
                if tc.id:
                    tool_calls[i]["id"] = tc.id
                if tc.function.name:
                    tool_calls[i]["function"]["name"] = tc.function.name
                if tc.function.arguments:
                    tool_calls[i]["function"]["arguments"] += tc.function.arguments

    message = {"role": "assistant", "content": content or None}
    if tool_calls:
        message["tool_calls"] = [tool_calls[i] for i in sorted(tool_calls)]

    return message, finish_reason, content


def ask_permission(tool_name, args):
    print(f"\n── {tool_name} " + "─" * max(1, 34 - len(tool_name)))
    for key, value in args.items():
        text = value if len(str(value)) <= 120 else str(value)[:117] + "..."
        print(f"  {key}: {text}")
    return input("  allow? [y/n] ").strip().lower() == "y"


def run_tool(tool, args, plan_mode, auto_approve, auto_yes):
    if plan_mode and not tool.is_read_only:
        return "Plan mode: mutating tools are blocked. Use read-only tools only."

    if not tool.is_read_only and not auto_approve:
        if not (auto_yes or ask_permission(tool.name, args)):
            return "user denied"

    return tool.execute(args)


def run_agent_loop(messages, tools, openai_tools, auto_approve=False, stream=False, auto_yes=False, plan_mode=False):
    while True:
        compact(messages)

        try:
            if stream and not auto_approve:
                message, finish_reason, content = call_with_retry(
                    lambda: stream_completion(messages, openai_tools)
                )
            else:
                response = call_with_retry(
                    lambda: client.chat.completions.create(
                        model=MODEL,
                        messages=messages,
                        tools=openai_tools,
                    )
                )
                message = response.choices[0].message.model_dump(exclude_none=True)
                finish_reason = response.choices[0].finish_reason
                content = message.get("content") or ""
        except RateLimitError:
            print("\n⚠ rate limited — wait a moment and try again.")
            return None
        except APIError as e:
            print(f"\n⚠ API error: {getattr(e, 'message', e)}")
            return None

        if not finish_reason:
            print("\n⚠ no response from model — try again.")
            return None

        if finish_reason == "tool_calls":
            messages.append(message)
            for tool_call in message["tool_calls"]:
                args = json.loads(tool_call["function"]["arguments"])
                tool = tools[tool_call["function"]["name"]]
                result = run_tool(tool, args, plan_mode, auto_approve, auto_yes)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": result,
                })
            continue

        messages.append(message)
        if not auto_approve and not stream:
            print(content)
        elif not auto_approve and stream:
            print()
        return content


def build_tools(system_prompt):
    base_tool_instances = [
        ReadFileTool(),
        WriteFileTool(),
        EditFileTool(),
        GrepTool(),
        BashTool(),
        TodoWriteTool(),
        WebFetchTool(FIRECRAWL_API_KEY),
        WebSearchTool(FIRECRAWL_API_KEY),
    ]

    sub_tools = {tool.name: tool for tool in base_tool_instances}
    sub_openai_tools = [tool.to_openai() for tool in base_tool_instances]

    spawn_tool = SpawnAgentTool(system_prompt, sub_tools, sub_openai_tools, run_agent_loop)
    tool_instances = base_tool_instances + [spawn_tool]
    tools = {tool.name: tool for tool in tool_instances}
    openai_tools = [tool.to_openai() for tool in tool_instances]
    return tools, openai_tools, run_agent_loop


system_prompt = build_system_prompt()
tools, openai_tools, _run_agent_loop = build_tools(system_prompt)


def run_agent(messages, tools_dict, plan_mode=False, stream=True, auto_yes=False):
    result = _run_agent_loop(
        messages,
        tools_dict,
        openai_tools,
        stream=stream,
        auto_yes=auto_yes,
        plan_mode=plan_mode,
    )
    if result is None and messages and messages[-1].get("role") == "user":
        messages.pop()
    return result or ""
