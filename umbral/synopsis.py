from __future__ import annotations

import html
import json
import os
import re
import threading
from pathlib import Path
from typing import Iterable
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from PySide6.QtCore import QThread, Signal

from .covers import _request_json, _steam_app_id
from .models import Game
from .net import ssl_context
from .paths import data_dir

_WIKI_USER_AGENT = "UmbralLauncher/8.53 (https://github.com/sanjurjogon-crypto/umbral)"
_CACHE_LOCK = threading.Lock()

_BOILERPLATE_PREFIXES = (
    "juego de steam instalado en ",
    "juego de epic games instalado en ",
    "juego de gog instalado en ",
    "juego independiente detectado en ",
    "sin descripción disponible",
)
_BOILERPLATE_SUBSTRINGS = (
    "lanzado con ",
    "umbral lo lanzará directamente",
    "port nativo para pc",
    "recreación nativa",
    "emulador propio",
)


def needs_synopsis(game: Game) -> bool:
    desc = (game.description or "").strip()
    if not desc:
        return True
    low = desc.lower()
    if any(low.startswith(prefix) for prefix in _BOILERPLATE_PREFIXES):
        return True
    if any(part in low for part in _BOILERPLATE_SUBSTRINGS) and len(desc) < 160:
        return True
    return False


def _clean_text(raw: str, max_chars: int = 260) -> str:
    text = re.sub(r"<[^>]+>", " ", html.unescape(raw or ""))
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rsplit(".", 1)[0].strip()
    if len(cut) >= 80:
        return cut + "."
    cut = text[:max_chars].rsplit(" ", 1)[0].strip()
    return (cut or text[:max_chars]).rstrip(",;:") + "…"


def _clean_search_title(title: str) -> str:
    cleaned = re.sub(r"\s*[\(\[].*?[\)\]]", "", title or "")
    cleaned = cleaned.replace("™", "").replace("®", "").replace("©", "")
    cleaned = re.sub(r"\s+[-–]\s+", ": ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _cache_file() -> Path:
    return data_dir() / "synopses.json"


def _cache_keys(game: Game) -> tuple[str, str]:
    norm_title = re.sub(r"[^a-z0-9]+", " ", _clean_search_title(game.title).lower()).strip()
    sys_key = (game.system_key or game.source or "").strip().lower()
    return (f"{sys_key}:{norm_title}" if sys_key else norm_title, f":{norm_title}")


def _load_cache() -> dict[str, str]:
    path = _cache_file()
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return {str(k): str(v) for k, v in raw.items() if isinstance(v, str) and v.strip()}
    except (OSError, ValueError):
        pass
    return {}


def _save_cache(cache: dict[str, str]) -> None:
    path = _cache_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        pass


def cached_synopsis(game: Game) -> str:
    with _CACHE_LOCK:
        cache = _load_cache()
    k1, k2 = _cache_keys(game)
    return cache.get(k1) or cache.get(k2) or ""


def store_cached_synopsis(game: Game, text: str) -> None:
    clean = (text or "").strip()
    if not clean:
        return
    k1, k2 = _cache_keys(game)
    if not k2.strip(":"):
        return
    with _CACHE_LOCK:
        cache = _load_cache()
        if cache.get(k1) == clean and cache.get(k2) == clean:
            return
        cache[k1] = clean
        cache.setdefault(k2, clean)
        _save_cache(cache)


def _steam_synopsis(game: Game) -> str:
    app_id = _steam_app_id(game)
    sys_key = (game.system_key or game.source or "").strip().lower()
    is_pc = sys_key in {"", "pc", "steam", "epic", "gog", "ports", "dusklight", "hookshot", "longshot"}
    if not app_id and is_pc and game.title:
        clean_title = _clean_search_title(game.title)
        search_url = (
            "https://store.steampowered.com/api/storesearch/"
            f"?term={quote(clean_title, safe='')}&cc=ES&l=spanish"
        )
        data = _request_json(search_url)
        items = data.get("items") if isinstance(data, dict) else None
        if isinstance(items, list) and items:
            first = items[0]
            if isinstance(first, dict) and first.get("id"):
                hit_name = re.sub(r"[^a-z0-9]+", " ", str(first.get("name") or "").lower()).strip()
                want_name = re.sub(r"[^a-z0-9]+", " ", clean_title.lower()).strip()
                if want_name and (want_name in hit_name or hit_name in want_name):
                    app_id = str(first["id"])
    if not app_id:
        return ""
    details_url = (
        f"https://store.steampowered.com/api/appdetails?appids={app_id}&l=spanish"
    )
    payload = _request_json(details_url)
    entry = payload.get(str(app_id)) if isinstance(payload, dict) else None
    if not isinstance(entry, dict) or not entry.get("success"):
        return ""
    info = entry.get("data")
    if not isinstance(info, dict):
        return ""
    raw = str(info.get("short_description") or "").strip()
    return _clean_text(raw) if raw else ""


def _wikipedia_synopsis(title: str, lang: str = "es") -> str:
    clean_title = _clean_search_title(title)
    if not clean_title:
        return ""
    queries = (
        f"{clean_title} {'videojuego' if lang == 'es' else 'video game'}",
        clean_title,
    )
    for query in queries:
        search_url = (
            f"https://{lang}.wikipedia.org/w/api.php?action=query&list=search"
            f"&srsearch={quote(query, safe='')}&srlimit=3&format=json"
        )
        try:
            req = Request(search_url, headers={"User-Agent": _WIKI_USER_AGENT})
            with urlopen(req, timeout=10, context=ssl_context()) as resp:
                data = json.loads(resp.read(256_000).decode("utf-8", errors="ignore"))
        except (URLError, TimeoutError, OSError, ValueError):
            continue

        hits = data.get("query", {}).get("search", []) if isinstance(data, dict) else []
        for hit in hits[:2]:
            page_title = str(hit.get("title") or "").strip()
            if not page_title:
                continue
            extract_url = (
                f"https://{lang}.wikipedia.org/w/api.php?action=query&prop=extracts"
                f"&exintro=1&explaintext=1&redirects=1&titles={quote(page_title, safe='')}&format=json"
            )
            try:
                req = Request(extract_url, headers={"User-Agent": _WIKI_USER_AGENT})
                with urlopen(req, timeout=10, context=ssl_context()) as resp:
                    ex_data = json.loads(resp.read(256_000).decode("utf-8", errors="ignore"))
            except (URLError, TimeoutError, OSError, ValueError):
                continue

            pages = ex_data.get("query", {}).get("pages", {}) if isinstance(ex_data, dict) else {}
            for page in pages.values():
                if not isinstance(page, dict):
                    continue
                extract = str(page.get("extract") or "").strip()
                low = extract.lower()
                if not extract or "puede referirse a" in low or "may refer to" in low:
                    continue
                return _clean_text(extract)
    return ""


def fetch_synopsis(game: Game) -> str:
    """Fetch a clean synopsis from local cache, Steam (Spanish), or Wikipedia ES/EN."""
    cached = cached_synopsis(game)
    if cached:
        return cached
    text = _steam_synopsis(game)
    if not text:
        text = _wikipedia_synopsis(game.title, lang="es")
    if not text:
        text = _wikipedia_synopsis(game.title, lang="en")
    if text:
        store_cached_synopsis(game, text)
    return text


class SynopsisWorker(QThread):
    updated = Signal(list)

    def __init__(self, games: Iterable[Game]) -> None:
        super().__init__()
        self._games = list(games)
        self._stop = threading.Event()

    def cancel(self) -> None:
        self._stop.set()
        self.requestInterruption()

    def run(self) -> None:
        batch: list[tuple[str, str]] = []
        for idx, game in enumerate(self._games):
            if self._stop.is_set() or self.isInterruptionRequested():
                break
            try:
                text = fetch_synopsis(game)
            except Exception:  # noqa: BLE001
                text = ""
            if text:
                batch.append((game.id, text))
                # Emit early for the first game and every 3 games thereafter so synopses persist incrementally
                if idx == 0 or len(batch) >= 3:
                    if not self._stop.is_set() and not self.isInterruptionRequested():
                        self.updated.emit(list(batch))
                    batch.clear()
        if batch and not self._stop.is_set() and not self.isInterruptionRequested():
            self.updated.emit(batch)
