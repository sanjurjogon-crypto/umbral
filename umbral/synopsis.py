from __future__ import annotations

import html
import json
import os
import re
import threading
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Iterable
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from PySide6.QtCore import QThread, Signal

from .covers import (
    GAMEDB_ROOT,
    PLATFORM_IDS,
    _bucket_key,
    _compact,
    _request_json,
    _steam_app_id,
)
from .models import Game
from .net import ssl_context
from .paths import data_dir

_WIKI_USER_AGENT = "UmbralLauncher/8.58 (https://github.com/sanjurjogon-crypto/umbral)"
_CACHE_LOCK = threading.Lock()
_CACHE_VERSION = 6

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
    "third person bp game template",
    "arranca desde tu propia copia",
    "se ejecuta con tu emulador",
    "usa tu propia copia",
    "vuelto a imaginar para",
    "reconstruido para pc",
)


def needs_synopsis(game: Game) -> bool:
    desc = (game.description or "").strip()
    if not desc or len(desc) < 28:
        return True
    low = desc.lower()
    if re.sub(r"[^a-z0-9]+", "", low) == re.sub(r"[^a-z0-9]+", "", (game.title or "").lower()):
        return True
    if any(low.startswith(prefix) for prefix in _BOILERPLATE_PREFIXES):
        return True
    if any(part in low for part in _BOILERPLATE_SUBSTRINGS) and len(desc) < 260:
        return True
    if any(pat in low for pat in _DEV_LEAD_PATTERNS):
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
    cleaned = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", cleaned)
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
        if isinstance(raw, dict) and raw.get("_v") == _CACHE_VERSION:
            return {
                str(k): str(v)
                for k, v in raw.items()
                if k != "_v" and isinstance(v, str) and v.strip()
            }
    except (OSError, ValueError):
        pass
    return {}


def _save_cache(cache: dict[str, str]) -> None:
    path = _cache_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        payload: dict[str, object] = {"_v": _CACHE_VERSION, **cache}
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
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
        try:
            data = _request_json(search_url)
        except (URLError, TimeoutError, OSError, ValueError):
            return ""
        items = data.get("items") if isinstance(data, dict) else None
        if isinstance(items, list) and items:
            first = items[0]
            if isinstance(first, dict) and first.get("id"):
                hit_comp = _compact(str(first.get("name") or ""))
                want_comp = _compact(clean_title)
                if want_comp and (
                    hit_comp == want_comp
                    or hit_comp.removeprefix("the") == want_comp.removeprefix("the")
                ):
                    app_id = str(first["id"])
    if not app_id:
        return ""
    details_url = (
        f"https://store.steampowered.com/api/appdetails?appids={app_id}&l=spanish"
    )
    try:
        payload = _request_json(details_url)
    except (URLError, TimeoutError, OSError, ValueError):
        return ""
    entry = payload.get(str(app_id)) if isinstance(payload, dict) else None
    if not isinstance(entry, dict) or not entry.get("success"):
        return ""
    info = entry.get("data")
    if not isinstance(info, dict):
        return ""
    raw = str(info.get("short_description") or "").strip()
    return _clean_text(raw) if raw else ""


_DEV_LEAD_PATTERNS = (
    "es un videojuego",
    "fue un videojuego",
    "desarrollado por",
    "publicado por",
    "distribuido por",
    "comenzó a distribuir",
    "versión física",
    "fue lanzado",
    "se lanzó",
    "salió a la venta",
    "fue anunciado",
    "anunciado en",
    "publicado en",
    "lanzado en",
    "se hizo cargo",
    "interactive entertainment",
    "psyonix",
    "cronología de los juegos",
    "is a video game",
    "is an action",
    "is a role-playing",
    "is a survival",
    "developed by",
    "published by",
    "distributed by",
    "released for",
)


def _wiki_title_matches(game_title: str, wiki_title: str) -> bool:
    want = _compact(_clean_search_title(game_title))
    clean_wiki = re.sub(r"\s*\([^)]*\)\s*$", "", wiki_title or "")
    got = _compact(_clean_search_title(clean_wiki))
    if not want or not got:
        return False
    return want == got or want.removeprefix("the") == got.removeprefix("the")


def _strip_dev_sentences(text: str) -> str:
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    kept = [
        s
        for s in sentences
        if not any(pat in s.lower() for pat in _DEV_LEAD_PATTERNS)
    ]
    return " ".join(kept).strip()


def _extract_wiki_plot_or_gameplay(extract: str, lang: str) -> str:
    # Split plain-text Wikipedia extract into sections by == Heading ==
    parts = re.split(r"(?m)^=+\s*([^=\n]+?)\s*=+\s*$", extract)
    intro = parts[0].strip() if parts else ""
    sections: list[tuple[str, str]] = []
    for idx in range(1, len(parts) - 1, 2):
        sections.append((parts[idx].strip().lower(), parts[idx + 1].strip()))

    preferred = (
        ("argumento", "sinopsis", "trama", "historia", "premisa", "jugabilidad", "modo de juego")
        if lang == "es"
        else ("plot", "premise", "synopsis", "story", "gameplay")
    )
    for kw in preferred:
        for heading, body in sections:
            if kw in heading and len(body) >= 40:
                return _clean_text(body)

    # Fallback to intro only after stripping pure development/release sentences
    if intro:
        trimmed = _strip_dev_sentences(intro)
        if len(trimmed) >= 45:
            return _clean_text(trimmed)
    return ""


def _gamedb_synopsis(game: Game) -> str:
    clean_title = _clean_search_title(game.title)
    if not clean_title:
        return ""
    target = _compact(clean_title)
    if not target:
        return ""
    try:
        bucket = _request_json(f"{GAMEDB_ROOT}/buckets/{_bucket_key(clean_title)}.json")
    except (URLError, TimeoutError, OSError, ValueError):
        return ""
    if not isinstance(bucket, dict):
        return ""

    candidates: list[tuple[int, str]] = []
    for gid, entry in bucket.items():
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "")
        comp = _compact(name)
        if not comp:
            continue
        if comp == target:
            candidates.append((100, str(gid)))
        elif comp.removeprefix("the") == target.removeprefix("the"):
            candidates.append((90, str(gid)))
    candidates.sort(reverse=True)

    wanted = set(PLATFORM_IDS.get((game.system_key or "").lower(), ()))
    for _score, gid in candidates[:4]:
        try:
            details = _request_json(f"{GAMEDB_ROOT}/games/{gid}.json", limit=3_000_000)
        except (URLError, TimeoutError, OSError, ValueError):
            continue
        if not isinstance(details, dict):
            continue
        platforms = [p for p in details.get("platforms", []) if isinstance(p, int)]
        if wanted and platforms and not any(pid in wanted for pid in platforms):
            continue
        raw = str(details.get("storyline") or details.get("summary") or "").strip()
        if len(raw) >= 28:
            return _clean_text(raw)
    return ""


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
        for hit in hits[:3]:
            page_title = str(hit.get("title") or "").strip()
            if not page_title or not _wiki_title_matches(title, page_title):
                continue
            extract_url = (
                f"https://{lang}.wikipedia.org/w/api.php?action=query&prop=extracts"
                f"&explaintext=1&redirects=1&titles={quote(page_title, safe='')}&format=json"
            )
            try:
                req = Request(extract_url, headers={"User-Agent": _WIKI_USER_AGENT})
                with urlopen(req, timeout=10, context=ssl_context()) as resp:
                    ex_data = json.loads(resp.read(512_000).decode("utf-8", errors="ignore"))
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
                parsed = _extract_wiki_plot_or_gameplay(extract, lang)
                if parsed:
                    return parsed
    return ""


def _looks_spanish(text: str) -> bool:
    low = f" {(text or '').lower()} "
    if any(ch in low for ch in "ñ¿¡"):
        return True
    markers = (" el ", " la ", " los ", " las ", " de ", " del ", " que ", " en ", " un ", " una ", " para ", " con ")
    hits = sum(1 for m in markers if m in low)
    if hits >= 3:
        return True
    return hits >= 1 and any(ch in low for ch in "áéíóúü")


def _translate_to_spanish(text: str) -> str:
    clean = (text or "").strip()
    if not clean or _looks_spanish(clean):
        return clean
    url = (
        "https://translate.googleapis.com/translate_a/single"
        f"?client=gtx&sl=auto&tl=es&dt=t&q={quote(clean, safe='')}"
    )
    req = Request(url, headers={"User-Agent": _WIKI_USER_AGENT})
    try:
        with urlopen(req, timeout=6, context=ssl_context()) as response:
            payload = json.loads(response.read(200_000).decode("utf-8", errors="replace"))
        if isinstance(payload, list) and payload and isinstance(payload[0], list):
            translated = "".join(
                str(part[0]) for part in payload[0] if isinstance(part, list) and part and part[0]
            ).strip()
            if translated:
                return _clean_text(translated, max_chars=280)
    except (URLError, TimeoutError, OSError, ValueError):
        pass
    return clean


def fetch_synopsis(game: Game) -> str:
    """Fetch a clean synopsis (plot/premise/gameplay) in Spanish from cache, Steam, Wikipedia ES, GameDB, or Wikipedia EN."""
    cached = cached_synopsis(game)
    if cached:
        return cached
    text = _steam_synopsis(game)
    if not text:
        text = _wikipedia_synopsis(game.title, lang="es")
    if not text:
        text = _gamedb_synopsis(game)
    if not text:
        text = _wikipedia_synopsis(game.title, lang="en")
    if text:
        text = _translate_to_spanish(text)
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
        if not self._games:
            return
        batch: list[tuple[str, str]] = []
        emitted_first = False
        pool = ThreadPoolExecutor(max_workers=min(4, len(self._games)))
        try:
            future_map = {pool.submit(fetch_synopsis, game): game for game in self._games}
            pending = set(future_map.keys())
            while pending:
                if self._stop.is_set() or self.isInterruptionRequested():
                    break
                done, pending = wait(pending, timeout=0.1, return_when=FIRST_COMPLETED)
                for fut in done:
                    game = future_map[fut]
                    try:
                        text = fut.result()
                    except Exception:  # noqa: BLE001
                        text = ""
                    if text or (game.description or "").strip():
                        batch.append((game.id, text))
                        if not emitted_first or len(batch) >= 3:
                            emitted_first = True
                            if not self._stop.is_set() and not self.isInterruptionRequested():
                                self.updated.emit(list(batch))
                            batch.clear()
            if batch and not self._stop.is_set() and not self.isInterruptionRequested():
                self.updated.emit(batch)
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
