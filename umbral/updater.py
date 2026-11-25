from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shlex
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
from .paths import cache_root, data_dir

REPO = "sanjurjogon-crypto/umbral"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"
WINDOWS_ASSET_NAME = "Umbral.exe"
LINUX_ASSET_NAME = "Umbral-linux-x86_64"
MACOS_ASSET_NAME = "Umbral-macos-arm64.zip"
ASSET_NAME = WINDOWS_ASSET_NAME
USER_AGENT = f"Umbral/{__version__}"


def expected_asset_name(platform_name: Optional[str] = None) -> str:
    target = (sys.platform if platform_name is None else platform_name).lower()
    if target.startswith("win"):
        return WINDOWS_ASSET_NAME
    if target.startswith("darwin"):
        return MACOS_ASSET_NAME
    return LINUX_ASSET_NAME


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


def _pick_asset(assets: list[dict], asset_name: Optional[str] = None) -> Optional[dict]:
    wanted = (asset_name or expected_asset_name()).lower()
    candidates = [item for item in assets if isinstance(item, dict)]
    for item in candidates:
        if str(item.get("name", "")).lower() == wanted:
            return item
    if wanted.endswith(".exe"):
        for item in candidates:
            if str(item.get("name", "")).lower().endswith(".exe"):
                return item
    elif "macos" in wanted or wanted.endswith(".zip"):
        for item in candidates:
            name = str(item.get("name", "")).lower()
            if "macos" in name and name.endswith(".zip"):
                return item
    else:
        for item in candidates:
            name = str(item.get("name", "")).lower()
            if name.endswith(".appimage") or ("linux" in name and not name.endswith(".sha256")):
                return item
    return None


def _info_from_payload(payload: dict, asset_name: Optional[str] = None) -> Optional[UpdateInfo]:
    tag = str(payload.get("tag_name") or payload.get("name") or "").strip()
    version = tag[1:] if tag.lower().startswith("v") else tag
    if not version:
        return None
    assets = payload.get("assets") or []
    if not isinstance(assets, list):
        assets = []
    wanted_name = asset_name or expected_asset_name()
    asset = _pick_asset(assets, wanted_name)
    if asset is None:
        raise UpdateError(f"El release no incluye {wanted_name}.")
    selected_name = str(asset.get("name") or wanted_name)
    size = int(asset.get("size") or 0)
    digest = str(asset.get("digest") or "")
    sha_url = ""
    expected_sha_name = (selected_name + ".sha256").lower()
    for item in assets:
        if str(item.get("name", "")).lower() == expected_sha_name:
            sha_url = str(item.get("browser_download_url", ""))
            break
    return UpdateInfo(
        version=version,
        tag=tag,
        notes=_clean_notes(str(payload.get("body") or "")),
        asset_url=str(asset.get("browser_download_url") or ""),
        asset_name=selected_name,
        size=size,
        digest=digest,
        sha_url=sha_url,
        page_url=str(payload.get("html_url") or RELEASES_PAGE),
        published_at=str(payload.get("published_at") or ""),
    )


def _is_trusted_github_url(url: str) -> bool:
    return url.startswith(
        (
            "https://github.com/",
            "https://objects.githubusercontent.com/",
            "https://release-assets.githubusercontent.com/",
        )
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
    if not _is_trusted_github_url(info.asset_url):
        raise UpdateError("El release apunta a una dirección no válida.")
    if info.sha_url and not _is_trusted_github_url(info.sha_url):
        raise UpdateError("La firma del release apunta a una dirección no válida.")
    if info.page_url and not info.page_url.startswith("https://github.com/"):
        raise UpdateError("La página del release apunta a una dirección no válida.")
    return info


def update_dir() -> Path:
    path = cache_root() / "Umbral" / "update"
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


def format_download_progress(done: int, total: int) -> str:
    done_mb = f"{done / (1024 * 1024):.1f}".replace(".", ",")
    if total > 0:
        percent = min(100, int(done * 100 / total))
        total_mb = f"{total / (1024 * 1024):.1f}".replace(".", ",")
        return f"{percent} % · {done_mb} de {total_mb} MB"
    return f"{done_mb} MB"


def _download_once(
    url: str,
    temporary: Path,
    target: Path,
    expected_size: int,
    progress: Optional[Callable[[int, int], None]],
    cancel_event: Optional[threading.Event],
    is_pe: bool = True,
) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    digest = hashlib.sha256()
    done = 0
    with urlopen(request, timeout=18.0) as response:
        total = int(response.headers.get("Content-Length") or expected_size or 0)
        if progress is not None:
            progress(0, total)
        with temporary.open("wb") as handle:
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    raise UpdateCancelled()
                chunk = response.read(65_536)
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
    if total and done != total:
        raise UpdateError("La descarga quedó incompleta.")
    with temporary.open("rb") as handle:
        header = handle.read(4)
        valid = header[:2] == b"MZ" if is_pe else header == b"\x7fELF"
        if not valid:
            raise UpdateError("El archivo descargado no es un ejecutable válido.")
    os.replace(temporary, target)
    if not is_pe:
        try:
            os.chmod(target, 0o755)
        except OSError:
            pass
    return digest.hexdigest()


def _download_bytes(
    url: str,
    target: Path,
    expected_size: int,
    progress: Optional[Callable[[int, int], None]],
    cancel_event: Optional[threading.Event],
    is_pe: bool = True,
) -> str:
    temporary = target.with_name(target.name + ".part")
    max_attempts = 2
    for attempt in range(1, max_attempts + 1):
        try:
            return _download_once(url, temporary, target, expected_size, progress, cancel_event, is_pe=is_pe)
        except UpdateCancelled:
            temporary.unlink(missing_ok=True)
            raise
        except HTTPError as exc:
            temporary.unlink(missing_ok=True)
            raise UpdateError(f"No se pudo descargar la actualización (error {exc.code}).") from exc
        except UpdateError:
            temporary.unlink(missing_ok=True)
            raise
        except (URLError, TimeoutError, OSError) as exc:
            temporary.unlink(missing_ok=True)
            if attempt >= max_attempts or (cancel_event is not None and cancel_event.is_set()):
                raise UpdateError("No se pudo descargar la actualización. Revisa tu conexión.") from exc
        finally:
            if temporary.exists():
                temporary.unlink(missing_ok=True)
    raise UpdateError("No se pudo descargar la actualización. Revisa tu conexión.")


def download_update(
    info: UpdateInfo,
    progress: Optional[Callable[[int, int], None]] = None,
    cancel_event: Optional[threading.Event] = None,
) -> Path:
    if not _is_trusted_github_url(info.asset_url):
        raise UpdateError("La dirección de descarga no es válida.")
    if info.sha_url and not _is_trusted_github_url(info.sha_url):
        raise UpdateError("La dirección de la firma no es válida.")
    is_pe = info.asset_name.lower().endswith(".exe")
    suffix = ".exe" if is_pe else "-linux"
    target = update_dir() / f"Umbral-{slug_version(info.version)}{suffix}"
    for old in update_dir().glob(f"Umbral-*{suffix}"):
        if old != target:
            old.unlink(missing_ok=True)
    digest = _download_bytes(
        info.asset_url, target, info.size, progress, cancel_event, is_pe=is_pe
    )
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
$targetDir = [System.IO.Path]::GetDirectoryName($target)
$new = {_ps_quote(str(new_exe))}
$staged = {_ps_quote(str(staged))}
$backup = {_ps_quote(str(backup))}
$log = {_ps_quote(str(log))}
$pidToWait = {int(pid)}
$exeName = [System.IO.Path]::GetFileNameWithoutExtension($target)
$hasWildcardName = $exeName -match '[\\*\\?\\[\\]]'
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
function Target-Processes-Running {{
    if ($pidToWait -gt 0 -and $null -ne (Get-Process -Id $pidToWait -ErrorAction SilentlyContinue)) {{
        return $true
    }}
    try {{
        $normTarget = [System.IO.Path]::GetFullPath($target)
        $candidates = if ($hasWildcardName) {{
            Get-Process -ErrorAction SilentlyContinue
        }} else {{
            Get-Process -Name $exeName -ErrorAction SilentlyContinue
        }}
        $matches = $candidates | Where-Object {{
            try {{ $_.Path -and ([System.IO.Path]::GetFullPath($_.Path) -ieq $normTarget) }} catch {{ $false }}
        }}
        if ($null -ne $matches) {{ return $true }}
    }} catch {{}}
    return $false
}}
function Move-WithRetry($src, $dst) {{
    $lastError = $null
    for ($attempt = 1; $attempt -le 40; $attempt++) {{
        try {{
            Move-Item -LiteralPath $src -Destination $dst -Force
            return
        }} catch {{
            $lastError = $_
            if ($attempt -ge 4) {{
                try {{
                    Copy-Item -LiteralPath $src -Destination $dst -Force
                    Remove-Item -LiteralPath $src -Force -ErrorAction SilentlyContinue
                    return
                }} catch {{
                    $lastError = $_
                }}
            }}
            Start-Sleep -Milliseconds 250
        }}
    }}
    throw $lastError
}}
function Copy-WithRetry($src, $dst) {{
    $lastError = $null
    for ($attempt = 1; $attempt -le 40; $attempt++) {{
        try {{
            Copy-Item -LiteralPath $src -Destination $dst -Force
            return
        }} catch {{
            $lastError = $_
            Start-Sleep -Milliseconds 250
        }}
    }}
    throw $lastError
}}
function Start-TargetAndVerify {{
    for ($launchTry = 1; $launchTry -le 2; $launchTry++) {{
        $started = Start-Process -FilePath $target -WorkingDirectory $targetDir -ArgumentList '--relaunch' -PassThru
        Start-Sleep -Milliseconds 1500
        $pidToWait = 0
        if ($null -ne $started -and -not $started.HasExited) {{
            return $true
        }}
        if (Target-Processes-Running) {{
            return $true
        }}
        $code = if ($null -ne $started) {{ $started.ExitCode }} else {{ -1 }}
        Write-Log "Reintento de arranque $launchTry (código $code)"
        if ($launchTry -eq 1) {{
            Start-Sleep -Milliseconds 600
        }} else {{
            throw "El nuevo ejecutable no permaneció abierto tras actualizar (código $code)."
        }}
    }}
    return $false
}}
try {{
    Write-Log "Esperando al proceso $pidToWait"
    $waited = 0
    while ($waited -lt 600) {{
        if (-not (Target-Processes-Running)) {{ break }}
        Start-Sleep -Milliseconds 100
        $waited++
    }}
    if (Target-Processes-Running) {{
        throw "Umbral sigue abierto; no se reemplaza el ejecutable."
    }}
    Start-Sleep -Milliseconds 250
    Unblock-File -LiteralPath $new -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $staged) {{ Remove-Item -LiteralPath $staged -Force -ErrorAction SilentlyContinue }}
    Copy-WithRetry $new $staged
    Unblock-File -LiteralPath $staged -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $backup) {{ Remove-Item -LiteralPath $backup -Force -ErrorAction SilentlyContinue }}
    Move-WithRetry $target $backup
    Write-Log "Ejecutable anterior movido a $backup"
    Move-WithRetry $staged $target
    Unblock-File -LiteralPath $target -ErrorAction SilentlyContinue
    Write-Log "Nuevo ejecutable instalado"
    $null = Start-TargetAndVerify
    Remove-Item -LiteralPath $new -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $backup -Force -ErrorAction SilentlyContinue
    Write-Log "Actualización completada"
}} catch {{
    Write-Log "ERROR: $($_.Exception.Message)"
    if (Test-Path -LiteralPath $staged) {{ Remove-Item -LiteralPath $staged -Force -ErrorAction SilentlyContinue }}
    if ((Test-Path -LiteralPath $backup) -and -not (Test-Path -LiteralPath $target)) {{
        Move-Item -LiteralPath $backup -Destination $target -Force -ErrorAction SilentlyContinue
        Write-Log "Restaurado el ejecutable anterior"
    }}
    if (-not (Target-Processes-Running)) {{
        Start-Process -FilePath $target -WorkingDirectory $targetDir -ArgumentList '--relaunch' -ErrorAction SilentlyContinue
    }}
}}
"""


def _encoded_command(script: str) -> str:
    return base64.b64encode(script.encode("utf-16-le")).decode("ascii")


def _clean_subprocess_env(base: Optional[dict[str, str]] = None) -> dict[str, str]:
    """Strip PyInstaller bootloader env vars so the relaunched executable starts cleanly."""
    source = os.environ if base is None else base
    cleaned: dict[str, str] = {}
    for key, value in source.items():
        upper = key.upper()
        if upper in {"_MEIPASS", "_MEIPASS2", "TCL_LIBRARY", "TK_LIBRARY"}:
            continue
        if upper.startswith("_PYI_"):
            continue
        cleaned[key] = value
    return cleaned


def _posix_replacement_script(target: Path, new_bin: Path, pid: int) -> str:
    backup = target.with_name(target.name + ".old")
    staged = target.with_name(target.name + ".new")
    log = target.with_name("umbral-update.log")
    return f"""#!/bin/sh
set -eu
TARGET={shlex.quote(str(target))}
NEW={shlex.quote(str(new_bin))}
STAGED={shlex.quote(str(staged))}
BACKUP={shlex.quote(str(backup))}
LOG={shlex.quote(str(log))}
PID={int(pid)}
log_msg() {{
  printf '%s %s\\n' "$(date -Iseconds 2>/dev/null || date)" "$1" >> "$LOG" 2>/dev/null || true
}}
log_msg "Esperando al proceso $PID"
waited=0
while [ "$waited" -lt 300 ]; do
  if ! kill -0 "$PID" 2>/dev/null; then
    break
  fi
  sleep 0.1
  waited=$((waited + 1))
done
cp -f "$NEW" "$STAGED"
chmod 755 "$STAGED"
cp -f "$TARGET" "$BACKUP" 2>/dev/null || true
mv -f "$STAGED" "$TARGET"
chmod 755 "$TARGET"
log_msg "Nuevo ejecutable instalado"
"$TARGET" --relaunch >/dev/null 2>&1 &
sleep 1
rm -f "$NEW" "$BACKUP" 2>/dev/null || true
log_msg "Actualización completada"
"""


def _macos_app_replacement_script(app_bundle: Path, new_zip: Path, pid: int) -> str:
    log_path = data_dir() / "update.log"
    tmp_dir = app_bundle.with_name(f".{app_bundle.name}.tmp")
    backup = app_bundle.with_name(f"{app_bundle.name}.bak")
    return f"""#!/bin/sh
set -eu
APP={shlex.quote(str(app_bundle))}
NEW={shlex.quote(str(new_zip))}
TMP={shlex.quote(str(tmp_dir))}
BACKUP={shlex.quote(str(backup))}
LOG={shlex.quote(str(log_path))}
PID={int(pid)}
log_msg() {{
  printf '%s %s\\n' "$(date -Iseconds 2>/dev/null || date)" "$1" >> "$LOG" 2>/dev/null || true
}}
log_msg "Esperando al proceso $PID"
waited=0
while [ "$waited" -lt 300 ]; do
  if ! kill -0 "$PID" 2>/dev/null; then
    break
  fi
  sleep 0.1
  waited=$((waited + 1))
done
rm -rf "$TMP" "$BACKUP"
mkdir -p "$TMP"
ditto -x -k "$NEW" "$TMP"
NEW_APP="$TMP/Umbral.app"
if [ ! -d "$NEW_APP" ]; then
  log_msg "No se encontró Umbral.app dentro del zip"
  exit 1
fi
mv "$APP" "$BACKUP"
mv "$NEW_APP" "$APP"
rm -rf "$TMP" "$BACKUP" "$NEW" 2>/dev/null || true
log_msg "Nueva app macOS instalada"
open -n "$APP" --args --relaunch >/dev/null 2>&1 || true
"""


def apply_update(new_exe: Path) -> None:
    if not getattr(sys, "frozen", False):
        raise UpdateError("La actualización automática solo funciona desde el ejecutable de Umbral.")
    target = Path(sys.executable).resolve()
    if os.name == "nt" and target.suffix.lower() != ".exe":
        raise UpdateError("No se pudo localizar el ejecutable de Umbral.")
    if not new_exe.is_file():
        raise UpdateError("La actualización descargada ya no está disponible.")
    probe = target.with_name(".umbral-write-test")
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        folder_hint = "Descargas" if os.name == "nt" else ("Aplicaciones" if sys.platform == "darwin" else "~/.local/bin o Descargas")
        raise UpdateError(
            f"No puedo escribir en la carpeta de Umbral. Mueve {target.name} a una carpeta "
            f"con permisos, como {folder_hint}, y vuelve a intentarlo."
        ) from exc

    if os.name != "nt":
        shell = shutil.which("sh") or "/bin/sh"
        app_bundle = next((p for p in target.parents if p.suffix.lower() == ".app"), None)
        if sys.platform == "darwin" and app_bundle is not None and new_exe.suffix.lower() == ".zip":
            script = _macos_app_replacement_script(app_bundle, new_exe, os.getpid())
        else:
            script = _posix_replacement_script(target, new_exe, os.getpid())
        try:
            subprocess.Popen(
                [shell, "-c", script],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=_clean_subprocess_env(),
                start_new_session=True,
                close_fds=True,
            )
        except OSError as exc:
            raise UpdateError("No se pudo iniciar el proceso de actualización.") from exc
        return

    powershell = shutil.which("powershell.exe") or shutil.which("pwsh.exe")
    if not powershell:
        sys_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        candidate = sys_root / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
        if candidate.is_file():
            powershell = str(candidate)
    if not powershell:
        raise UpdateError("Windows no tiene PowerShell disponible para aplicar la actualización.")
    script = _replacement_script(target, new_exe, os.getpid())
    # CREATE_NO_WINDOW (not DETACHED_PROCESS): powershell.exe silently aborts when
    # spawned with DETACHED_PROCESS + DEVNULL handles from a GUI (--noconsole) app.
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
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
            env=_clean_subprocess_env(),
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
