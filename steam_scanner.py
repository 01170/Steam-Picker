"""
steam_scanner.py

Finds your Steam install, walks every library folder, and returns a clean
list of installed games (name, appid, icon path). No network calls -
everything is read straight off disk from Steam's own cache.
"""

import os
import re
import winreg
from dataclasses import dataclass
from typing import Optional


@dataclass
class SteamGame:
    appid: str
    name: str
    install_dir: str
    icon_path: Optional[str] = None


def find_steam_install() -> Optional[str]:
    """
    Locate the Steam install folder. Tries the Windows registry first,
    then falls back to the handful of paths Steam almost always installs
    to, in case the registry lookup comes back empty on this machine.
    """
    reg_paths = [
        (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam"),
    ]
    for hive, path in reg_paths:
        try:
            with winreg.OpenKey(hive, path) as key:
                install_path, _ = winreg.QueryValueEx(key, "SteamPath")
                return os.path.normpath(install_path)
        except (FileNotFoundError, OSError):
            continue

    fallback_paths = [
        r"C:\Program Files (x86)\Steam",
        r"C:\Program Files\Steam",
    ]
    for path in fallback_paths:
        if os.path.isdir(path):
            return os.path.normpath(path)

    return None


def _parse_vdf_kv(text: str) -> dict:
    """
    Minimal VDF (Valve Data Format) parser - good enough for the flat
    key/value pairs we need out of appmanifest and libraryfolders files.
    Avoids pulling in an external vdf dependency for something this small.
    """
    result = {}
    # Matches "key"   "value"
    for match in re.finditer(r'"([^"]+)"\s+"([^"]*)"', text):
        result[match.group(1).lower()] = match.group(2)
    return result


def find_library_folders(steam_path: str) -> list[str]:
    """
    Steam can install games across multiple drives. libraryfolders.vdf
    (in steamapps/) lists every additional library path.
    """
    libraries = [os.path.join(steam_path, "steamapps")]

    vdf_path = os.path.join(steam_path, "steamapps", "libraryfolders.vdf")
    if not os.path.exists(vdf_path):
        return libraries

    with open(vdf_path, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()

    # Library entries look like:  "path"   "D:\\SteamLibrary"
    for match in re.finditer(r'"path"\s+"([^"]+)"', text):
        raw_path = match.group(1).replace("\\\\", "\\")
        lib_steamapps = os.path.join(raw_path, "steamapps")
        if lib_steamapps not in libraries and os.path.isdir(lib_steamapps):
            libraries.append(lib_steamapps)

    return libraries


def _normalize_name(name: str) -> str:
    """Strip trademark symbols/punctuation and lowercase, so 'South Park (TM):
    The Stick of Truth' and 'south park the stick of truth' line up."""
    return re.sub(r"[^\w\s]", "", name).strip().lower()


def find_shortcut_icons() -> dict[str, str]:
    """
    Steam creates a Start Menu shortcut per installed game, each pointing
    at a correctly-matched .ico file. This turns out to be the most
    reliable icon source we've got - no cache-layout guessing, no
    network calls. Returns {normalized_game_name: icon_file_path}.
    """
    import glob

    try:
        import win32com.client
    except ImportError:
        print("  [shortcut icons] pywin32 isn't installed - run: pip install pywin32")
        return {}

    search_dirs = [
        r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Steam",
        os.path.join(
            os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Steam"
        ),
    ]

    # Only accept actual image files as icons. A shortcut's IconLocation
    # can point at the game's .exe instead of a .ico if no custom icon
    # was set - PIL can't open that, so treat it as "no icon" rather than
    # silently storing an unusable path.
    valid_exts = {".ico", ".png", ".jpg", ".jpeg"}

    mapping: dict[str, str] = {}
    shell = win32com.client.Dispatch("WScript.Shell")
    lnk_count = 0

    for directory in search_dirs:
        if not os.path.isdir(directory):
            continue
        for lnk_path in glob.glob(os.path.join(directory, "*.lnk")):
            lnk_count += 1
            try:
                shortcut = shell.CreateShortCut(lnk_path)
                icon_file = (shortcut.IconLocation or "").split(",")[0].strip()
                if os.path.splitext(icon_file)[1].lower() not in valid_exts:
                    continue
                if os.path.exists(icon_file):
                    game_name = os.path.splitext(os.path.basename(lnk_path))[0]
                    mapping[_normalize_name(game_name)] = icon_file
            except Exception:
                continue

    print(f"  [shortcut icons] found {lnk_count} shortcuts, resolved {len(mapping)} usable icons")
    return mapping


def match_shortcut_icon(game_name: str, shortcut_map: dict[str, str]) -> Optional[str]:
    """Match a scanned game name against the shortcut map - exact match
    first, then a fuzzy fallback for minor name differences."""
    key = _normalize_name(game_name)
    if key in shortcut_map:
        return shortcut_map[key]

    import difflib
    close = difflib.get_close_matches(key, shortcut_map.keys(), n=1, cutoff=0.85)
    return shortcut_map[close[0]] if close else None


def find_icon(steam_path: str, appid: str) -> Optional[str]:
    """
    Steam caches artwork locally once a game's installed - no API call
    needed for most games. Two things make this trickier than it should be:

    1. The small square "_icon.jpg" is only cached if you've triggered a
       UI element that shows it, so it's missing for a lot of games.
       Box art (library_600x900) is shown every time you browse your
       library, so it's cached far more reliably - prioritize that.
    2. Steam has used two different cache layouts over the years: older
       installs use flat "<appid>_suffix.jpg" filenames, newer ones use
       a per-appid folder. Check both.
    """
    cache_dir = os.path.join(steam_path, "appcache", "librarycache")
    candidates = [
        # Newer folder-based layout
        os.path.join(cache_dir, appid, "library_600x900.jpg"),
        os.path.join(cache_dir, appid, "icon.jpg"),
        os.path.join(cache_dir, appid, "logo.jpg"),
        # Older flat-file layout
        os.path.join(cache_dir, f"{appid}_library_600x900.jpg"),
        os.path.join(cache_dir, f"{appid}_icon.jpg"),
        os.path.join(cache_dir, f"{appid}_logo.jpg"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def fetch_icon_from_cdn(appid: str, cache_dir: str) -> Optional[str]:
    """
    Fallback for games with no locally cached art: pull box art straight
    from Steam's public CDN (no API key required) and cache it to disk
    so we only ever fetch it once per game.
    """
    import urllib.request
    import urllib.error

    os.makedirs(cache_dir, exist_ok=True)
    dest_path = os.path.join(cache_dir, f"{appid}.jpg")
    if os.path.exists(dest_path):
        return dest_path

    # Steam's CDN 403s requests with no User-Agent, and not every game has
    # both filename variants published - try a couple of combinations.
    urls = [
        f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/library_600x900.jpg",
        f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/library_600x900_2x.jpg",
        f"https://steamcdn-a.akamaihd.net/steam/apps/{appid}/library_600x900.jpg",
    ]

    for url in urls:
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                data = response.read()
            with open(dest_path, "wb") as f:
                f.write(data)
            return dest_path
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
            continue

    return None


def scan_installed_games(steam_path: Optional[str] = None) -> list[SteamGame]:
    """
    Main entry point. Returns every installed game found across all
    Steam library folders, with a resolved icon path where available.
    """
    if steam_path is None:
        steam_path = find_steam_install()
    if steam_path is None:
        raise RuntimeError(
            "Couldn't find a Steam install. Is Steam installed on this machine?"
        )

    games = []
    shortcut_icons = find_shortcut_icons()

    for library in find_library_folders(steam_path):
        if not os.path.isdir(library):
            continue
        for filename in os.listdir(library):
            if not (filename.startswith("appmanifest_") and filename.endswith(".acf")):
                continue

            manifest_path = os.path.join(library, filename)
            try:
                with open(manifest_path, "r", encoding="utf-8", errors="ignore") as f:
                    data = _parse_vdf_kv(f.read())
            except OSError:
                continue

            appid = data.get("appid")
            name = data.get("name")
            install_dir = data.get("installdir", "")
            if not appid or not name:
                continue

            # Shortcut icons only - deliberately no fallback to box art or
            # CDN cover images. Mixing square icons with rectangular cover
            # art in the tiny screen cutout looked inconsistent, so a
            # missing shortcut just means "no icon" (placeholder tile)
            # rather than a mismatched photo.
            icon_path = match_shortcut_icon(name, shortcut_icons)
            icon_source = "shortcut" if icon_path else None

            games.append(
                SteamGame(
                    appid=appid,
                    name=name,
                    install_dir=install_dir,
                    icon_path=icon_path,
                )
            )
            games[-1].icon_source = icon_source  # type: ignore[attr-defined]

    # De-dupe just in case a game shows up in more than one library entry
    seen = set()
    unique_games = []
    for g in games:
        if g.appid not in seen:
            seen.add(g.appid)
            unique_games.append(g)

    return sorted(unique_games, key=lambda g: g.name.lower())


if __name__ == "__main__":
    # Quick manual test - run this file directly on your own machine to
    # sanity check the scanner before we wire up the GUI.
    try:
        found = scan_installed_games()
        print(f"\nFound {len(found)} installed games:\n")
        for game in found:
            source = getattr(game, "icon_source", None)
            if game.icon_path:
                status = f"icon found via {source}"
            else:
                status = "no icon"
            print(f"  [{game.appid}] {game.name}  ({status})")
    except RuntimeError as e:
        print(f"Error: {e}")
