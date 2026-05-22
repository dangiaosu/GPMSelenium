from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from gpm_selenium.gpm import GpmProfile


class SessionCacheError(RuntimeError):
    pass


def save_profiles(cache_path: Path, profiles: list[GpmProfile]) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {"profiles": [cached_profile(profile) for profile in profiles]}
    cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def cached_profile(profile: GpmProfile) -> dict[str, Any]:
    profile_payload: dict[str, Any] = asdict(profile)
    profile_payload["raw_proxy"] = ""
    return profile_payload


def load_profiles(cache_path: Path) -> list[GpmProfile]:
    if not cache_path.exists():
        return []
    raw_text: str = cache_path.read_text(encoding="utf-8")
    raw_payload: Any = json.loads(raw_text)
    if not isinstance(raw_payload, dict):
        raise SessionCacheError(f"Session cache is not a JSON object; cache_path={cache_path}")
    raw_profiles: Any = raw_payload.get("profiles")
    if not isinstance(raw_profiles, list):
        raise SessionCacheError(f"Session cache missing profiles list; cache_path={cache_path}")
    return [profile_from_json(item, cache_path) for item in raw_profiles if isinstance(item, dict)]


def profile_from_json(raw_profile: dict[str, Any], cache_path: Path) -> GpmProfile:
    raw_profile_id: Any = raw_profile.get("profile_id")
    if not isinstance(raw_profile_id, str) or raw_profile_id.strip() == "":
        raise SessionCacheError(f"Cached profile missing profile_id; cache_path={cache_path}; profile={raw_profile}")
    return GpmProfile(
        profile_id=raw_profile_id.strip(),
        name=string_value(raw_profile, "name"),
        group_id=string_value(raw_profile, "group_id"),
        raw_proxy=string_value(raw_profile, "raw_proxy"),
        browser_type=string_value(raw_profile, "browser_type"),
        browser_version=string_value(raw_profile, "browser_version"),
        note=string_value(raw_profile, "note"),
        created_at=string_value(raw_profile, "created_at"),
    )


def string_value(raw_profile: dict[str, Any], key: str) -> str:
    raw_value: Any = raw_profile.get(key)
    if raw_value is None:
        return ""
    return str(raw_value).strip()
