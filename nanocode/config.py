"""Runtime configuration. Importing this module never requires credentials."""

import os
from pathlib import Path

from openai import OpenAI

DEFAULT_MODEL = "cohere/north-mini-code:free"


def load_dotenv():
    # Project-local settings take priority over the installation's .env.
    paths = [Path.cwd() / ".env", Path(__file__).resolve().parent.parent / ".env"]
    for path in dict.fromkeys(paths):
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("export "):
                line = line[7:].strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


class Config:
    def __init__(self, model=None):
        load_dotenv()
        self.model = model or os.environ.get("MODEL") or DEFAULT_MODEL
        self.firecrawl_key = os.environ.get("FIRECRAWL_API_KEY")
        key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise ValueError("Set OPENROUTER_API_KEY (or OPENAI_API_KEY) in your .env or environment.")
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=key,
            timeout=60.0,
            max_retries=2,
        )
