# NanoCode

**Python agent harness that turns plain-English requests into file operations and terminal commands.**

NanoCode connects an OpenRouter model to your local project. It can inspect code, propose changes, execute approved tools, and use the results to decide what to do next—all from your terminal.

<img width="2506" height="1476" alt="NanoCode terminal interface" src="https://github.com/user-attachments/assets/8fc11d57-1ca6-4591-b142-65f2c42e0429" />

## At a glance

| Metric | Current implementation |
|---|---|
| Tools | **6 core tools + 2 optional web tools** |
| Regression tests | **22 tests**, runnable without API credentials or network access |
| Direct runtime dependencies | **1**: the OpenAI Python SDK |
| Python requirement | **3.10+** |
| Agent execution limit | **40 model/tool rounds per user request** |
| Shell timeout | **60 seconds by default**, configurable by the tool up to **300 seconds** |
| Tool output budget | **16,000 characters**, plus truncation notices |
| Search limit | **100 matches**, also subject to the output budget |
| File reading | **200 lines by default**, up to **500 lines per request** |
| History compaction trigger | **100,000 serialized characters**, not tokens |

These numbers describe implemented limits and test counts. They are not latency, accuracy, or benchmark claims. One task can require multiple API requests, and provider retries or summarization can add requests.

## What you can do

- Understand an unfamiliar codebase and trace how a feature works.
- Search for relevant files and investigate reported errors.
- Make focused changes after reviewing the proposed edits.
- Run tests and inspect command output and exit codes.
- Create small scripts or utilities within a project.
- Fetch documentation or search the web when Firecrawl is configured.

NanoCode works in the directory where you launch it. It lists top-level entries for the model, then reads relevant files through tools as needed.

## Features

- **Terminal interface:** a framed wordmark, short startup animation, workspace details, example prompts, and BUILD/PLAN indicators.
- **Streaming responses:** display text as it arrives, with an animated indicator while waiting.
- **Tool execution loop:** pass tool descriptions to the model, validate requests, execute tools, and return their results.
- **Approval previews:** display file diffs before approved edits or writes; ask before shell commands.
- **Read-only planning:** hide mutating tools from the model and block their execution when plan mode is enabled.
- **Recoverable errors:** return invalid arguments, missing files, ambiguous edits, and tool failures to the model as feedback.
- **Bounded execution:** limit rounds, shell duration, search results, file ranges, and tool output.
- **History compaction:** summarize older context while keeping complete tool-call/result groups.
- **Project instructions:** load rules from a local NANOCODE.md.
- **Focused file editing:** require one unique exact match and replace files atomically.
- **Interrupt handling:** cancel the current task and preserve valid tool-result history for the next request.

## How it works

An agent harness is the software surrounding the model: it manages context, exposes tools, controls execution, and feeds results back.

In NanoCode, the **model decides which action to request**, the **tool performs the action**, and the **harness coordinates the process**.

~~~text
User request
     |
     v
Model receives instructions, history, and tool schemas
     |
     +---- Final answer --------------------> Terminal
     |
     v
Tool request
     |
     v
Validate arguments and check permissions
     |
     v
Execute tool and add its result to history
     |
     +--------------------------------------> Model
~~~

For example, a bug-fixing task may involve searching for a function, reading its file, proposing an edit, requesting approval, running tests, and reporting the observed result. Verification depends on the task and model; NanoCode does not automatically guarantee that every change is tested.

## Tools

| Tool | Changes files or runs commands? | Purpose |
|---|---|---|
| read_file | No | Read numbered UTF-8 lines, with a continuation offset. |
| grep | No | Search by regex, skipping common dependency directories, Git internals, and .env files during directory searches. |
| write_file | Yes | Create or overwrite a UTF-8 file, creating parent directories as needed. |
| edit_file | Yes | Replace a single unique exact string in a file. |
| bash | Yes | Execute a non-interactive shell command and return its exit code and output. |
| todo_write | No | Display a task checklist. |
| web_fetch | No local mutation | Fetch a URL through Firecrawl; requires a Firecrawl key. |
| web_search | No local mutation | Return up to 5 web results through Firecrawl; requires a Firecrawl key. |

Web tools are registered only when FIRECRAWL_API_KEY is configured. Child agents are not part of the current implementation.

## Requirements

- Python 3.10 or newer.
- An OpenRouter API key.
- Internet access for model requests.
- An interactive terminal for the conversational interface and approval prompts.
- Optionally, a Firecrawl API key for web tools.

The setup commands below target macOS/Linux. The regression suite uses POSIX shell commands and was verified on macOS.

## Quick start

~~~bash
git clone https://github.com/Aakashi06/Nanocode.git
cd Nanocode

python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .

cp .env.example .env
~~~

Edit .env and replace the placeholder with your OpenRouter key:

~~~dotenv
OPENROUTER_API_KEY=your-openrouter-api-key
MODEL=cohere/north-mini-code:free

# Optional: enable web_fetch and web_search.
# FIRECRAWL_API_KEY=your-firecrawl-api-key
~~~

Launch NanoCode:

~~~bash
nanocode
~~~

It opens in the **current terminal**. At the prompt, try:

~~~text
Explain this project and identify its main entry point. Do not modify files.
~~~

Keep credentials in .env or environment variables. The repository ignores .env.

## Work on another project

Activate NanoCode's environment, then change into the project you want to inspect:

~~~bash
source /absolute/path/to/Nanocode/.venv/bin/activate
cd /absolute/path/to/your-project
nanocode
~~~

Your launch directory becomes the working directory for file tools and shell commands. The installation's .env remains a fallback configuration source when running from another folder.

## Commands and usage

### Interactive commands

| Command | Action |
|---|---|
| /help | Show available commands and an example task. |
| /plan | Toggle read-only planning mode. |
| /model | Show the current model. |
| /model MODEL_ID | Switch models and start a fresh conversation. |
| /clear | Start a fresh conversation. |
| /exit | Quit; /quit is an alias. |

Press **Ctrl+C** to interrupt the current task or input. Press **Ctrl+D** at the prompt to exit.

### One task, then exit

~~~bash
nanocode -p "Read pyproject.toml and summarize its dependencies."
~~~

### Start in planning mode

~~~bash
nanocode --plan
~~~

Plan mode blocks edits, writes, and all shell commands, including test commands. Turn it off with /plan when ready to execute an approved change.

### Choose a model

~~~bash
nanocode --model cohere/north-mini-code:free
~~~

### CLI flags

| Flag | Purpose |
|---|---|
| -p, --prompt | Run one task and exit. |
| --plan | Start in read-only planning mode. |
| --model | Override the configured OpenRouter model ID. |
| --no-stream | Print complete responses instead of streaming them. |
| -y, --yes | Automatically approve edits, writes, and commands. |
| --repl | Compatibility flag for older invocations; the default is already the current-terminal interface. |

Use auto-approval only when you intend to authorize the requested actions. With non-interactive input, use -p; mutating actions are denied unless -y is supplied. Failed or interrupted one-shot tasks return a nonzero exit status.

### Terminal display

Color and animation are enabled in supported interactive terminals. Redirected output and dumb terminals use a static display.

~~~bash
# Disable animation but keep color.
NANOCODE_NO_ANIMATION=1 nanocode

# Disable color and animation.
NO_COLOR=1 nanocode
~~~

## Configuration

| Setting | Purpose |
|---|---|
| OPENROUTER_API_KEY | Preferred credential for OpenRouter requests. |
| OPENAI_API_KEY | Supported alternative credential name; requests still go to OpenRouter. |
| MODEL | Default model ID, unless overridden by --model. |
| FIRECRAWL_API_KEY | Optional credential enabling both web tools. |
| NO_COLOR | Disable colors and animation when set. |
| NANOCODE_NO_ANIMATION | Disable animation when set. |

Existing environment variables take precedence over .env values. NanoCode reads the working directory's .env first, then the installation's .env for settings not already present. OPENROUTER_API_KEY takes precedence over OPENAI_API_KEY.

The default model is cohere/north-mini-code:free. Other OpenRouter models can be selected, but they must support tool calling to execute agent tasks. Restart NanoCode after changing credentials; /model changes only the model.

Free models have provider and account limits. A new key on the same account does not reset account quota. Availability and free pricing can change; consult [OpenRouter's limits documentation](https://openrouter.ai/docs/api-reference/limits).

## Project instructions

Create NANOCODE.md in the directory where you launch NanoCode:

~~~markdown
Keep changes focused.
Use the Python standard library where possible.
Run relevant tests after changing behavior.
Ask before adding dependencies.
~~~

The first 16,000 characters are included in the system prompt as project instructions.

## Testing

~~~bash
python -m unittest discover -s tests -v
~~~

The suite currently contains **22 regression tests** covering:

- Argument validation and recovery from malformed tool requests.
- File ranges, parent-directory creation, unique edits, and permission preservation.
- Search exclusions, binary files, and invalid regular expressions.
- Approval denial and plan-mode enforcement.
- Shell exit codes, timeouts, and bounded output.
- Tool-loop recovery, empty responses, and incomplete responses.
- Compaction of multiple conversations and individual long tasks.
- Interrupted tool batches and step-limit handling.
- Streamed tool-argument fragments and usage-only chunks.
- Authentication guidance and credential-free CLI help.

These tests mock model requests. Passing them verifies the tested harness behaviors; it does not prove model accuracy or uninterrupted API availability.

## Troubleshooting

| Symptom | Next step |
|---|---|
| API key required | Set OPENROUTER_API_KEY in .env or your environment. |
| 401: key rejected | Check the credential and restart; an exported key can override your .env. |
| 403: access denied | Check key permissions and provider/privacy settings. |
| 404: model unavailable | Select an available model with --model or /model. |
| 429: rate limited | Check account quota and provider capacity; switching models helps only when the limit is provider-specific. |
| Empty or incomplete response | Try a smaller task or another compatible model. |
| Edit matched zero or multiple times | Provide a unique exact string with more surrounding context. |
| Command timed out | Narrow the command or ask for a longer timeout, up to 300 seconds. |
| Tool output truncated | Ask for a smaller file range or narrower search. |
| nanocode not found | Activate the virtual environment and run python -m pip install -e . |

## Scope and limitations

- Approval prompts are not an operating-system sandbox. Approved commands run with your user's permissions, and file paths are not restricted to the launch directory.
- Conversation history exists in memory; sessions are not persisted or resumed after exit.
- Shell commands are non-interactive. Directory changes inside one shell command do not persist into later commands.
- Compaction summarizes context and may lose details.
- Code and tool output sent to the model leave your machine through OpenRouter.
- Model-generated changes require review, and outcomes depend on the selected model and provider.

## Project structure

~~~text
Nanocode/
├── nanocode/
│   ├── __main__.py       # CLI entry point and interactive commands
│   ├── agent.py          # Model/tool loop, streaming, and compaction
│   ├── config.py         # Environment settings and OpenRouter client
│   ├── tools.py          # File, shell, checklist, and optional web tools
│   ├── ui.py             # Welcome screen, spinner, and approval previews
│   └── __init__.py
├── tests/
│   └── test_nanocode.py  # 22 regression tests
├── .env.example
├── .gitignore
├── pyproject.toml
├── requirements.txt
└── README.md
~~~

## License

MIT, as designated by the original project README. A standalone LICENSE file has not yet been added.
