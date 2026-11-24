from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from . import __version__
from .paths import data_dir

REPO = "sanjurjogon-crypto/umbral"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"
ASSET_NAME = "Umbral.exe"
USER_AGENT = f"Umbral/{__version__}"


class UpdateError(Exception):
    pass


class UpdateCancelled(Exception):
    pass


@dataclass
class UpdateInfo:
    version: str
    tag: str
    notes: str
    asset_url: str
    asset_name: str
    size: int
    digest: str
    sha_url: str
    page_url: str
    published_at: str


def parse_version(text: str) -> tuple[int, ...]:
    cleaned = re.sub(r"^[vV\s]+", "", str(text or "").strip())
    parts = re.findall(r"\d+", cleaned)
    if not parts:
        return ()
    return tuple(int(part) for part in parts[:4])


def is_newer(remote: str, current: str) -> bool:
    remote_key = parse_version(remote)
    current_key = parse_version(current)
    if not remote_key or not current_key:
        return False
    size = max(len(remote_key), len(current_key))
    padded_remote = remote_key + (0,) * (size - len(remote_key))
    padded_current = current_key + (0,) * (size - len(current_key))
    return padded_remote > padded_current


def _request_json(url: str, timeout: float = 8.0) -> dict:
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        payload = response.read(1_500_000)
    return json.loads(payload.decode("utf-8"))


def _clean_notes(text: str) -> str:
    clean = str(text or "").replace("\ufeff", "").replace("\r\n", "\n").strip()
    if len(clean) > 6000:
        clean = clean[:6000].rsplit("\n", 1)[0] + "\n…"
    return clean


def _pick_asset(assets: list[dict]) -> Optional[dict]:
    candidates = [item for item in assets if isinstance(item, dict)]
    for item in candidates:
        if str(item.get("name", "")).lower() == ASSET_NAME.lower():
            return item
    for item in candidates:
        if str(item.get("name", "")).lower().endswith(".exe"):
            return item
    return None


def _info_from_payload(payload: dict) -> Optional[UpdateInfo]:
    tag = str(payload.get("tag_name") or payload.get("name") or "").strip()
    version = tag[1:] if tag.lower().startswith("v") else tag
    if not version:
        return None
    assets = payload.get("assets") or []
    if not isinstance(assets, list):
        assets = []
    asset = _pick_asset(assets)
    if asset is None:
        raise UpdateError("El release no incluye Umbral.exe.")
    size = int(asset.get("size") or 0)
    digest = str(asset.get("digest") or "")
    sha_url = ""
    for item in assets:
        if str(item.get("name", "")).lower() == (ASSET_NAME + ".sha256").lower():
            sha_url = str(item.get("browser_download_url", ""))
            break
    return UpdateInfo(
        version=version,
        tag=tag,
        notes=_clean_notes(str(payload.get("body") or "")),
        asset_url=str(asset.get("browser_download_url") or ""),
        asset_name=str(asset.get("name") or ASSET_NAME),
        size=size,
        digest=digest,
        sha_url=sha_url,
        page_url=str(payload.get("html_url") or RELEASES_PAGE),
        published_at=str(payload.get("published_at") or ""),
    )


def check_for_update(current: str = __version__, timeout: float = 8.0) -> Optional[UpdateInfo]:
    try:
        payload = _request_json(API_LATEST, timeout=timeout)
    except HTTPError as exc:
        if exc.code == 404:
            return None
        if exc.code in (403, 429):
            raise UpdateError("GitHub ha limitado las comprobaciones. Inténtalo dentro de un rato.") from exc
        raise UpdateError(f"GitHub respondió con un error {exc.code}.") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise UpdateError("No se pudo conectar con GitHub.") from exc
    except (ValueError, UnicodeDecodeError) as exc:
        raise UpdateError("GitHub devolvió una respuesta que no se pudo leer.") from exc
    if payload.get("draft") or payload.get("prerelease"):
        return None
    info = _info_from_payload(payload)
    if info is None or not is_newer(info.version, current):
        return None
    if not info.asset_url.startswith("https://github.com/"):
        raise UpdateError("El release apunta a una dirección no válida.")
    return info


def update_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    path = Path(base) / "Umbral" / "update"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _read_sha_file(url: str) -> str:
    try:
        request = Request(url, headers={"User-Agent": USER_AGENT})
        with urlopen(request, timeout=8.0) as response:
            text = response.read(4096).decode("utf-8", "ignore")
    except (HTTPError, URLError, OSError, TimeoutError, ValueError):
        return ""
    match = re.search(r"\b([0-9a-fA-F]{64})\b", text)
    return match.group(1).lower() if match else ""


def _download_bytes(
    url: str,
    target: Path,
    expected_size: int,
    progress: Optional[Callable[[int, int], None]],
    cancel_event: Optional[threading.Event],
) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    temporary = target.with_name(target.name + ".part")
    digest = hashlib.sha256()
    done = 0
    try:
        with urlopen(request, timeout=30.0) as response:
            total = int(response.headers.get("Content-Length") or expected_size or 0)
            with temporary.open("wb") as handle:
                while True:
                    if cancel_event is not None and cancel_event.is_set():
                        raise UpdateCancelled()
                    chunk = response.read(262_144)
                    if not chunk:
                        break
                    handle.write(chunk)
                    digest.update(chunk)
                    done += len(chunk)
                    if progress is not None:
                        progress(done, total)
        if done < 1024:
            raise UpdateError("La descarga quedó vacía.")
        if expected_size and done != expected_size:
            raise UpdateError("La descarga no coincide con el tamaño esperado.")
        with temporary.open("rb") as handle:
            if handle.read(2) != b"MZ":
                raise UpdateError("El archivo descargado no es un ejecutable válido.")
        os.replace(temporary, target)
    except UpdateCancelled:
        temporary.unlink(missing_ok=True)
        raise
    except HTTPError as exc:
        temporary.unlink(missing_ok=True)
        raise UpdateError(f"No se pudo descargar la actualización (error {exc.code}).") from exc
    except (URLError, TimeoutError, OSError) as exc:
        temporary.unlink(missing_ok=True)
        raise UpdateError("No se pudo descargar la actualización. Revisa tu conexión.") from exc
    finally:
        if temporary.exists():
            temporary.unlink(missing_ok=True)
    return digest.hexdigest()


def download_update(
    info: UpdateInfo,
    progress: Optional[Callable[[int, int], None]] = None,
    cancel_event: Optional[threading.Event] = None,
) -> Path:
    target = update_dir() / f"Umbral-{slug_version(info.version)}.exe"
    for old in update_dir().glob("Umbral-*.exe"):
        if old != target:
            old.unlink(missing_ok=True)
    digest = _download_bytes(info.asset_url, target, info.size, progress, cancel_event)
    expected = ""
    if info.digest.lower().startswith("sha256:"):
        expected = info.digest.split(":", 1)[1].strip().lower()
    elif info.digest and re.fullmatch(r"[0-9a-fA-F]{64}", info.digest):
        expected = info.digest.lower()
    if not expected and info.sha_url:
        expected = _read_sha_file(info.sha_url)
        if not expected:
            target.unlink(missing_ok=True)
            raise UpdateError(
                "No se pudo comprobar la firma SHA-256 de la actualización. "
                "Vuelve a intentarlo en unos segundos."
            )
    if expected and digest != expected:
        target.unlink(missing_ok=True)
        raise UpdateError("La firma del archivo no coincide. La actualización se ha descartado.")
    return target


def slug_version(version: str) -> str:
    return re.sub(r"[^0-9A-Za-z._-]+", "-", version).strip("-") or "nueva"


def backup_data(version: str, keep: int = 3) -> Path:
    root = data_dir() / "backups"
    destination = root / f"pre-{slug_version(version)}"
    destination.mkdir(parents=True, exist_ok=True)
    for name in ("library.json", "settings.json"):
        source = data_dir() / name
        if source.exists():
            shutil.copy2(source, destination / name)
    backups = sorted(
        (item for item in root.iterdir() if item.is_dir()),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    for old in backups[keep:]:
        shutil.rmtree(old, ignore_errors=True)
    return destination


def _ps_quote(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _replacement_script(target: Path, new_exe: Path, pid: int) -> str:
    backup = target.with_name(target.stem + ".old.exe")
    staged = target.with_name(target.name + ".new")
    log = target.with_name("umbral-update.log")
    return f"""$ErrorActionPreference = 'Stop'
$target = {_ps_quote(str(target))}
$new = {_ps_quote(str(new_exe))}
$staged = {_ps_quote(str(staged))}
$backup = {_ps_quote(str(backup))}
$log = {_ps_quote(str(log))}
$pidToWait = {int(pid)}
$utf8Bom = New-Object System.Text.UTF8Encoding($true)
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
function Write-Log($message) {{
    try {{
        $line = "$(Get-Date -Format o) $message`r`n"
        if (-not (Test-Path -LiteralPath $log)) {{
            [System.IO.File]::WriteAllText($log, $line, $utf8Bom)
        }} else {{
            [System.IO.File]::AppendAllText($log, $line, $utf8NoBom)
        }}
    }} catch {{}}
}}
try {{
    Write-Log "Esperando al proceso $pidToWait"
    $waited = 0
    while ($waited -lt 240) {{
        $proc = Get-Process -Id $pidToWait -ErrorAction SilentlyContinue
        if ($null -eq $proc) {{ break }}
        Start-Sleep -Milliseconds 500
        $waited++
    }}
    if ($null -ne (Get-Process -Id $pidToWait -ErrorAction SilentlyContinue)) {{
        throw "Umbral sigue abierto; no se reemplaza el ejecutable."
    }}
    Start-Sleep -Milliseconds 700
    if (Test-Path -LiteralPath $staged) {{ Remove-Item -LiteralPath $staged -Force -ErrorAction SilentlyContinue }}
    Move-Item -LiteralPath $new -Destination $staged -Force
    if (Test-Path -LiteralPath $backup) {{ Remove-Item -LiteralPath $backup -Force -ErrorAction SilentlyContinue }}
    Move-Item -LiteralPath $target -Destination $backup -Force
    Write-Log "Ejecutable anterior movido a $backup"
    Move-Item -LiteralPath $staged -Destination $target -Force
    Write-Log "Nuevo ejecutable instalado"
    $started = Start-Process -FilePath $target -PassThru
    Start-Sleep -Seconds 4
    if ($null -ne $started -and $started.HasExited -and $started.ExitCode -ne 0) {{
        throw "El nuevo ejecutable se cerró al iniciar (código $($started.ExitCode))."
    }}
    Remove-Item -LiteralPath $backup -Force -ErrorAction SilentlyContinue
    Write-Log "Actualización completada"
}} catch {{
    Write-Log "ERROR: $($_.Exception.Message)"
    if (Test-Path -LiteralPath $staged) {{ Remove-Item -LiteralPath $staged -Force -ErrorAction SilentlyContinue }}
    if ((Test-Path -LiteralPath $backup) -and -not (Test-Path -LiteralPath $target)) {{
        Move-Item -LiteralPath $backup -Destination $target -Force -ErrorAction SilentlyContinue
        Write-Log "Restaurado el ejecutable anterior"
    }}
    Start-Process -FilePath $target -ErrorAction SilentlyContinue
}}
"""


def _encoded_command(script: str) -> str:
    return base64.b64encode(script.encode("utf-16-le")).decode("ascii")


def apply_update(new_exe: Path) -> None:
    if not getattr(sys, "frozen", False):
        raise UpdateError("La actualización automática solo funciona desde el ejecutable de Umbral.")
    target = Path(sys.executable).resolve()
    if target.suffix.lower() != ".exe":
        raise UpdateError("No se pudo localizar el ejecutable de Umbral.")
    if not new_exe.is_file():
        raise UpdateError("La actualización descargada ya no está disponible.")
    probe = target.with_name(".umbral-write-test")
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        raise UpdateError(
            "No puedo escribir en la carpeta de Umbral. Mueve Umbral.exe a una carpeta "
            "con permisos, como Descargas, y vuelve a intentarlo."
        ) from exc
    powershell = shutil.which("powershell.exe") or shutil.which("pwsh.exe")
    if not powershell:
        raise UpdateError("Windows no tiene PowerShell disponible para aplicar la actualización.")
    script = _replacement_script(target, new_exe, os.getpid())
    flags = 0
    if os.name == "nt":
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
    try:
        subprocess.Popen(
            [
                powershell,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-WindowStyle",
                "Hidden",
                "-EncodedCommand",
                _encoded_command(script),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
            close_fds=True,
        )
    except OSError as exc:
        raise UpdateError("No se pudo iniciar el proceso de actualización.") from exc


def relative_time(iso_text: str) -> str:
    if not iso_text:
        return ""
    try:
        moment = datetime.fromisoformat(iso_text)
    except ValueError:
        return ""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    seconds = max(0, int((datetime.now(timezone.utc) - moment).total_seconds()))
    if seconds < 90:
        return "hace un momento"
    minutes = seconds // 60
    if minutes < 60:
        return f"hace {minutes} min"
    hours = minutes // 60
    if hours < 24:
        return f"hace {hours} h"
    days = hours // 24
    return f"hace {days} días"
