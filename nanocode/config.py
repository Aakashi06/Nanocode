"""Configuration module for nanocode.

This module handles loading configuration from environment variables.
Sensitive credentials like API keys are loaded from the environment
rather than being hardcoded in the source code.
"""

import os
from pathlib import Path

from openai import OpenAI


def _load_dotenv():
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


_load_dotenv()


class Config:
    """Central configuration class for nanocode.

    All sensitive values are loaded from environment variables to avoid
    leaking credentials in source control. If a required environment
    variable is not set, a clear error message is raised.

    Attributes:
        OPENAI_API_KEY: API key for the OpenAI-compatible endpoint.
        FIRECRAWL_API_KEY: API key for the Firecrawl web scraping service.
        MODEL: The model identifier to use for completions.
    """

    def __init__(self):
        """Initialize configuration from environment variables.

        Raises:
            ValueError: If required environment variables are not set.
        """
        self.OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
        self.FIRECRAWL_API_KEY = os.environ.get("FIRECRAWL_API_KEY")
        self.MODEL = os.environ.get("MODEL", "poolside/laguna-s-2.1:free")

        if not self.OPENAI_API_KEY:
            raise ValueError(
                "OPENAI_API_KEY environment variable is required. "
                "Set it with: export OPENAI_API_KEY='your-api-key-here'"
            )
        if not self.FIRECRAWL_API_KEY:
            raise ValueError(
                "FIRECRAWL_API_KEY environment variable is required. "
                "Set it with: export FIRECRAWL_API_KEY='your-api-key-here'"
            )

        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=self.OPENAI_API_KEY,
        )


# Create a singleton config instance for convenience
config = Config()

client = config.client
MODEL = config.MODEL
FIRECRAWL_API_KEY = config.FIRECRAWL_API_KEY