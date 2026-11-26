from __future__ import annotations

import html
import json
import re
import threading
from pathlib import Path
from typing import Iterable
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from PySide6.QtCore import QThread, Signal

from .covers import USER_AGENT, _request_json, _steam_app_id
from .models import Game
from .net import ssl_context

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


def _steam_synopsis(game: Game) -> str:
    app_id = _steam_app_id(game)
    if not app_id and game.title:
        search_url = (
            "https://store.steampowered.com/api/storesearch/"
            f"?term={quote(game.title, safe='')}&cc=ES&l=spanish"
        )
        data = _request_json(search_url)
        items = data.get("items") if isinstance(data, dict) else None
        if isinstance(items, list) and items:
            first = items[0]
            if isinstance(first, dict) and first.get("id"):
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
    clean_title = re.sub(r"\s+", " ", title or "").strip()
    if not clean_title:
        return ""
    search_url = (
        f"https://{lang}.wikipedia.org/w/api.php?action=query&list=search"
        f"&srsearch={quote(clean_title + (' videojuego' if lang == 'es' else ' video game'), safe='')}"
        "&srlimit=3&format=json"
    )
    try:
        req = Request(search_url, headers={"User-Agent": USER_AGENT})
        with urlopen(req, timeout=10, context=ssl_context()) as resp:
            data = json.loads(resp.read(256_000).decode("utf-8", errors="ignore"))
    except (URLError, TimeoutError, OSError, ValueError):
        return ""

    hits = data.get("query", {}).get("search", []) if isinstance(data, dict) else []
    if not hits:
        return ""
    page_title = str(hits[0].get("title") or "").strip()
    if not page_title:
        return ""

    extract_url = (
        f"https://{lang}.wikipedia.org/w/api.php?action=query&prop=extracts"
        f"&exintro=1&explaintext=1&redirects=1&titles={quote(page_title, safe='')}&format=json"
    )
    try:
        req = Request(extract_url, headers={"User-Agent": USER_AGENT})
        with urlopen(req, timeout=10, context=ssl_context()) as resp:
            ex_data = json.loads(resp.read(256_000).decode("utf-8", errors="ignore"))
    except (URLError, TimeoutError, OSError, ValueError):
        return ""

    pages = ex_data.get("query", {}).get("pages", {}) if isinstance(ex_data, dict) else {}
    for page in pages.values():
        if isinstance(page, dict):
            extract = str(page.get("extract") or "").strip()
            if extract:
                return _clean_text(extract)
    return ""


def fetch_synopsis(game: Game) -> str:
    """Fetch a clean synopsis silently from Steam (Spanish) or Wikipedia ES/EN."""
    text = _steam_synopsis(game)
    if text:
        return text
    text = _wikipedia_synopsis(game.title, lang="es")
    if text:
        return text
    return _wikipedia_synopsis(game.title, lang="en")


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
        changes: list[tuple[str, str]] = []
        for game in self._games:
            if self._stop.is_set() or self.isInterruptionRequested():
                break
            try:
                text = fetch_synopsis(game)
            except Exception:  # noqa: BLE001
                text = ""
            if text:
                changes.append((game.id, text))
        if not self._stop.is_set() and not self.isInterruptionRequested():
            self.updated.emit(changes)
