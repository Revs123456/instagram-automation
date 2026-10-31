"""Configuration loaded from environment variables (or a local .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: str | os.PathLike = ".env") -> None:
    """Minimal .env loader: KEY=VALUE lines, existing env vars win."""
    p = Path(path)
    if not p.is_file():
        return
    for raw in p.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


@dataclass(frozen=True)
class Config:
    access_token: str
    ig_user_id: str
    app_secret: str = ""
    verify_token: str = ""
    graph_version: str = "v23.0"
    db_path: str = "data/igauto.db"
    rules_path: str = "config/rules.json"

    @classmethod
    def from_env(cls) -> "Config":
        load_dotenv()
        missing = [k for k in ("IG_ACCESS_TOKEN", "IG_USER_ID") if not os.environ.get(k)]
        if missing:
            raise SystemExit(
                f"Missing required settings: {', '.join(missing)}. "
                "Copy .env.example to .env and fill it in (see README)."
            )
        return cls(
            access_token=os.environ["IG_ACCESS_TOKEN"],
            ig_user_id=os.environ["IG_USER_ID"],
            app_secret=os.environ.get("IG_APP_SECRET", ""),
            verify_token=os.environ.get("IG_WEBHOOK_VERIFY_TOKEN", ""),
            graph_version=os.environ.get("IG_GRAPH_VERSION", "v23.0"),
            db_path=os.environ.get("IG_DB_PATH", "data/igauto.db"),
            rules_path=os.environ.get("IG_RULES_PATH", "config/rules.json"),
        )
