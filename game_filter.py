import json
import os
import time
import urllib.error
import urllib.request
from typing import Optional

APP_DATA_DIR = os.path.join(os.environ.get("LOCALAPPDATA", "."), "GamePicker")
TYPE_CACHE_PATH = os.path.join(APP_DATA_DIR, "app_type_cache.json")
EXCLUDE_LIST_PATH = os.path.join(APP_DATA_DIR, "excluded.json")

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def _load_type_cache() -> dict:
    if not os.path.exists(TYPE_CACHE_PATH):
        return {}
    try:
        with open(TYPE_CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_type_cache(cache: dict) -> None:
    os.makedirs(APP_DATA_DIR, exist_ok=True)
    with open(TYPE_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)


def _fetch_app_type(appid: str) -> Optional[str]:

    url = f"https://store.steampowered.com/api/appdetails?appids={appid}&filters=basic"
    try:
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=5) as response:
            payload = json.load(response)
        entry = payload.get(str(appid), {})
        if not entry.get("success"):
            return None
        return entry.get("data", {}).get("type", "").lower() or None
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None


def classify_appids(appids: list[str], progress_callback=None) -> dict[str, str]:

    cache = _load_type_cache()
    to_fetch = [a for a in appids if a not in cache]

    for i, appid in enumerate(to_fetch, start=1):
        app_type = _fetch_app_type(appid)
        if app_type is not None:
            cache[appid] = app_type
        if progress_callback:
            progress_callback(i, len(to_fetch))
        time.sleep(0.2)

    if to_fetch:
        _save_type_cache(cache)

    return {appid: cache.get(appid, "unknown") for appid in appids}


def load_excluded() -> set[str]:
    if not os.path.exists(EXCLUDE_LIST_PATH):
        return set()
    try:
        with open(EXCLUDE_LIST_PATH, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except (json.JSONDecodeError, OSError):
        return set()


def save_excluded(excluded: set[str]) -> None:
    os.makedirs(APP_DATA_DIR, exist_ok=True)
    with open(EXCLUDE_LIST_PATH, "w", encoding="utf-8") as f:
        json.dump(sorted(excluded), f, indent=2)


def add_to_excluded(appid: str) -> None:
    excluded = load_excluded()
    excluded.add(appid)
    save_excluded(excluded)


def remove_from_excluded(appid: str) -> None:
    excluded = load_excluded()
    excluded.discard(appid)
    save_excluded(excluded)


GAME_TYPES = {"game"}


def filter_games(games: list, progress_callback=None) -> list:
    excluded = load_excluded()
    appids = [g.appid for g in games]
    types = classify_appids(appids, progress_callback=progress_callback)

    return [
        g for g in games
        if types.get(g.appid) in GAME_TYPES and g.appid not in excluded
    ]


if __name__ == "__main__":
    from steam_scanner import scan_installed_games

    all_games = scan_installed_games()
    print(f"Scanned {len(all_games)} installed apps.\n")

    def progress(done, total):
        print(f"  classifying... {done}/{total}", end="\r")

    filtered = filter_games(all_games, progress_callback=progress)
    print(f"\n\n{len(filtered)} eligible for the picker after filtering:\n")
    for g in filtered:
        print(f"  [{g.appid}] {g.name}")
