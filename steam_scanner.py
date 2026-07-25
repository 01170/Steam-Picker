from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

try:
    import winreg
except ImportError:
    winreg = None


LOGGER = logging.getLogger(__name__)
_MANIFEST_RE = re.compile(r"^appmanifest_(\d+)\.acf$", re.IGNORECASE)
_VDF_PAIR_RE = re.compile(r'"((?:\\.|[^"])*)"\s+"((?:\\.|[^"])*)"')
_IMAGE_EXTENSIONS = {".ico", ".png", ".jpg", ".jpeg", ".webp"}


@dataclass
class SteamGame:
    appid: str
    name: str
    install_dir: str
    icon_path: Optional[str] = None
    icon_source: Optional[str] = None


@dataclass(frozen=True)
class ScanStats:
    libraries: int = 0
    manifests_seen: int = 0
    malformed_manifests: int = 0
    duplicates: int = 0
    games: int = 0
    icons_found: int = 0
    missing_icons: int = 0


LAST_SCAN_STATS = ScanStats()


def _clean_vdf_value(value: str) -> str:
    return value.replace(r"\\", "\\").replace(r"\"", '"')


def _parse_vdf_kv(text: str) -> dict[str, str]:
    return {
        _clean_vdf_value(key).lower(): _clean_vdf_value(value)
        for key, value in _VDF_PAIR_RE.findall(text)
    }


def _read_text(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as exc:
        LOGGER.warning("Could not read %s: %s", path, exc)
        return None


def find_steam_install() -> Optional[str]:
    if winreg is not None:
        registry_values = [
            (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
            (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamExe"),
            (
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\WOW6432Node\Valve\Steam",
                "InstallPath",
            ),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath"),
        ]
        for hive, key_path, value_name in registry_values:
            try:
                with winreg.OpenKey(hive, key_path) as key:
                    value, _ = winreg.QueryValueEx(key, value_name)
                candidate = Path(value)
                if value_name == "SteamExe":
                    candidate = candidate.parent
                if candidate.is_dir():
                    return os.path.normpath(str(candidate))
            except (FileNotFoundError, OSError, TypeError):
                continue

    for candidate in (
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Steam",
        Path(os.environ.get("PROGRAMFILES", "")) / "Steam",
        Path(r"C:\Program Files (x86)\Steam"),
        Path(r"C:\Program Files\Steam"),
    ):
        if candidate.is_dir():
            return os.path.normpath(str(candidate))
    return None


def _path_key(path: Path) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def find_library_folders(steam_path: str) -> list[str]:
    primary = Path(steam_path) / "steamapps"
    candidates = [primary]
    library_file = primary / "libraryfolders.vdf"
    text = _read_text(library_file) if library_file.is_file() else None
    if text:
        for raw_path in re.findall(r'"path"\s+"((?:\\.|[^"])*)"', text, re.I):
            candidates.append(Path(_clean_vdf_value(raw_path)) / "steamapps")

    libraries: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = _path_key(candidate)
        if key not in seen and candidate.is_dir():
            seen.add(key)
            libraries.append(os.path.normpath(str(candidate)))
    return libraries


def _normalize_name(name: str) -> str:
    return re.sub(r"[^\w\s]", "", name, flags=re.UNICODE).strip().casefold()


def find_shortcut_icons() -> dict[str, str]:
    try:
        import glob
        import win32com.client
    except ImportError:
        LOGGER.debug("pywin32 unavailable; skipping shortcut icon fallback")
        return {}

    directories = [
        Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
        / "Microsoft/Windows/Start Menu/Programs/Steam",
        Path(os.environ.get("APPDATA", ""))
        / "Microsoft/Windows/Start Menu/Programs/Steam",
    ]
    mapping: dict[str, str] = {}
    try:
        shell = win32com.client.Dispatch("WScript.Shell")
    except Exception as exc:
        LOGGER.debug("Could not initialize shortcut reader: %s", exc)
        return mapping

    for directory in directories:
        if not directory.is_dir():
            continue
        for shortcut_path in glob.glob(str(directory / "*.lnk")):
            try:
                shortcut = shell.CreateShortCut(shortcut_path)
                icon_file = (shortcut.IconLocation or "").split(",", 1)[0].strip()
                path = Path(os.path.expandvars(icon_file))
                if path.suffix.lower() in _IMAGE_EXTENSIONS and path.is_file():
                    mapping[_normalize_name(Path(shortcut_path).stem)] = str(path)
            except Exception as exc:
                LOGGER.debug("Could not inspect shortcut %s: %s", shortcut_path, exc)
    return mapping


def match_shortcut_icon(
    game_name: str, shortcut_map: dict[str, str]
) -> Optional[str]:
    return shortcut_map.get(_normalize_name(game_name))


def _manifest_icon_hashes(data: dict[str, str]) -> list[str]:
    hashes: list[str] = []
    for key in ("clienticon", "icon"):
        value = data.get(key, "").strip()
        if re.fullmatch(r"[0-9a-fA-F]{8,64}", value) and value not in hashes:
            hashes.append(value)
    return hashes


def _existing_file(candidates: Iterable[Path]) -> Optional[str]:
    for candidate in candidates:
        try:
            if candidate.is_file() and candidate.stat().st_size > 0:
                return os.path.normpath(str(candidate))
        except OSError:
            continue
    return None


def _find_hashed_icon(steam_path: str, hashes: Iterable[str]) -> Optional[str]:
    roots = (
        Path(steam_path) / "steam/games",
        Path(steam_path) / "games",
        Path(steam_path) / "appcache/librarycache",
    )
    candidates: list[Path] = []
    for icon_hash in hashes:
        for root in roots:
            for extension in (".ico", ".png", ".jpg", ".jpeg"):
                candidates.append(root / f"{icon_hash}{extension}")
    return _existing_file(candidates)


def _cache_candidates(steam_path: str, appid: str) -> Iterable[Path]:
    cache = Path(steam_path) / "appcache/librarycache"
    app_cache = cache / appid

    preferred_names = (
        "clienticon.ico",
        "clienticon.png",
        "clienticon.jpg",
        "icon.ico",
        "icon.png",
        "icon.jpg",
    )
    for name in preferred_names:
        yield app_cache / name
    for suffix in (
        "_clienticon.ico",
        "_clienticon.png",
        "_clienticon.jpg",
        "_icon.ico",
        "_icon.png",
        "_icon.jpg",
    ):
        yield cache / f"{appid}{suffix}"

    if app_cache.is_dir():
        try:
            yield from sorted(
                (
                    path
                    for path in app_cache.iterdir()
                    if path.is_file()
                    and path.suffix.lower() in _IMAGE_EXTENSIONS
                    and "icon" in path.stem.casefold()
                ),
                key=lambda path: (
                    "clienticon" not in path.stem.casefold(),
                    path.suffix.lower() != ".ico",
                    path.name.casefold(),
                ),
            )
        except OSError:
            return


def _find_square_cache_icon(steam_path: str, appid: str) -> Optional[str]:
    app_cache = Path(steam_path) / "appcache/librarycache" / appid
    if not app_cache.is_dir():
        return None

    try:
        from PIL import Image
    except ImportError:
        LOGGER.debug("Pillow unavailable; cannot inspect hash-named cache images")
        return None

    candidates: list[tuple[int, int, Path]] = []
    try:
        files = app_cache.iterdir()
    except OSError:
        return None

    for path in files:
        if not path.is_file() or path.suffix.lower() not in _IMAGE_EXTENSIONS:
            continue
        if any(
            word in path.stem.casefold()
            for word in ("hero", "logo", "header", "capsule", "library")
        ):
            continue
        try:
            with Image.open(path) as image:
                width, height = image.size
        except (OSError, ValueError):
            continue
        if width <= 0 or height <= 0:
            continue

        ratio = width / height
        if 0.85 <= ratio <= 1.15:
            squareness = abs(width - height)
            area = width * height
            candidates.append((squareness, area, path))

    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1], item[2].name.casefold()))
    return os.path.normpath(str(candidates[0][2]))


def find_icon(
    steam_path: str,
    appid: str,
    metadata: Optional[dict[str, str]] = None,
) -> Optional[str]:
    hashes = _manifest_icon_hashes(metadata or {})

    return (
        _find_hashed_icon(steam_path, hashes)
        or _existing_file(_cache_candidates(steam_path, appid))
        or _find_square_cache_icon(steam_path, appid)
    )


def _resolve_icon(
    steam_path: str,
    appid: str,
    name: str,
    metadata: dict[str, str],
    shortcut_icons: dict[str, str],
) -> tuple[Optional[str], Optional[str]]:
    hashes = _manifest_icon_hashes(metadata)
    icon = _find_hashed_icon(steam_path, hashes)
    if icon:
        return icon, "steam icon hash"

    icon = _existing_file(_cache_candidates(steam_path, appid))
    if icon:
        return icon, "Steam library cache"

    icon = _find_square_cache_icon(steam_path, appid)
    if icon:
        return icon, "Steam square cache asset"

    icon = match_shortcut_icon(name, shortcut_icons)
    if icon:
        return icon, "Start Menu shortcut"
    return None, None


def scan_installed_games(steam_path: Optional[str] = None) -> list[SteamGame]:
    global LAST_SCAN_STATS

    steam_path = steam_path or find_steam_install()
    if steam_path is None:
        raise RuntimeError(
            "Couldn't find a Steam install. Is Steam installed on this machine?"
        )

    libraries = find_library_folders(steam_path)
    if not libraries:
        raise RuntimeError(f"No Steam library folders found under {steam_path!r}.")

    shortcut_icons = find_shortcut_icons()
    games_by_appid: dict[str, SteamGame] = {}
    manifests_seen = malformed = duplicates = icons_found = 0

    for library_name in libraries:
        library = Path(library_name)
        try:
            manifests = sorted(library.glob("appmanifest_*.acf"))
        except OSError as exc:
            LOGGER.warning("Could not list Steam library %s: %s", library, exc)
            continue

        for manifest in manifests:
            manifests_seen += 1
            filename_match = _MANIFEST_RE.match(manifest.name)
            text = _read_text(manifest)
            if text is None:
                malformed += 1
                continue

            data = _parse_vdf_kv(text)
            appid = data.get("appid") or (
                filename_match.group(1) if filename_match else None
            )
            name = data.get("name", "").strip()
            if not appid or not appid.isdigit() or not name:
                malformed += 1
                LOGGER.warning("Skipping malformed manifest: %s", manifest)
                continue

            if appid in games_by_appid:
                duplicates += 1
                continue

            install_folder = data.get("installdir", "").strip()
            install_dir = install_folder
            icon_path, icon_source = _resolve_icon(
                steam_path, appid, name, data, shortcut_icons
            )
            if icon_path:
                icons_found += 1

            games_by_appid[appid] = SteamGame(
                appid=appid,
                name=name,
                install_dir=install_dir,
                icon_path=icon_path,
                icon_source=icon_source,
            )

    games = sorted(games_by_appid.values(), key=lambda game: game.name.casefold())
    LAST_SCAN_STATS = ScanStats(
        libraries=len(libraries),
        manifests_seen=manifests_seen,
        malformed_manifests=malformed,
        duplicates=duplicates,
        games=len(games),
        icons_found=icons_found,
        missing_icons=len(games) - icons_found,
    )
    LOGGER.info(
        "Steam scan complete: %d games in %d libraries; %d icons found, "
        "%d missing, %d malformed manifests, %d duplicates",
        LAST_SCAN_STATS.games,
        LAST_SCAN_STATS.libraries,
        LAST_SCAN_STATS.icons_found,
        LAST_SCAN_STATS.missing_icons,
        LAST_SCAN_STATS.malformed_manifests,
        LAST_SCAN_STATS.duplicates,
    )
    return games


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        found = scan_installed_games()
    except RuntimeError as exc:
        raise SystemExit(f"Error: {exc}") from exc

    print(f"\nFound {len(found)} installed games:\n")
    for game in found:
        status = game.icon_source or "no icon"
        print(f"  [{game.appid}] {game.name} ({status})")
    print(f"\nStats: {LAST_SCAN_STATS}")
