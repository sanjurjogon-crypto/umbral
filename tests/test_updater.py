from __future__ import annotations

from pathlib import Path

from umbral.updater import _replacement_script


def test_replacement_script_waits_and_logs(tmp_path: Path) -> None:
    target = tmp_path / "Umbral.exe"
    new = tmp_path / "Umbral-8.20.0.exe"
    script = _replacement_script(target, new, 4321)
    assert "$pidToWait = 4321" in script
    assert "umbral-update.log" in script
    assert "sigue abierto" in script
    assert "Restaurado el ejecutable anterior" in script
