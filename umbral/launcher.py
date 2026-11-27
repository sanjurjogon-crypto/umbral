from __future__ import annotations

import os
import re
import shlex
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QThread, Signal

from .job import create_job_for_process, wait_for_job
from .models import Game, slugify
from .paths import logs_dir

MAX_LOG_FILES = 50


class LaunchError(Exception):
    def __init__(self, summary: str, details: str = "") -> None:
        super().__init__(summary)
        self.summary = summary
        self.details = details


def _is_macos_app_bundle(path: Path) -> bool:
    return path.suffix.lower() == ".app" and path.is_dir()


def validate(game: Game) -> list[str]:
    issues: list[str] = []
    if not game.executable:
        issues.append("Falta la ruta del ejecutable del emulador o del port.")
    else:
        exe_path = Path(game.executable)
        if not exe_path.is_file() and not _is_macos_app_bundle(exe_path):
            issues.append(f"No existe el ejecutable: {game.executable}")
    if game.rom_path and not Path(game.rom_path).exists():
        issues.append(f"No existe el archivo o la carpeta del juego: {game.rom_path}")
    if game.working_dir and not Path(game.working_dir).is_dir():
        issues.append(f"No existe la carpeta de trabajo: {game.working_dir}")
    return issues


def build_command(game: Game) -> list[str]:
    args = game.resolved_arguments()
    exe_path = Path(game.executable)
    if _is_macos_app_bundle(exe_path):
        cmd = ["open", "-W", "-a", str(exe_path)]
        if args:
            cmd.extend(["--args", *args])
        return cmd
    return [game.executable, *args]


def diagnostic_text(game: Game, log_path: Path | None = None) -> str:
    lines = [
        f"Juego: {game.title}",
        f"Subtítulo: {game.subtitle}",
        f"Sistema: {game.system}",
        f"Emulador o port: {game.emulator}",
        "",
        f"Ejecutable: {game.executable}",
        f"Carpeta de trabajo: {game.working_dir}",
        f"Archivo o carpeta: {game.rom_path or '(no usa archivo)'}",
        f"Comando: {game.command_preview}",
    ]
    if log_path:
        lines += ["", f"Registro: {log_path}"]
    return "\n".join(lines)


def _prune_logs(keep: int = MAX_LOG_FILES) -> None:
    try:
        files = sorted(
            (item for item in logs_dir().glob("*.log") if item.is_file()),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        for old in files[keep:]:
            old.unlink(missing_ok=True)
    except OSError:
        pass


def launch_game(game: Game) -> tuple[subprocess.Popen, Path]:
    issues = validate(game)
    if issues:
        raise LaunchError("El juego no se puede lanzar todavía.", "\n".join(issues))

    command = build_command(game)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = logs_dir() / f"{stamp}_{slugify(game.title)}.log"
    _prune_logs()

    cmd_text = (
        subprocess.list2cmdline(command)
        if os.name == "nt"
        else shlex.join(command)
    )

    log_handle = None
    try:
        log_handle = log_path.open("w", encoding="utf-8")
        log_handle.write("Umbral · registro de lanzamiento\n")
        log_handle.write(f"Fecha: {datetime.now().isoformat(timespec='seconds')}\n")
        log_handle.write(f"Juego: {game.title} · {game.subtitle}\n")
        log_handle.write(f"Comando: {cmd_text}\n")
        log_handle.write(f"Carpeta: {game.working_dir}\n")
        log_handle.write("-" * 60 + "\n")
        log_handle.flush()
    except OSError:
        log_handle = None

    try:
        process = subprocess.Popen(
            command,
            cwd=game.working_dir or None,
            stdin=subprocess.DEVNULL,
            stdout=log_handle or subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
    except OSError as error:
        if log_handle:
            try:
                log_handle.write(f"\nERROR: {error}\n")
                log_handle.close()
            except OSError:
                pass
        raise LaunchError(
            "No se pudo iniciar el proceso.",
            f"Comando: {cmd_text}\nError: {error}",
        ) from error
    finally:
        if log_handle:
            try:
                log_handle.close()
            except OSError:
                pass

    return process, log_path


class ProcessWatcher(QThread):
    finished_ok = Signal(int, int, str)

    def __init__(self, process: subprocess.Popen, log_path: Path, game_id: str = "") -> None:
        super().__init__()
        self._process = process
        self._log_path = str(log_path)
        self.game_id = game_id
        self.started_at = time.monotonic()
        self._job = create_job_for_process(self._process)
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def elapsed_seconds(self) -> int:
        return max(1, int(time.monotonic() - self.started_at))

    def run(self) -> None:
        while not self._stop.is_set():
            code = self._process.poll()
            if code is not None:
                wait_for_job(self._job)
                if not self._stop.is_set():
                    self.finished_ok.emit(int(code), self.elapsed_seconds(), self._log_path)
                return
            self._stop.wait(0.2)


def steam_app_id(game: Game) -> str:
    args = list(game.arguments or [])
    for index, arg in enumerate(args):
        if arg == "-applaunch" and index + 1 < len(args):
            candidate = str(args[index + 1]).strip()
            if candidate.isdigit():
                return candidate
    match = re.search(r"AppID de Steam:\s*(\d+)", game.notes or "")
    return match.group(1) if match else ""


def _linux_steam_app_running(app_id: str) -> bool:
    proc_root = Path("/proc")
    if not proc_root.is_dir():
        return False
    marker = f"AppId={app_id}"
    try:
        entries = list(proc_root.iterdir())
    except OSError:
        return False
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            raw = (entry / "cmdline").read_bytes()
        except OSError:
            continue
        if not raw:
            continue
        text = raw.replace(b"\x00", b" ").decode("utf-8", "ignore")
        if marker in text:
            return True
    return False


def _steam_app_state(app_id: str) -> tuple[bool, bool]:
    if not app_id:
        return False, False
    if os.name != "nt":
        return _linux_steam_app_running(app_id), False
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, rf"Software\Valve\Steam\Apps\{app_id}"
        ) as handle:
            running = False
            updating = False
            try:
                value, _ = winreg.QueryValueEx(handle, "Running")
                running = bool(int(value))
            except (OSError, ValueError, TypeError):
                pass
            try:
                value, _ = winreg.QueryValueEx(handle, "Updating")
                updating = bool(int(value))
            except (OSError, ValueError, TypeError):
                pass
            return running, updating
    except OSError:
        return False, False


class SteamWatcher(QThread):
    finished_ok = Signal(int, int, str)

    def __init__(
        self,
        app_id: str,
        log_path: Path,
        game_id: str = "",
        launch_timeout: float = 120.0,
        poll_interval: float = 1.0,
    ) -> None:
        super().__init__()
        self.app_id = str(app_id)
        self._log_path = str(log_path)
        self.game_id = game_id
        self._launch_timeout = launch_timeout
        self._poll_interval = poll_interval
        self._started_at: Optional[float] = None
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def elapsed_seconds(self) -> int:
        if self._started_at is None:
            return 0
        return max(1, int(time.monotonic() - self._started_at))

    def run(self) -> None:
        deadline = time.monotonic() + self._launch_timeout
        while not self._stop_event.is_set():
            running, updating = _steam_app_state(self.app_id)
            if running:
                self._started_at = time.monotonic()
                break
            if updating:
                deadline = max(deadline, time.monotonic() + 30.0)
            if time.monotonic() >= deadline:
                return
            self._stop_event.wait(min(0.5, self._poll_interval))

        if self._stop_event.is_set() or self._started_at is None:
            return

        while not self._stop_event.is_set():
            running, _updating = _steam_app_state(self.app_id)
            if not running:
                self.finished_ok.emit(0, self.elapsed_seconds(), self._log_path)
                return
            self._stop_event.wait(self._poll_interval)
