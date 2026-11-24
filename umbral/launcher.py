from __future__ import annotations

import os
import subprocess
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from .job import create_job_for_process, wait_for_job
from .models import Game, slugify
from .paths import logs_dir


class LaunchError(Exception):
    def __init__(self, summary: str, details: str = "") -> None:
        super().__init__(summary)
        self.summary = summary
        self.details = details


def validate(game: Game) -> list[str]:
    issues: list[str] = []
    if not game.executable:
        issues.append("Falta la ruta del ejecutable del emulador o del port.")
    elif not Path(game.executable).is_file():
        issues.append(f"No existe el ejecutable: {game.executable}")
    if game.rom_path and not Path(game.rom_path).exists():
        issues.append(f"No existe el archivo o la carpeta del juego: {game.rom_path}")
    if game.working_dir and not Path(game.working_dir).is_dir():
        issues.append(f"No existe la carpeta de trabajo: {game.working_dir}")
    return issues


def build_command(game: Game) -> list[str]:
    return [game.executable, *game.resolved_arguments()]


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


def launch_game(game: Game) -> tuple[subprocess.Popen, Path]:
    issues = validate(game)
    if issues:
        raise LaunchError("El juego no se puede lanzar todavía.", "\n".join(issues))

    command = build_command(game)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = logs_dir() / f"{stamp}_{slugify(game.title)}.log"

    log_handle = None
    try:
        log_handle = log_path.open("w", encoding="utf-8")
        log_handle.write("Umbral · registro de lanzamiento\n")
        log_handle.write(f"Fecha: {datetime.now().isoformat(timespec='seconds')}\n")
        log_handle.write(f"Juego: {game.title} · {game.subtitle}\n")
        log_handle.write(f"Comando: {subprocess.list2cmdline(command)}\n")
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
            f"Comando: {subprocess.list2cmdline(command)}\nError: {error}",
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

    def __init__(self, process: subprocess.Popen, log_path: Path) -> None:
        super().__init__()
        self._process = process
        self._log_path = str(log_path)

    def run(self) -> None:
        started = time.monotonic()
        job = create_job_for_process(self._process)
        code = self._process.wait()
        wait_for_job(job)
        seconds = max(1, int(time.monotonic() - started))
        self.finished_ok.emit(int(code), seconds, self._log_path)
