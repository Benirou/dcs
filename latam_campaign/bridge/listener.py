"""Lee en vivo los eventos que el puente Lua escribe en dcs.log y los aplica al hangar."""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterator

from ..hangar import Hangar

MARKER = "LATAM|"


def default_dcs_log() -> Path:
    """Ruta habitual de dcs.log en Windows (Saved Games\\DCS o DCS.openbeta)."""
    home = Path(os.environ.get("USERPROFILE", Path.home()))
    for folder in ("DCS", "DCS.openbeta"):
        candidate = home / "Saved Games" / folder / "Logs" / "dcs.log"
        if candidate.exists():
            return candidate
    return home / "Saved Games" / "DCS" / "Logs" / "dcs.log"


def parse_line(line: str) -> dict | None:
    idx = line.find(MARKER)
    if idx < 0:
        return None
    try:
        event = json.loads(line[idx + len(MARKER):].strip())
    except json.JSONDecodeError:
        return None
    return event if isinstance(event, dict) else None


def _name(part) -> str | None:
    return part.get("name") if isinstance(part, dict) else None


@dataclass
class EventApplier:
    """Traduce eventos de DCS a cambios en el hangar. Ignora unidades que no están en él."""
    hangar: Hangar
    clock: Callable[[], datetime] = datetime.now
    positions: dict[str, dict] = field(default_factory=dict)

    def apply(self, event: dict) -> str | None:
        kind = event.get("kind")
        now = self.clock()
        t = float(event.get("t") or 0)
        initiator = _name(event.get("initiator"))
        target = _name(event.get("target"))
        if kind == "takeoff" and initiator:
            self.hangar.on_takeoff(initiator, t, now)
        elif kind == "land" and initiator:
            self.hangar.on_land(initiator, t, now)
        elif kind == "hit" and target:
            self.hangar.on_hit(target, now)
        elif kind in ("crash", "dead", "unit_lost") and initiator:
            self.hangar.on_lost(initiator, kind, now)
        elif kind == "ejection" and initiator:
            self.hangar.on_lost(initiator, "eyección", now)
        elif kind == "positions":
            units = event.get("units") or []
            if isinstance(units, list):
                self.positions = {u["name"]: u for u in units if isinstance(u, dict) and "name" in u}
        else:
            return None
        return kind


def read_new(path: Path, position: int) -> tuple[list[dict], int]:
    """Lee los eventos completos escritos desde `position`. Devuelve (eventos, nueva posición)."""
    if not path.exists():
        return [], position
    size = path.stat().st_size
    if size < position:          # DCS reinició y volvió a crear el log
        position = 0
    if size == position:
        return [], position
    with path.open("rb") as fh:
        fh.seek(position)
        chunk = fh.read()
    # Solo líneas completas; lo que quede a medio escribir se lee en la próxima vuelta.
    complete = chunk[: chunk.rfind(b"\n") + 1]
    events = [e for e in map(parse_line, complete.decode("utf-8", errors="replace").splitlines()) if e]
    return events, position + len(complete)


def follow(path: Path, from_start: bool = False, poll: float = 0.5,
           stop: Callable[[], bool] = lambda: False) -> Iterator[dict]:
    """Sigue el archivo como `tail -f` hasta que `stop()` devuelva True."""
    position = 0 if from_start or not path.exists() else path.stat().st_size
    while not stop():
        events, position = read_new(path, position)
        yield from events
        if not events:
            time.sleep(poll)
