# Nanocode

A minimal terminal coding agent built in Python — one small piece at a time. Nanocode reads your prompts, calls tools, streams replies, and asks before running anything that changes your system.

## Features

- **Streaming replies** — token-by-token output in the terminal
- **Tool loop** — the model can read files, search, edit, run bash, fetch URLs, and more
- **Permission gate** — write/edit/bash/sub-agent tools prompt `[y/n]` before running
- **Plan mode** — toggle with `/plan` to block mutating tools until you approve the plan
- **Sub-agents** — spawn isolated child agents for focused tasks
- **Compaction** — long conversations are summarized automatically to save context
- **Project instructions** — drop a `NANOCODE.md` in your cwd for custom rules

## Tools

| Tool | Name | Read-only | Description |
|------|------|-----------|-------------|
| Read file | `read_file` | yes | Read a UTF-8 text file |
| Write file | `write_file` | no | Write content to a file |
| Edit file | `edit_file` | no | Replace an exact string in a file |
| Grep | `grep` | yes | Search files for a regex |
| Bash | `bash` | no | Run a shell command |
| Todo | `todo_write` | yes | Store and display a task checklist |
| Web fetch | `web_fetch` | yes | Fetch a URL as readable text (Firecrawl) |
| Web search | `web_search` | yes | Search the web (Firecrawl) |
| Sub-agent | `task` | no | Run a fresh agent loop on a sub-task |

## Requirements

- Python 3.10+
- [OpenRouter](https://openrouter.ai/) API key (OpenAI-compatible)
- [Firecrawl](https://firecrawl.dev/) API key (for web fetch/search)

## Setup

```bash
git clone https://github.com/Aakashi06/Nanocode.git
cd Nanocode

python3 -m venv .venv
source .venv/bin/activate

pip install -e .
```

Create a `.env` file in the project root:

```bash
OPENAI_API_KEY=your-openrouter-api-key
FIRECRAWL_API_KEY=your-firecrawl-api-key
```

Optional — override the default model:

```bash
MODEL=poolside/laguna-s-2.1:free
```

See `.env.example` for a template.

## Usage

### Interactive REPL

```bash
nanocode
```

On macOS this opens a new Terminal window. To run in the current terminal:

```bash
python -m nanocode --repl
```

```
┌─────────────────────────────────────────┐
│  nanocode · tiny coding agent           │
│  /plan          toggle plan mode        │
│  ctrl-c / ctrl-d  quit                  │
└─────────────────────────────────────────┘

› 
```

Type `/plan` to toggle plan mode (prompt changes to `plan ›`).

### One-shot prompt

```bash
nanocode -p "Read pyproject.toml and summarize it"
```

### CLI flags

| Flag | Description |
|------|-------------|
| `-p`, `--prompt` | Run a single prompt and exit |
| `-y`, `--yes` | Auto-approve mutating tools |
| `--no-stream` | Disable streaming output |
| `--repl` | Run REPL in the current terminal |

## Project instructions

Create `NANOCODE.md` in your working directory. Its contents are injected into the system prompt under **Project instructions**.

## Project structure

```
Nanocode/
├── nanocode/
│   ├── __main__.py   # CLI entry point and REPL
│   ├── agent.py      # Agent loop, streaming, compaction
│   ├── config.py     # API keys and client (loads .env)
│   └── tools.py      # Tool definitions
├── pyproject.toml
├── requirements.txt
└── .env              # your keys (not committed)
```

## License

MIT
