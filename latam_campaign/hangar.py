"""Registro de aeronaves: cada avión/helicóptero tiene matrícula, horas, condición y estado.

Reglas de desgaste (fase 1, simples y ajustables):
- Tiempo en taller = horas voladas x ratio real del modelo x MAINTENANCE_FACTOR (20 %).
- La condición baja WEAR_PER_HOUR puntos por hora de vuelo y HIT_DAMAGE por impacto recibido.
- Con condición < LOW_CONDITION el tiempo en taller se multiplica por LOW_CONDITION_PENALTY.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

MAINTENANCE_FACTOR = 0.2
WEAR_PER_HOUR = 3.0
HIT_DAMAGE = 15.0
LOW_CONDITION = 50.0
LOW_CONDITION_PENALTY = 1.5

AVAILABLE = "disponible"
FLYING = "en vuelo"
MAINTENANCE = "mantenimiento"
LOST = "perdido"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS aircraft (
    tail TEXT PRIMARY KEY,
    unit TEXT NOT NULL,
    display TEXT NOT NULL,
    faction TEXT NOT NULL,
    base TEXT NOT NULL,
    real_downtime_ratio REAL NOT NULL,
    hours REAL NOT NULL DEFAULT 0,
    condition REAL NOT NULL DEFAULT 100,
    status TEXT NOT NULL DEFAULT 'disponible',
    maintenance_until TEXT,
    takeoff_mission_time REAL,
    hits_this_sortie INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    tail TEXT,
    message TEXT NOT NULL
);
"""


@dataclass
class Aircraft:
    tail: str
    unit: str
    display: str
    faction: str
    base: str
    real_downtime_ratio: float
    hours: float = 0.0
    condition: float = 100.0
    status: str = AVAILABLE
    maintenance_until: datetime | None = None
    takeoff_mission_time: float | None = None
    hits_this_sortie: int = 0


def maintenance_duration(flight_hours: float, real_ratio: float, condition: float,
                         factor: float = MAINTENANCE_FACTOR) -> timedelta:
    hours = flight_hours * real_ratio * factor
    if condition < LOW_CONDITION:
        hours *= LOW_CONDITION_PENALTY
    return timedelta(hours=hours)


class Hangar:
    def __init__(self, db_path: Path | str):
        self.db = sqlite3.connect(str(db_path))
        self.db.row_factory = sqlite3.Row
        self.db.executescript(_SCHEMA)

    # --- lectura / escritura -------------------------------------------------
    @staticmethod
    def _row_to_aircraft(row: sqlite3.Row) -> Aircraft:
        data = dict(row)
        if data["maintenance_until"]:
            data["maintenance_until"] = datetime.fromisoformat(data["maintenance_until"])
        return Aircraft(**data)

    def add(self, aircraft: Aircraft) -> None:
        self.db.execute(
            "INSERT INTO aircraft (tail, unit, display, faction, base, real_downtime_ratio) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (aircraft.tail, aircraft.unit, aircraft.display, aircraft.faction,
             aircraft.base, aircraft.real_downtime_ratio),
        )
        self.db.commit()

    def save(self, a: Aircraft) -> None:
        self.db.execute(
            "UPDATE aircraft SET hours=?, condition=?, status=?, maintenance_until=?, "
            "takeoff_mission_time=?, hits_this_sortie=? WHERE tail=?",
            (a.hours, a.condition, a.status,
             a.maintenance_until.isoformat() if a.maintenance_until else None,
             a.takeoff_mission_time, a.hits_this_sortie, a.tail),
        )
        self.db.commit()

    def get(self, tail: str) -> Aircraft | None:
        row = self.db.execute("SELECT * FROM aircraft WHERE tail=?", (tail,)).fetchone()
        return self._row_to_aircraft(row) if row else None

    def all(self) -> list[Aircraft]:
        rows = self.db.execute("SELECT * FROM aircraft ORDER BY tail").fetchall()
        return [self._row_to_aircraft(r) for r in rows]

    def log(self, tail: str | None, message: str, now: datetime) -> None:
        self.db.execute("INSERT INTO log (at, tail, message) VALUES (?, ?, ?)",
                        (now.isoformat(timespec="seconds"), tail, message))
        self.db.commit()

    def recent_log(self, limit: int = 20) -> list[tuple[str, str | None, str]]:
        rows = self.db.execute("SELECT at, tail, message FROM log ORDER BY id DESC LIMIT ?",
                               (limit,)).fetchall()
        return [(r["at"], r["tail"], r["message"]) for r in rows]

    # --- reglas ---------------------------------------------------------------
    def refresh(self, now: datetime) -> None:
        """Libera los aviones cuyo mantenimiento terminó."""
        for a in self.all():
            if a.status == MAINTENANCE and a.maintenance_until and a.maintenance_until <= now:
                a.status, a.maintenance_until = AVAILABLE, None
                self.save(a)
                self.log(a.tail, "sale de mantenimiento", now)

    def available(self, unit: str | None = None, now: datetime | None = None) -> list[Aircraft]:
        if now:
            self.refresh(now)
        return [a for a in self.all()
                if a.status == AVAILABLE and (unit is None or a.unit == unit)]

    def on_takeoff(self, tail: str, mission_time: float, now: datetime) -> None:
        a = self.get(tail)
        if not a or a.status == LOST:
            return
        a.status, a.takeoff_mission_time, a.hits_this_sortie = FLYING, mission_time, 0
        self.save(a)
        self.log(tail, "despega", now)

    def on_hit(self, tail: str, now: datetime) -> None:
        a = self.get(tail)
        if not a or a.status == LOST:
            return
        a.hits_this_sortie += 1
        a.condition = max(0.0, a.condition - HIT_DAMAGE)
        self.save(a)
        self.log(tail, f"recibe impacto (condición {a.condition:.0f} %)", now)

    def on_land(self, tail: str, mission_time: float, now: datetime) -> None:
        a = self.get(tail)
        if not a or a.status != FLYING:
            return
        flight_s = max(0.0, mission_time - (a.takeoff_mission_time or mission_time))
        flight_h = flight_s / 3600
        a.hours += flight_h
        a.condition = max(0.0, a.condition - WEAR_PER_HOUR * flight_h)
        downtime = maintenance_duration(flight_h, a.real_downtime_ratio, a.condition)
        a.status = MAINTENANCE if downtime.total_seconds() > 0 else AVAILABLE
        a.maintenance_until = now + downtime if a.status == MAINTENANCE else None
        a.takeoff_mission_time = None
        self.save(a)
        minutes = downtime.total_seconds() / 60
        self.log(tail, f"aterriza tras {flight_h * 60:.0f} min; taller {minutes:.0f} min", now)

    def on_lost(self, tail: str, reason: str, now: datetime) -> None:
        a = self.get(tail)
        if not a or a.status == LOST:
            return
        a.status, a.condition, a.maintenance_until, a.takeoff_mission_time = LOST, 0.0, None, None
        self.save(a)
        self.log(tail, f"perdido ({reason})", now)


def create_squadron(hangar: Hangar, faction_id: str, entry, base: str, count: int,
                    first_number: int) -> list[str]:
    """Crea `count` aeronaves de un modelo con matrículas consecutivas."""
    tails = []
    for n in range(first_number, first_number + count):
        tail = f"{entry.tail_prefix}-{n}" if entry.tail_prefix else str(n)
        hangar.add(Aircraft(tail=tail, unit=entry.unit, display=entry.display,
                            faction=faction_id, base=base,
                            real_downtime_ratio=entry.real_downtime_ratio))
        tails.append(tail)
    return tails
