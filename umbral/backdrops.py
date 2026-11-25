from __future__ import annotations

import html
import io
import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from PIL import Image, UnidentifiedImageError

from .covers import (
    GAMEDB_ROOT,
    PLATFORM_IDS,
    USER_AGENT,
    _bucket_key,
    _compact,
    _request_json,
    _steam_app_id,
    is_image_bytes,
)
from .models import Game, slugify
from .net import ssl_context
from .paths import backdrops_dir

STEAM_HERO_URLS = (
    "https://cdn.akamai.steamstatic.com/steam/apps/{app_id}/library_hero.jpg",
    "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{app_id}/library_hero.jpg",
    "https://cdn.akamai.steamstatic.com/steam/apps/{app_id}/page_bg_generated_v6b.jpg",
)


@dataclass(frozen=True)
class BackdropOption:
    url: str
    thumb_url: str
    title: str
    source: str


def backdrop_path(game: Game) -> Path:
    return backdrops_dir() / f"{slugify(game.title)}-{game.id[:6]}.jpg"


def game_backdrop(game: Game) -> Path | None:
    raw = (game.backdrop or "").strip()
    if not raw:
        return None
    path = Path(raw)
    try:
        if path.is_file() and path.stat().st_size > 256:
            return path
    except OSError:
        return None
    return None


def _fetch_bytes(url: str, limit: int = 12_000_000, timeout: int = 20) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "image/*,*/*;q=0.8"})
    with urlopen(request, timeout=timeout, context=ssl_context()) as response:
        return response.read(limit)


def fetch_thumbnail(url: str) -> bytes | None:
    try:
        payload = _fetch_bytes(url, limit=3_000_000, timeout=12)
    except (URLError, TimeoutError, OSError, ValueError):
        return None
    return payload if is_image_bytes(payload) else None


def download_backdrop(url: str, game: Game) -> Path | None:
    try:
        payload = _fetch_bytes(url, limit=12_000_000, timeout=25)
    except (URLError, TimeoutError, OSError, ValueError):
        return None
    if not is_image_bytes(payload):
        return None
    try:
        with Image.open(io.BytesIO(payload)) as img:
            rgb = img.convert("RGB")
            if rgb.width < 320 or rgb.height < 180:
                return None
            target = backdrop_path(game)
            rgb.save(target, format="JPEG", quality=92, optimize=True)
            return target
    except (UnidentifiedImageError, OSError, ValueError):
        return None


def _steam_options_for_app(app_id: str, title: str) -> list[BackdropOption]:
    options: list[BackdropOption] = []
    if not app_id:
        return options
    for hero_tmpl in STEAM_HERO_URLS[:1]:
        hero_url = hero_tmpl.format(app_id=app_id)
        options.append(BackdropOption(url=hero_url, thumb_url=hero_url, title=title or "Steam Hero", source="Steam"))
    try:
        data = _request_json(
            f"https://store.steampowered.com/api/appdetails?appids={app_id}&l=spanish",
            limit=600_000,
        )
    except (URLError, TimeoutError, OSError, ValueError):
        return options
    entry = data.get(str(app_id)) or {}
    payload = entry.get("data") or {}
    name = str(payload.get("name", title) or title)
    bg = str(payload.get("background_raw") or payload.get("background") or "")
    if bg:
        options.append(BackdropOption(url=bg, thumb_url=bg, title=name, source="Steam"))
    for shot in (payload.get("screenshots") or [])[:5]:
        if not isinstance(shot, dict):
            continue
        full = str(shot.get("path_full", "")).split("?")[0]
        thumb = str(shot.get("path_thumbnail", full)).split("?")[0]
        if full:
            options.append(BackdropOption(url=full, thumb_url=thumb or full, title=name, source="Steam"))
    return options


def _steam_search_backdrops(query: str) -> list[BackdropOption]:
    try:
        data = _request_json(
            f"https://store.steampowered.com/api/storesearch/?term={quote(query, safe='')}&cc=ES&l=spanish",
            limit=400_000,
        )
    except (URLError, TimeoutError, OSError, ValueError):
        return []
    items = data.get("items", [])
    if not isinstance(items, list) or not items:
        return []
    target = _compact(query)
    best_id = ""
    best_name = ""
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", ""))
        app_id = item.get("id")
        compact = _compact(name)
        if not app_id or not compact:
            continue
        if compact == target or target in compact or compact in target:
            best_id = str(app_id)
            best_name = name
            break
    if not best_id and isinstance(items[0], dict) and items[0].get("id"):
        best_id = str(items[0]["id"])
        best_name = str(items[0].get("name", query))
    return _steam_options_for_app(best_id, best_name) if best_id else []


def _igdb_url(raw_url: str, size: str) -> str:
    url = str(raw_url or "").strip()
    if not url:
        return ""
    if url.startswith("//"):
        url = "https:" + url
    if "/t_thumb/" in url:
        return url.replace("/t_thumb/", f"/{size}/")
    return url


def _gamedb_backdrops(query: str, system_key: str) -> list[BackdropOption]:
    bucket_key = _bucket_key(query)
    try:
        bucket = _request_json(f"{GAMEDB_ROOT}/buckets/{bucket_key}.json")
    except (URLError, TimeoutError, OSError, ValueError):
        return []
    target = _compact(query)
    if not target:
        return []
    wanted = set(PLATFORM_IDS.get(system_key, ()))
    candidates: list[tuple[int, int, str]] = []
    for game_id, entry in bucket.items():
        name = str(entry.get("name", ""))
        compact = _compact(name)
        if not compact:
            continue
        if compact == target:
            score = 100
        elif compact.startswith(target) or target.startswith(compact):
            score = 70
        elif target in compact:
            score = 55
        else:
            continue
        candidates.append((score, -abs(len(compact) - len(target)), str(game_id)))

    options: list[BackdropOption] = []
    for _, _, game_id in sorted(candidates, reverse=True)[:4]:
        try:
            data = _request_json(f"{GAMEDB_ROOT}/games/{game_id}.json", limit=3_000_000)
        except (URLError, TimeoutError, OSError, ValueError):
            continue
        platforms = {p for p in data.get("platforms", []) if isinstance(p, int)}
        if wanted and platforms and not (wanted & platforms) and options:
            continue
        title = str(data.get("name", query))
        for key in ("artworks", "screenshots"):
            for item in (data.get(key) or [])[:5]:
                if not isinstance(item, dict):
                    continue
                raw = str(item.get("url", ""))
                full = _igdb_url(raw, "t_1080p")
                thumb = _igdb_url(raw, "t_screenshot_med")
                if full:
                    options.append(BackdropOption(url=full, thumb_url=thumb or full, title=title, source="IGDB"))
        if len(options) >= 6:
            break
    return options


def _bing_image_search(query: str, limit: int = 8) -> list[BackdropOption]:
    search_term = f"{query} wallpaper 1080p"
    url = f"https://www.bing.com/images/search?q={quote(search_term, safe='')}&first=1&qft=+filterui:aspect-wide"
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "es-ES,es;q=0.9,en;q=0.8"})
    try:
        with urlopen(request, timeout=15, context=ssl_context()) as response:
            raw_html = response.read(1_500_000).decode("utf-8", errors="replace")
    except (URLError, TimeoutError, OSError, ValueError):
        return []
    options: list[BackdropOption] = []
    for match in re.finditer(r'm="([^"]+)"', raw_html):
        blob = html.unescape(match.group(1))
        try:
            meta = json.loads(blob)
        except ValueError:
            continue
        murl = str(meta.get("murl", "")).strip()
        turl = str(meta.get("turl", "")).strip() or murl
        title = str(meta.get("t", "")).strip() or query
        if not murl.startswith(("http://", "https://")):
            continue
        options.append(BackdropOption(url=murl, thumb_url=turl, title=title, source="Web"))
        if len(options) >= limit:
            break
    return options


def search_backdrops(query: str, game: Game | None = None, max_results: int = 12) -> list[BackdropOption]:
    clean = (query or "").strip()
    if not clean and game is not None:
        clean = game.title
    if not clean:
        return []

    raw_options: list[BackdropOption] = []
    app_id = _steam_app_id(game) if game is not None else ""
    if app_id:
        raw_options.extend(_steam_options_for_app(app_id, game.title if game else clean))
    sys_key = game.system_key if game is not None else ""
    raw_options.extend(_gamedb_backdrops(clean, sys_key))
    if not app_id:
        raw_options.extend(_steam_search_backdrops(clean))
    if len(raw_options) < max_results:
        raw_options.extend(_bing_image_search(clean, limit=max_results))

    seen: set[str] = set()
    unique: list[BackdropOption] = []
    for opt in raw_options:
        if opt.url in seen:
            continue
        seen.add(opt.url)
        unique.append(opt)
        if len(unique) >= max_results:
            break
    return unique
