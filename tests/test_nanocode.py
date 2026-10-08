"""Regression tests for the harness's failure paths; no network or credentials."""

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

from openai import AuthenticationError

from nanocode.agent import Agent, finish_pending
from nanocode.tools import bash, build_tools, edit_file, grep, read_file, validate, write_file


class HarnessTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.client = Mock()
        self.agent = Agent(NS(client=self.client, model="test:free", firecrawl_key=None))

    def tearDown(self):
        self.directory.cleanup()

    def call(self, name, args, call_id="call-1"):
        return {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}

    def execute(self, call, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()):
            return self.agent.execute(call, kwargs.get("plan_mode", False), kwargs.get("auto_yes", True))

    def run_agent(self, messages, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()):
            return self.agent.run(messages, **kwargs)

    def messages(self):
        return [{"role": "system", "content": "test"}, {"role": "user", "content": "fix"}]

    def test_optional_web(self):
        self.assertNotIn("web_fetch", build_tools())
        self.assertIn("web_search", build_tools("fake"))
        self.assertNotIn("task", build_tools())

    def test_validation_nested_and_integer(self):
        tool = self.agent.tools["todo_write"]
        with self.assertRaises(ValueError):
            validate({"items": [{"content": "task", "status": "invalid"}]}, tool.parameters)
        for timeout in (True, 0, 301, "60"):
            with self.assertRaises(ValueError):
                validate({"command": "true", "timeout": timeout}, self.agent.tools["bash"].parameters)

    def test_invalid_arguments_recover(self):
        for args in ({}, {"path": 42}, {"path": "x", "extra": "x"}):
            self.assertTrue(self.execute(self.call("read_file", args)).startswith("Error:"))
        call = self.call("read_file", {})
        call["function"]["arguments"] = "{broken"
        self.assertTrue(self.execute(call).startswith("Error:"))
        self.assertIn("Unknown tool", self.execute(self.call("unknown", {})))

    def test_write_creates_parent_and_read_ranges(self):
        path = self.root / "nested" / "source.py"
        write_file({"path": str(path), "content": "one\ntwo\nthree\n"})
        result = read_file({"path": str(path), "start_line": 2, "max_lines": 1})
        self.assertIn("2: two", result)
        self.assertIn("start_line=3", result)
        self.assertNotIn("1: one", result)

    def test_ambiguous_edit_does_not_change_file(self):
        path = self.root / "code.py"
        path.write_text("value value")
        for old in ("value", "", "missing"):
            result = self.execute(self.call("edit_file", {"path": str(path), "old_string": old, "new_string": "new"}))
            self.assertTrue(result.startswith("Error:"))
            self.assertEqual(path.read_text(), "value value")

    def test_unique_edit_preserves_permissions(self):
        path = self.root / "script"
        path.write_text("unique value")
        path.chmod(0o755)
        edit_file({"path": str(path), "old_string": "unique", "new_string": "changed"})
        self.assertEqual(path.read_text(), "changed value")
        self.assertEqual(path.stat().st_mode & 0o777, 0o755)

    def test_search_skips_dependencies_binary_and_secret(self):
        (self.root / ".venv").mkdir()
        (self.root / ".venv" / "ignored").write_text("needle")
        (self.root / ".env").write_text("needle")
        (self.root / "binary").write_bytes(b"\xff\x00needle")
        (self.root / "code.py").write_text("needle")
        result = grep({"path": str(self.root), "pattern": "needle"})
        self.assertIn("code.py:1:needle", result)
        self.assertNotIn(".env", result)
        self.assertNotIn("ignored", result)

    def test_tool_os_error_returns_to_model(self):
        result = self.execute(self.call("read_file", {"path": str(self.root / "missing")}))
        self.assertTrue(result.startswith("Error:"))

    def test_plan_and_denial_prevent_writes(self):
        path = self.root / "new.py"
        call = self.call("write_file", {"path": str(path), "content": "oops"})
        self.assertIn("plan mode", self.execute(call, plan_mode=True))
        with patch("nanocode.ui.approve", return_value=False):
            self.assertIn("denied", self.execute(call, auto_yes=False))
        self.assertFalse(path.exists())

    def test_bash_exit_code_timeout_and_bounded_output(self):
        self.assertIn("Exit code: 7", bash({"command": "exit 7"}))
        self.assertIn("timed out", bash({"command": "sleep 5", "timeout": 1}))
        result = bash({"command": f"{sys.executable} -c 'print(\"x\" * 20000)'"})
        self.assertIn("truncated", result)
        self.assertLess(len(result), 16300)

    def test_tool_loop_recovers_after_bad_call(self):
        messages = self.messages()
        bad = {"role": "assistant", "tool_calls": [self.call("read_file", {})]}
        final = {"role": "assistant", "content": "Recovered"}
        with patch.object(self.agent, "complete", side_effect=[(bad, "tool_calls"), (final, "stop")]):
            self.assertTrue(self.run_agent(messages, stream=False))
        self.assertTrue(messages[3]["content"].startswith("Error:"))
        self.assertEqual(messages[3]["tool_call_id"], "call-1")

    def test_plan_filters_schema_and_updates_prompt(self):
        messages = self.messages()
        with patch.object(self.agent, "complete", return_value=({"role": "assistant", "content": "Plan"}, "stop")) as complete:
            self.assertTrue(self.run_agent(messages, plan_mode=True, stream=False))
        names = [schema["function"]["name"] for schema in complete.call_args.args[1]]
        self.assertNotIn("bash", names)
        self.assertIn("Plan mode is ON", messages[0]["content"])

    def test_interruption_completes_all_pending_results(self):
        messages = self.messages()
        assistant = {"role": "assistant", "tool_calls": [self.call("bash", {"command": "true"}), self.call("bash", {"command": "true"}, "call-2")]}
        with patch.object(self.agent, "complete", return_value=(assistant, "tool_calls")), patch.object(self.agent, "execute", side_effect=KeyboardInterrupt):
            self.assertFalse(self.run_agent(messages))
        self.assertEqual([m["tool_call_id"] for m in messages if m["role"] == "tool"], ["call-1", "call-2"])
        finish_pending(messages, "again")
        self.assertEqual(len(messages), 5)

    def test_incomplete_response_does_not_enter_history(self):
        messages = self.messages()
        with patch.object(self.agent, "complete", return_value=({"role": "assistant", "content": "partial"}, "length")):
            self.assertFalse(self.run_agent(messages))
        self.assertEqual(len(messages), 2)

    def test_empty_response_rejected(self):
        with patch.object(self.agent, "complete", return_value=({"role": "assistant", "content": None}, "stop")):
            self.assertFalse(self.run_agent(self.messages()))

    def test_compaction_preserves_tool_groups_and_arguments(self):
        messages = [{"role": "system", "content": "system"}]
        for index in range(4):
            messages.extend([
                {"role": "user", "content": str(index) * 30000},
                {"role": "assistant", "tool_calls": [self.call("read_file", {"path": "file.py"}, f"call-{index}")]},
                {"role": "tool", "tool_call_id": f"call-{index}", "content": "result"},
                {"role": "assistant", "content": "done"}])
        self.client.chat.completions.create.return_value = NS(choices=[NS(message=NS(content="summary"), finish_reason="stop")])
        with contextlib.redirect_stdout(io.StringIO()):
            self.agent.compact(messages)
        self.assertEqual(messages[2]["role"], "user")
        self.assertEqual(messages[2]["content"], "2" * 30000)
        transcript = self.client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
        self.assertIn('"tool_calls"', transcript)
        self.assertIn("file.py", transcript)
        self.assertEqual(messages[4]["tool_call_id"], "call-2")

    def test_stream_handles_usage_chunk_and_argument_fragments(self):
        def chunk(content=None, calls=None, reason=None):
            return NS(choices=[NS(delta=NS(content=content, tool_calls=calls), finish_reason=reason)])
        first = NS(index=0, id="call-1", function=NS(name="read_file", arguments='{"path":'))
        second = NS(index=0, id=None, function=NS(name=None, arguments='"file.py"}'))
        response = Mock()
        response.__enter__ = Mock(return_value=iter([chunk(calls=[first]), chunk(calls=[second], reason="tool_calls"), NS(choices=[])]))
        response.__exit__ = Mock(return_value=False)
        self.client.chat.completions.create.return_value = response
        with contextlib.redirect_stdout(io.StringIO()):
            message, reason = self.agent.complete(self.messages(), [], True)
        self.assertEqual(reason, "tool_calls")
        self.assertEqual(json.loads(message["tool_calls"][0]["function"]["arguments"]), {"path": "file.py"})

    def test_compaction_of_one_long_task_keeps_complete_batches(self):
        messages = self.messages()
        for index in range(5):
            messages.extend([
                {"role": "assistant", "tool_calls": [self.call("read_file", {"path": "file.py"}, f"call-{index}")]},
                {"role": "tool", "tool_call_id": f"call-{index}", "content": "x" * 25000}])
        self.client.chat.completions.create.return_value = NS(choices=[NS(message=NS(content="Goal and progress"), finish_reason="stop")])
        with contextlib.redirect_stdout(io.StringIO()):
            self.agent.compact(messages)
        self.assertEqual(messages[1]["role"], "user")
        self.assertEqual(messages[2]["tool_calls"][0]["id"], "call-2")
        self.assertEqual(messages[3]["tool_call_id"], "call-2")

    def test_authentication_error_is_actionable(self):
        response = NS(status_code=401, request=Mock(), headers={})
        error = AuthenticationError("User not found", response=response, body={})
        output = io.StringIO()
        with patch.object(self.agent, "complete", side_effect=error), contextlib.redirect_stdout(output):
            self.assertFalse(self.agent.run(self.messages()))
        self.assertIn("Set a valid OPENROUTER_API_KEY", output.getvalue())

    def test_invalid_regex_is_recoverable(self):
        result = self.execute(self.call("grep", {"pattern": "[", "path": str(self.root)}))
        self.assertIn("Error: Invalid search regex", result)

    def test_step_limit_leaves_valid_tool_history(self):
        messages = self.messages()
        assistant = {"role": "assistant", "tool_calls": [self.call("read_file", {})]}
        with patch("nanocode.agent.MAX_STEPS", 2), patch.object(self.agent, "complete", return_value=(assistant, "tool_calls")):
            self.assertFalse(self.run_agent(messages))
        self.assertEqual([message["role"] for message in messages], ["system", "user", "assistant", "tool", "assistant", "tool"])

    def test_help_does_not_require_credentials(self):
        result = subprocess.run([sys.executable, "-m", "nanocode", "--help"], capture_output=True, text=True,
                                env={key: value for key, value in os.environ.items() if "API_KEY" not in key})
        self.assertEqual(result.returncode, 0)
        self.assertIn("--model", result.stdout)


if __name__ == "__main__":
    unittest.main()
