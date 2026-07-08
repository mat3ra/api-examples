"""File-based OIDC token cache storage."""

import json
import os

_FILE_PATH = os.path.join(os.path.expanduser("~"), ".mat3ra", "oidc_token_cache.json")


async def read() -> dict:
    try:
        with open(_FILE_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


async def write(cache: dict) -> None:
    os.makedirs(os.path.dirname(_FILE_PATH), exist_ok=True)
    with open(_FILE_PATH, "w") as f:
        json.dump(cache, f)
