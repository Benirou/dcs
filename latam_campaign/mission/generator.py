"""Genera un .miz con pydcs a partir del teatro, las facciones y el hangar.

Fase 1: una salida de ataque (2 aviones del hangar) contra un campamento insurgente,
más los demás campamentos del teatro como blancos de oportunidad, y el puente Lua.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import logging

import yaml

logging.getLogger("dcs.installation").setLevel(logging.ERROR)

import dcs  # noqa: E402
from dcs import countries, task  # noqa: E402
from dcs.action import DoScript
from dcs.mapping import Point
from dcs.mission import StartType
from dcs.triggers import TriggerStart

from ..bridge import bridge_lua
from ..factions import DATA_DIR, Faction, load_faction, load_theater, resolve_unit
from ..hangar import Aircraft

KM = 1000.0


@dataclass
class SortieRequest:
    theater_id: str
    blue_faction_id: str
    aircraft: list[Aircraft]          # el primero es el jugador
    target_camp_id: str | None = None  # None = el primero del teatro
    start_type: StartType = StartType.Warm
    seed: int | None = None


def _country(mission: dcs.Mission, faction: Faction):
    """Devuelve el país DCS de la facción dentro de su coalición (lo agrega si falta)."""
    coalition = mission.coalition[faction.side]
    if faction.dcs_country in coalition.countries:
        return coalition.countries[faction.dcs_country]
    # Si el país está en otra coalición por defecto, lo sacamos de ahí.
    for side, other in mission.coalition.items():
        if side != faction.side and faction.dcs_country in other.countries:
            del other.countries[faction.dcs_country]
    country = getattr(countries, faction.dcs_country.replace(" ", ""))()
    coalition.add_country(country)
    return coalition.countries[faction.dcs_country]


def _camp_position(mission: dcs.Mission, camp: dict) -> Point:
    airport = mission.terrain.airports[camp["from_airport"]]
    north_km, east_km = camp["offset_km"]
    return Point(airport.position.x + north_km * KM, airport.position.y + east_km * KM,
                 mission.terrain)


def _add_camp(mission: dcs.Mission, camp: dict, rng: random.Random):
    faction = load_faction(camp["faction"])
    country = _country(mission, faction)
    template = faction.camp_templates[camp.get("template", "campamento")]
    types = []
    for unit_path, count in template:
        types += [resolve_unit(unit_path)] * int(count)
    for ad in faction.air_defense:
        if rng.random() < float(ad.get("rarity", 0)):
            types.append(resolve_unit(ad["unit"]))
    center = _camp_position(mission, camp)
    group = mission.vehicle_group_platoon(country, camp["name"], types, center,
                                          heading=rng.randint(0, 359))
    # Desparramar las unidades en un radio de ~150 m para que parezca un campamento.
    for unit in group.units:
        unit.position = Point(center.x + rng.uniform(-150, 150), center.y + rng.uniform(-150, 150),
                              mission.terrain)
    return group


def _load(flight, entry, main_task) -> None:
    """Carga armamento desde data/loadouts.yaml; si no hay, usa la carga por defecto de DCS."""
    table = yaml.safe_load((DATA_DIR / "loadouts.yaml").read_text(encoding="utf-8")) or {}
    stations = table.get(entry.unit, {}).get(main_task.__name__)
    if not stations:
        flight.load_task_default_loadout(main_task)
        return
    unit_type = entry.dcs_type
    for station, weapon_name in stations.items():
        pylon = getattr(unit_type, f"Pylon{station}")
        weapon = getattr(pylon, weapon_name)
        for unit in flight.units:
            unit.load_pylon(weapon)


def build_sortie(req: SortieRequest) -> dcs.Mission:
    rng = random.Random(req.seed)
    theater = load_theater(req.theater_id)
    terrain = getattr(dcs.terrain, theater["dcs_terrain"])()
    mission = dcs.Mission(terrain)
    start = theater["start_date"]
    mission.start_time = start if isinstance(start, datetime) else datetime.fromisoformat(str(start))

    blue = load_faction(req.blue_faction_id)
    blue_country = _country(mission, blue)

    camps = theater["camps"]
    target = next((c for c in camps if c["id"] == req.target_camp_id), camps[0])
    groups = {c["id"]: _add_camp(mission, c, rng) for c in camps}
    target_group = groups[target["id"]]

    if not req.aircraft:
        raise ValueError("La salida necesita al menos un avión disponible del hangar")
    types = {a.unit for a in req.aircraft}
    if len(types) != 1:
        raise ValueError("Todos los aviones de la salida deben ser del mismo modelo")
    entry = blue.flyable(req.aircraft[0].unit)
    base = next(b for b in theater["bases"] if b["id"] == req.aircraft[0].base)
    airport = terrain.airports[base["airport"]]

    flight = mission.flight_group_from_airport(
        blue_country, f"Ataque {target['name']}", entry.dcs_type, airport,
        maintask=task.GroundAttack, start_type=req.start_type, group_size=len(req.aircraft))
    for unit, aircraft in zip(flight.units, req.aircraft):
        unit.name = aircraft.tail          # la matrícula identifica al avión en los eventos
    flight.units[0].set_player()
    _load(flight, entry, task.GroundAttack)

    camp_pos = _camp_position(mission, target)
    ip = Point(airport.position.x + (camp_pos.x - airport.position.x) * 0.6,
               airport.position.y + (camp_pos.y - airport.position.y) * 0.6, terrain)
    flight.add_waypoint(ip, 3000, 700).name = "IP"
    attack = flight.add_waypoint(camp_pos, 1500, 650)
    attack.name = "Campamento"
    attack.tasks.append(task.AttackGroup(target_group.id))
    flight.land_at(airport)

    trigger = TriggerStart(comment="LatAm bridge")
    trigger.add_action(DoScript(mission.string(bridge_lua())))
    mission.triggerrules.triggers.append(trigger)

    tails = ", ".join(a.tail for a in req.aircraft)
    mission.set_description_text(
        f"Operación contra {target['name']}.\n\n"
        f"Salida de {len(req.aircraft)} {entry.display} desde {base['name']} ({tails}).\n"
        "Inteligencia reporta guerrilleros, una técnica con ZU-23 y posibles MANPADS.\n"
        "Neutralizar el campamento y regresar a la base. Cada minuto de vuelo cuenta para el desgaste.")
    mission.set_description_bluetask_text("Atacar el campamento marcado en el waypoint 'Campamento'.")
    return mission


def write_sortie(req: SortieRequest, out_path: Path) -> Path:
    mission = build_sortie(req)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    mission.save(str(out_path))
    return out_path
