from __future__ import annotations

import io
import json
import os
import re
import shutil
import struct
import threading
import unicodedata
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from PIL import Image, ImageFilter, UnidentifiedImageError

from .models import Game, slugify
from .paths import covers_dir, data_dir, safe_path

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36 Umbral/0.1"
)

GAMEDB_ROOT = "https://app.lizardbyte.dev/GameDB"
IGDB_IMAGE = "https://images.igdb.com/igdb/image/upload"

STEAM_PORTRAIT_URLS = (
    "https://cdn.akamai.steamstatic.com/steam/apps/{app_id}/library_600x900_2x.jpg",
    "https://cdn.akamai.steamstatic.com/steam/apps/{app_id}/library_600x900.jpg",
    "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{app_id}/library_600x900_2x.jpg",
    "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{app_id}/library_600x900.jpg",
)

CACHE_FILE = "cover_cache.json"
CACHE_TTL = timedelta(days=30)
_CACHE_LOCK = threading.Lock()

PLATFORM_IDS: dict[str, tuple[int, ...]] = {
    "switch2": (508, 130),
    "switch": (130, 508),
    "3ds": (37, 137),
    "ports": (508, 130, 6, 21, 5, 41),
    "wii": (5, 21),
    "wiiu": (41,),
    "nds": (20, 159),
    "gba": (24,),
    "gbc": (22,),
    "gb": (33,),
    "snes": (19, 58),
    "nes": (18, 99),
    "n64": (4,),
    "dreamcast": (23,),
    "saturn": (32,),
    "genesis": (29,),
    "mastersystem": (64,),
    "gamegear": (35,),
    "neogeo": (80, 136, 79),
    "arcade": (52,),
    "pce": (86,),
    "ps1": (7,),
    "ps2": (8,),
    "ps3": (9,),
    "psp": (38,),
    "psvita": (46,),
    "xbox": (11,),
    "xbox360": (12,),
    "c64": (15,),
    "amiga": (16,),
    "msx": (27,),
    "atari2600": (59,),
    "multi": (6,),
    "otros": (6,),
    "pc": (6,),
    "epic": (6,),
    "gog": (6,),
}


@dataclass
class CoverResult:
    path: Path
    source: str


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[®™©]", " ", text)
    text = re.sub(r"\[[^\]]*]|\([^)]*\)", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _compact(text: str) -> str:
    return _normalize(text).replace(" ", "")


def _bucket_key(title: str) -> str:
    cleaned = "".join(ch for ch in _normalize(title)[:2] if ch.isalnum())
    return cleaned or "@"


def _candidate_titles(game: Game) -> list[str]:
    names: list[str] = []
    values: list[str] = []
    if game.source in {"steam", "epic", "gog"}:
        values.append(game.title)
    else:
        emulated = game.system_key not in {"pc", "ports", "steam", "epic", "gog"}
        if game.rom_path:
            rom = safe_path(game.rom_path)
            is_dir = False
            try:
                is_dir = Path(game.rom_path).is_dir()
            except OSError:
                is_dir = False
            rom_name = rom.name if is_dir else rom.stem
            if emulated:
                values.append(rom_name)
                values.append(game.title)
            else:
                values.append(game.title)
                values.append(rom_name)
                if game.executable:
                    values.append(safe_path(game.executable).stem)
        else:
            values.append(game.title)
            if game.system_key not in {"ports", "steam", "epic", "gog"} and game.executable:
                values.append(safe_path(game.executable).stem)
    for value in values:
        if not value:
            continue
        text = str(value)
        text = re.sub(r"\[[^\]]*]|\([^)]*\)", " ", text)
        text = re.sub(r"[_.]+", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            continue
        variants = [text]
        comma = re.match(r"^(.+?),\s*(The|A|An|Los|Las|El|La)\s*[:\-]?\s*(.*)$", text, re.I)
        if comma:
            article = comma.group(2).title()
            rest = comma.group(3).strip()
            variants.insert(0, f"{article} {comma.group(1)}{': ' + rest if rest else ''}")
        for variant in variants:
            variant = re.sub(r"\s+", " ", variant).strip()
            if variant and variant not in names:
                names.append(variant)
    return names[:4]


def cover_path(game: Game) -> Path:
    return covers_dir() / f"{slugify(game.id)[:80]}.jpg"


def has_cover(game: Game) -> bool:
    if game.cover and Path(game.cover).is_file():
        return True
    return cover_path(game).is_file()


def find_local_cover(game: Game) -> Path | None:
    if game.cover and Path(game.cover).is_file():
        return Path(game.cover)
    return None


def game_cover(game: Game) -> Path | None:
    if game.cover and Path(game.cover).is_file():
        return Path(game.cover)
    fallback = cover_path(game)
    if fallback.is_file():
        return fallback
    return None


def clear_cover_cache(game: Game) -> None:
    target = cover_path(game)
    try:
        if target.is_file():
            target.unlink()
    except OSError:
        pass
    with _CACHE_LOCK:
        cache = _load_cache()
        key = slugify(game.id)
        if key in cache:
            cache.pop(key, None)
            _save_cache(cache)


def cover_needs_refresh(game: Game) -> bool:
    target = cover_path(game)
    manual = Path(game.cover) if game.cover else None
    if manual is not None and manual.is_file():
        try:
            if manual.resolve() != target.resolve():
                return False
        except OSError:
            return False
    path = game_cover(game)
    if path is None:
        return True
    return game.source == "steam" and is_landscape(path)


def image_size(path: Path) -> tuple[int, int]:
    try:
        with path.open("rb") as handle:
            data = handle.read(262_144)
    except OSError:
        return (0, 0)
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        try:
            width, height = struct.unpack(">II", data[16:24])
        except struct.error:
            return (0, 0)
        return (int(width), int(height))
    if data[:2] == b"\xff\xd8":
        index = 2
        while index + 9 < len(data):
            if data[index] != 0xFF:
                index += 1
                continue
            marker = data[index + 1]
            if marker in (0xD8, 0xD9):
                index += 2
                continue
            try:
                length = struct.unpack(">H", data[index + 2 : index + 4])[0]
            except struct.error:
                return (0, 0)
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                try:
                    height, width = struct.unpack(">HH", data[index + 5 : index + 9])
                except struct.error:
                    return (0, 0)
                return (int(width), int(height))
            index += 2 + length
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP" and len(data) >= 30:
        chunk = data[12:16]
        if chunk == b"VP8X" and len(data) >= 30:
            width = 1 + int.from_bytes(data[24:27], "little")
            height = 1 + int.from_bytes(data[27:30], "little")
            return (width, height)
        if chunk == b"VP8 " and len(data) >= 30 and data[23:26] == b"\x9d\x01\x2a":
            width = struct.unpack("<H", data[26:28])[0] & 0x3FFF
            height = struct.unpack("<H", data[28:30])[0] & 0x3FFF
            return (int(width), int(height))
        if chunk == b"VP8L" and len(data) >= 25 and data[20] == 0x2F:
            bits = int.from_bytes(data[21:25], "little")
            return ((bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1)
    return (0, 0)


def is_landscape(path: Path) -> bool:
    width, height = image_size(path)
    return width > 0 and height > 0 and width / height >= 1.05


def is_image_bytes(payload: bytes) -> bool:
    if payload[:8] == b"\x89PNG\r\n\x1a\n":
        return True
    if payload[:2] == b"\xff\xd8":
        return True
    if payload[:6] in (b"GIF87a", b"GIF89a"):
        return True
    if payload[:4] == b"RIFF" and payload[8:12] == b"WEBP":
        return True
    return False


def _steam_local_portrait(app_id: str) -> Path | None:
    if not app_id:
        return None
    try:
        from .stores import steam_roots
    except Exception:  # noqa: BLE001 - la portada nunca debe romper la app
        return None
    for root in steam_roots():
        candidate = root / "appcache" / "librarycache" / app_id / "library_600x900.jpg"
        try:
            if candidate.is_file() and candidate.stat().st_size > 4096:
                return candidate
        except OSError:
            continue
    return None


def _steam_portrait_urls(app_id: str) -> list[str]:
    if not app_id:
        return []
    return [template.format(app_id=app_id) for template in STEAM_PORTRAIT_URLS]


def _steam_header_cover(app_id: str) -> str:
    if not app_id:
        return ""
    try:
        data = _request_json(
            f"https://store.steampowered.com/api/appdetails?appids={app_id}&filters=basic&l=spanish",
            limit=400_000,
        )
    except (URLError, TimeoutError, OSError, ValueError):
        return ""
    entry = data.get(str(app_id)) or {}
    payload = entry.get("data") or {}
    return str(payload.get("header_image", ""))


def _load_cache() -> dict:
    path = data_dir() / CACHE_FILE
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_cache(cache: dict) -> None:
    path = data_dir() / CACHE_FILE
    try:
        temporary = path.with_name(path.name + ".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(cache, handle, ensure_ascii=False, indent=2)
        os.replace(temporary, path)
    except OSError:
        pass


def _cache_valid(entry: dict) -> bool:
    try:
        checked = datetime.fromisoformat(str(entry.get("checked_at", "")))
    except ValueError:
        return False
    if checked.tzinfo is None:
        checked = checked.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - checked < CACHE_TTL


def _request_json(url: str, limit: int = 8_000_000) -> dict:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urlopen(request, timeout=20) as response:
        payload = response.read(limit)
    data = json.loads(payload.decode("utf-8", errors="replace"))
    return data if isinstance(data, dict) else {}


def _request_bytes(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "image/*"})
    with urlopen(request, timeout=25) as response:
        return response.read(4_000_000)


def _gamedb_search(titles: list[str], system_key: str) -> dict | None:
    wanted = [pid for pid in PLATFORM_IDS.get(system_key, ()) ]
    buckets: dict[str, dict] = {}
    for title in titles:
        bucket = _bucket_key(title)
        if bucket in buckets:
            continue
        try:
            buckets[bucket] = _request_json(f"{GAMEDB_ROOT}/buckets/{bucket}.json")
        except (URLError, TimeoutError, OSError, ValueError):
            buckets[bucket] = {}
            continue

    for title in titles:
        target = _compact(title)
        if not target:
            continue
        bucket = buckets.get(_bucket_key(title)) or {}
        candidates: list[tuple[int, int, str, str]] = []
        for game_id, entry in bucket.items():
            name = str(entry.get("name", ""))
            compact = _compact(name)
            if not compact:
                continue
            if compact == target:
                score = 100
            elif compact.startswith(target) or target.startswith(compact):
                shorter = min(len(compact), len(target))
                longer = max(len(compact), len(target))
                if longer == 0 or shorter / longer < 0.72:
                    continue
                score = 70
            elif target in compact:
                score = 55
            else:
                continue
            candidates.append((score, -abs(len(compact) - len(target)), name, str(game_id)))
        for candidate in sorted(candidates, reverse=True)[:8]:
            details = _gamedb_cover(candidate[3], wanted)
            if details:
                return details
        if wanted:
            for candidate in sorted(candidates, reverse=True)[:4]:
                details = _gamedb_cover(candidate[3], [])
                if details:
                    return details
    return None


def _gamedb_cover(game_id: str, platform_ids: list[int]) -> dict | None:
    try:
        data = _request_json(f"{GAMEDB_ROOT}/games/{game_id}.json", limit=3_000_000)
    except (URLError, TimeoutError, OSError, ValueError):
        return None
    cover = data.get("cover") or {}
    url = str(cover.get("url", ""))
    if not url:
        return None
    platforms = [value for value in data.get("platforms", []) if isinstance(value, int)]
    if platform_ids and platforms and not any(pid in platform_ids for pid in platforms):
        return None
    if url.startswith("//"):
        url = "https:" + url
    if "/t_thumb/" in url:
        url_2x = url.replace("/t_thumb/", "/t_cover_big_2x/")
        url_1x = url.replace("/t_thumb/", "/t_cover_big/")
        return {
            "url": url_2x,
            "urls": [url_2x, url_1x],
            "title": str(data.get("name", "")),
            "source": "IGDB",
        }
    return {"url": url, "title": str(data.get("name", "")), "source": "IGDB"}


def _steam_app_id(game: Game) -> str:
    notes = game.notes or ""
    match = re.search(r"AppID de Steam:\s*(\d+)", notes)
    return match.group(1) if match else ""


def _steam_cover(app_id: str) -> dict | None:
    urls = _steam_portrait_urls(app_id)
    header = _steam_header_cover(app_id)
    if header:
        urls.append(header)
    if not urls:
        return None
    return {"url": urls[0], "urls": urls, "title": "", "source": "Steam"}


def _steam_search_cover(title: str) -> dict | None:
    try:
        data = _request_json(
            "https://store.steampowered.com/api/storesearch/"
            f"?term={quote(title, safe='')}&cc=ES&l=spanish",
            limit=400_000,
        )
    except (URLError, TimeoutError, OSError, ValueError):
        return None
    items = data.get("items", [])
    if not isinstance(items, list):
        return None
    target = _compact(title)
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", ""))
        app_id = item.get("id")
        compact = _compact(name)
        if not app_id or not compact:
            continue
        if compact == target or target in compact or compact in target:
            urls = _steam_portrait_urls(str(app_id))
            image = str(item.get("tiny_image", "")) or str(item.get("header_image", ""))
            if image:
                image = image.replace("capsule_sm_120", "header").replace(
                    "capsule_231x87", "header"
                )
                urls.append(image)
            header = _steam_header_cover(str(app_id))
            if header:
                urls.append(header)
            if not urls:
                continue
            return {
                "url": urls[0],
                "urls": urls,
                "title": name,
                "source": "Steam",
                "app_id": str(app_id),
            }
    return None


def _itch_cover(title: str) -> dict | None:
    try:
        data = _request_json(
            "https://itch.io/api/1/search/games?query=" + quote(title, safe=""), limit=400_000
        )
    except (URLError, TimeoutError, OSError, ValueError):
        return None
    games = data.get("games", [])
    if not isinstance(games, list):
        return None
    target = _compact(title)
    for item in games:
        if not isinstance(item, dict):
            continue
        name = str(item.get("title") or item.get("name") or "")
        compact = _compact(name)
        if not compact or not (compact == target or target in compact or compact in target):
            continue
        image = str(item.get("cover_url") or item.get("thumbnail_url") or "")
        if image:
            return {"url": image, "title": name, "source": "itch.io"}
    return None


def _resolve_online(game: Game) -> dict | None:
    if game.source == "steam":
        cover = _steam_cover(_steam_app_id(game))
        if cover:
            return cover
    titles = _candidate_titles(game)
    if not titles:
        return None
    if game.system_key in {"pc", "epic", "gog"}:
        steam = _steam_cover(_steam_app_id(game))
        if steam:
            return steam
        for title in titles:
            found = _steam_search_cover(title)
            if found:
                return found
        for title in titles:
            found = _itch_cover(title)
            if found:
                return found
    for index, title in enumerate(titles):
        found = _gamedb_search([title, *titles[:index], *titles[index + 1 :]], game.system_key)
        if found:
            return found
    if game.system_key not in {"pc", "steam", "epic", "gog"}:
        for title in titles:
            found = _itch_cover(title)
            if found:
                return found
    return None


UPSCALE_MIN_WIDTH = 600
UPSCALE_MIN_HEIGHT = 800
UPSCALE_MAX_EDGE = 1400


def upscale_cover_bytes(
    payload: bytes,
    min_width: int = UPSCALE_MIN_WIDTH,
    min_height: int = UPSCALE_MIN_HEIGHT,
    max_edge: int = UPSCALE_MAX_EDGE,
) -> bytes:
    """Upscale low-resolution cover images cleanly using Lanczos resampling and subtle sharpening."""
    if not payload or not is_image_bytes(payload):
        return payload
    try:
        with Image.open(io.BytesIO(payload)) as img:
            width, height = img.size
            if width <= 0 or height <= 0:
                return payload
            if width >= min_width and height >= min_height:
                return payload
            scale = max(min_width / width, min_height / height)
            scale = min(scale, max_edge / max(width, height))
            if scale <= 1.02:
                return payload
            new_w = max(width + 1, int(round(width * scale)))
            new_h = max(height + 1, int(round(height * scale)))
            converted = img.convert("RGBA") if "A" in img.getbands() else img.convert("RGB")
            upscaled = converted.resize((new_w, new_h), Image.Resampling.LANCZOS)
            sharpened = upscaled.filter(ImageFilter.UnsharpMask(radius=1.1, percent=65, threshold=3))
            buffer = io.BytesIO()
            fmt = (img.format or "").upper()
            if fmt == "PNG" and converted.mode == "RGBA":
                sharpened.save(buffer, format="PNG", optimize=True)
            else:
                if sharpened.mode != "RGB":
                    sharpened = sharpened.convert("RGB")
                sharpened.save(buffer, format="JPEG", quality=92, optimize=True)
            result = buffer.getvalue()
            return result if len(result) >= 512 else payload
    except (OSError, ValueError, UnidentifiedImageError):
        return payload


def _upscale_cover_file(path: Path) -> bool:
    try:
        raw = path.read_bytes()
    except OSError:
        return False
    upgraded = upscale_cover_bytes(raw)
    if upgraded == raw:
        return False
    try:
        temporary = path.with_name(path.name + ".up.tmp")
        temporary.write_bytes(upgraded)
        os.replace(temporary, path)
    except OSError:
        return False
    return True


def _download(url: str, target: Path) -> bool:
    try:
        payload = _request_bytes(url)
    except (URLError, TimeoutError, OSError, ValueError):
        return False
    if len(payload) < 1024:
        return False
    if not is_image_bytes(payload):
        return False
    payload = upscale_cover_bytes(payload)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".tmp")
        temporary.write_bytes(payload)
        os.replace(temporary, target)
    except OSError:
        return False
    return True


def _demo_base_title(title: str) -> str:
    base = re.sub(
        r"\s*[:\-]?\s*(demo|playtest|play test|beta|prueba)\s*$", "", title, flags=re.I
    ).strip()
    return base if base and base != title else ""


def _download_any(urls: list[str], target: Path) -> bool:
    for url in urls:
        if url and _download(url, target):
            return True
    return False


def _upgrade_portrait(game: Game, target: Path) -> bool:
    app_id = _steam_app_id(game)
    local = _steam_local_portrait(app_id)
    if local is not None:
        try:
            temporary = target.with_name(target.name + ".new")
            raw = local.read_bytes()
            temporary.write_bytes(upscale_cover_bytes(raw))
            os.replace(temporary, target)
            return True
        except OSError:
            pass
    temporary = target.with_name(target.name + ".new")
    urls = _steam_portrait_urls(app_id)
    header = _steam_header_cover(app_id)
    if header:
        urls.append(header)
    if not urls or not _download_any(urls, temporary):
        return False
    try:
        if is_landscape(temporary):
            temporary.unlink(missing_ok=True)
            return False
        os.replace(temporary, target)
    except OSError:
        return False
    return True


def fetch_cover(game: Game, cache: dict | None = None, use_cache: bool = True) -> Path | None:
    target = cover_path(game)
    existing = find_local_cover(game)
    if existing:
        try:
            if Path(existing).resolve() != target.resolve():
                return existing
        except OSError:
            return existing

    store = cache if cache is not None else _load_cache()
    key = slugify(game.id)
    with _CACHE_LOCK:
        entry = store.get(key) if use_cache else None

    if target.is_file():
        w, h = image_size(target)
        if (
            (w == 0 or w < UPSCALE_MIN_WIDTH or h < UPSCALE_MIN_HEIGHT)
            and not (isinstance(entry, dict) and entry.get("upscaled"))
        ):
            _upscale_cover_file(target)
            with _CACHE_LOCK:
                store[key] = {
                    **(entry if isinstance(entry, dict) else {}),
                    "status": "ok",
                    "upscaled": True,
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                }
                if cache is None:
                    _save_cache(store)
        if (
            game.source == "steam"
            and is_landscape(target)
            and not (isinstance(entry, dict) and entry.get("portrait_failed") and _cache_valid(entry))
        ):
            if _upgrade_portrait(game, target):
                with _CACHE_LOCK:
                    store[key] = {
                        "status": "ok",
                        "url": _steam_portrait_urls(_steam_app_id(game))[0],
                        "title": str((entry or {}).get("title", "")),
                        "source": "Steam",
                        "upscaled": True,
                        "checked_at": datetime.now(timezone.utc).isoformat(),
                    }
                    if cache is None:
                        _save_cache(store)
                return target
            with _CACHE_LOCK:
                store[key] = {
                    **(entry or {}),
                    "portrait_failed": True,
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                }
                if cache is None:
                    _save_cache(store)
        return target

    if isinstance(entry, dict) and _cache_valid(entry):
        if entry.get("status") == "not_found":
            retry_demo = (
                game.source == "steam"
                and bool(_demo_base_title(game.title))
                and not entry.get("demo_checked")
            )
            if not retry_demo:
                return None
        if entry.get("status") == "ok":
            urls = entry.get("urls") or [entry.get("url")]
            if _download_any([str(url) for url in urls if url], target):
                return target
            return None

    found = _resolve_online(game)
    if not found:
        with _CACHE_LOCK:
            store[key] = {
                "status": "not_found",
                "demo_checked": bool(_demo_base_title(game.title)),
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
            if cache is None:
                _save_cache(store)
        return None

    urls = [str(url) for url in (found.get("urls") or [found.get("url")]) if url]
    ok = _download_any(urls, target)
    if not ok and game.source == "steam":
        base = _demo_base_title(game.title)
        if base:
            extra = _steam_search_cover(base)
            if extra:
                extra_urls = [
                    str(url) for url in (extra.get("urls") or [extra.get("url")]) if url
                ]
                if _download_any(extra_urls, target):
                    urls = extra_urls
                    ok = True
    with _CACHE_LOCK:
        store[key] = {
            "status": "ok" if ok else "download_failed",
            "url": urls[0] if urls else "",
            "urls": urls,
            "title": str(found.get("title", "")),
            "source": str(found.get("source", "")),
            "demo_checked": bool(_demo_base_title(game.title)),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
        if cache is None:
            _save_cache(store)
    return target if ok else None


def fetch_covers(
    games: list[Game],
    missing_only: bool = True,
    workers: int = 4,
    stop_event: threading.Event | None = None,
) -> tuple[dict[str, Path], dict[str, Exception]]:
    targets = [
        game for game in games if not missing_only or cover_needs_refresh(game)
    ]
    results: dict[str, Path] = {}
    errors: dict[str, Exception] = {}
    if not targets or (stop_event is not None and stop_event.is_set()):
        return results, errors

    cache = _load_cache()
    lock_results: list[tuple[str, Path | None, Exception | None]] = []

    def work(game: Game) -> tuple[str, Path | None, Exception | None]:
        if stop_event is not None and stop_event.is_set():
            return game.id, None, None
        try:
            return game.id, fetch_cover(game, cache), None
        except Exception as error:  # noqa: BLE001 - una carátula nunca debe romper la app
            return game.id, None, error

    pool = ThreadPoolExecutor(max_workers=max(1, workers))
    aborted = False
    try:
        pending = {pool.submit(work, game) for game in targets}
        while pending:
            if stop_event is not None and stop_event.is_set():
                aborted = True
                break
            done, pending = wait(pending, timeout=0.1, return_when=FIRST_COMPLETED)
            for future in done:
                lock_results.append(future.result())
    finally:
        pool.shutdown(wait=not aborted, cancel_futures=aborted)

    with _CACHE_LOCK:
        _save_cache(cache)
    for game_id, path, error in lock_results:
        if path is not None:
            results[game_id] = path
        elif error is not None:
            errors[game_id] = error
    return results, errors
