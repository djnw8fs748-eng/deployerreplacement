"""Secret resolution and management.

Resolution order:
1. Shell environment variables
2. .stackr.env file (auto-loaded, gitignored)
3. Auto-generated secrets (written back to .stackr.env on first deploy)
"""

from __future__ import annotations

import os
import re
import secrets
from pathlib import Path

from dotenv import dotenv_values


ENV_FILE_NAME = ".stackr.env"
_VAR_RE = re.compile(r"\$\{([^}]+)\}")


def load_env_file(config_dir: Path) -> dict[str, str]:
    env_file = config_dir / ENV_FILE_NAME
    if env_file.exists():
        return {k: v for k, v in dotenv_values(env_file).items() if v is not None}
    return {}


def build_env(config_dir: Path) -> dict[str, str]:
    """Merge shell env + .stackr.env with shell env taking highest priority.

    Load order: file first, then shell env overwrites — so a CI pipeline can
    override any .stackr.env value by setting an environment variable.
    """
    env: dict[str, str] = {}
    env.update(load_env_file(config_dir))
    env.update({k: v for k, v in os.environ.items()})
    return env


def find_unresolved(value: str, env: dict[str, str]) -> list[str]:
    return [m for m in _VAR_RE.findall(value) if m not in env]


def resolve(value: str, env: dict[str, str]) -> str:
    def _replace(match: re.Match) -> str:  # type: ignore[type-arg]
        key = match.group(1)
        if key not in env:
            raise KeyError(f"Unresolved secret: ${{{key}}}")
        return env[key]

    return _VAR_RE.sub(_replace, value)


def resolve_dict(d: dict, env: dict[str, str]) -> dict:
    """Recursively resolve ${VAR} in all string values of a dict."""
    result = {}
    for k, v in d.items():
        if isinstance(v, str):
            result[k] = resolve(v, env)
        elif isinstance(v, dict):
            result[k] = resolve_dict(v, env)
        else:
            result[k] = v
    return result


def generate_secret(length: int = 32) -> str:
    return secrets.token_urlsafe(length)


def ensure_secret(key: str, config_dir: Path, env: dict[str, str]) -> str:
    """Return an existing secret or generate and persist a new one."""
    if key in env:
        return env[key]
    value = generate_secret()
    _append_to_env_file(config_dir, key, value)
    env[key] = value
    return value


def _append_to_env_file(config_dir: Path, key: str, value: str) -> None:
    env_file = config_dir / ENV_FILE_NAME
    with open(env_file, "a") as f:
        f.write(f"{key}={value}\n")


def init_env_file(config_dir: Path) -> Path:
    env_file = config_dir / ENV_FILE_NAME
    if not env_file.exists():
        env_file.write_text("# Stackr secrets — DO NOT COMMIT THIS FILE\n")
    return env_file
