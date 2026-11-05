"""Carga y validación de facciones y teatros (archivos YAML en data/)."""
from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DATA_DIR = Path(__file__).parent / "data"

# Prefijo en el YAML -> módulo de pydcs
_UNIT_ROOTS = {
    "planes": "dcs.planes",
    "helicopters": "dcs.helicopters",
    "vehicles": "dcs.vehicles",
    "ships": "dcs.ships",
}


class FactionError(ValueError):
    pass


def resolve_unit(path: str) -> Any:
    """Convierte 'planes.F_5E_3' o 'vehicles.Infantry.Soldier_RPG' en la clase de pydcs."""
    root, _, rest = path.partition(".")
    if root not in _UNIT_ROOTS or not rest:
        raise FactionError(f"Unidad con prefijo desconocido: {path!r}")
    obj: Any = importlib.import_module(_UNIT_ROOTS[root])
    for part in rest.split("."):
        if not hasattr(obj, part):
            raise FactionError(f"La unidad {path!r} no existe en pydcs (falta {part!r})")
        obj = getattr(obj, part)
    return obj


@dataclass
class AircraftEntry:
    unit: str
    display: str
    role: list[str]
    real_downtime_ratio: float = 2.0
    tail_prefix: str = ""

    @property
    def dcs_type(self) -> Any:
        return resolve_unit(self.unit)


@dataclass
class Faction:
    id: str
    name: str
    side: str
    dcs_country: str
    insurgent: bool = False
    aircraft: list[AircraftEntry] = field(default_factory=list)
    helicopters: list[AircraftEntry] = field(default_factory=list)
    ground: list[dict] = field(default_factory=list)
    air_defense: list[dict] = field(default_factory=list)
    camp_templates: dict[str, list[list]] = field(default_factory=dict)
    raw: dict = field(default_factory=dict, repr=False)

    def all_flyables(self) -> list[AircraftEntry]:
        return self.aircraft + self.helicopters

    def flyable(self, unit: str) -> AircraftEntry:
        for entry in self.all_flyables():
            if entry.unit == unit:
                return entry
        raise FactionError(f"{self.name} no tiene la aeronave {unit!r}")

    def unit_paths(self) -> list[str]:
        paths = [a.unit for a in self.all_flyables()]
        paths += [g["unit"] for g in self.ground + self.air_defense]
        for template in self.camp_templates.values():
            paths += [row[0] for row in template]
        return paths

    def validate(self) -> None:
        if self.side not in ("blue", "red"):
            raise FactionError(f"{self.id}: side debe ser blue o red")
        import dcs.countries as countries

        if not hasattr(countries, self.dcs_country.replace(" ", "")):
            raise FactionError(f"{self.id}: país DCS desconocido {self.dcs_country!r}")
        for path in self.unit_paths():
            resolve_unit(path)


def _flyables(items: list[dict] | None) -> list[AircraftEntry]:
    return [AircraftEntry(**item) for item in (items or [])]


def load_faction(faction_id: str, data_dir: Path = DATA_DIR) -> Faction:
    path = data_dir / "factions" / f"{faction_id}.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    faction = Faction(
        id=raw["id"],
        name=raw["name"],
        side=raw["side"],
        dcs_country=raw["dcs_country"],
        insurgent=raw.get("insurgent", False),
        aircraft=_flyables(raw.get("aircraft")),
        helicopters=_flyables(raw.get("helicopters")),
        ground=raw.get("ground", []),
        air_defense=raw.get("air_defense", []),
        camp_templates=raw.get("camp_templates", {}),
        raw=raw,
    )
    faction.validate()
    return faction


def list_factions(data_dir: Path = DATA_DIR) -> list[str]:
    return sorted(p.stem for p in (data_dir / "factions").glob("*.yaml"))


def load_theater(theater_id: str, data_dir: Path = DATA_DIR) -> dict:
    path = data_dir / "theaters" / f"{theater_id}.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))
