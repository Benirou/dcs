"""Línea de comandos de la fase 1 (la interfaz gráfica llega en la fase 3).

Uso:
    latam init                 crea la campaña con un escuadrón de F-5 venezolanos
    latam hangar               muestra el estado de cada avión
    latam generate             genera la misión .miz con 2 aviones disponibles
    latam listen               sigue dcs.log en vivo y actualiza el hangar
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

from .bridge.listener import EventApplier, default_dcs_log, follow
from .factions import load_faction, load_theater
from .hangar import Hangar, create_squadron

DEFAULT_THEATER = "caucasus_frontera"
DEFAULT_FACTION = "venezuela_2005"
DEFAULT_UNIT = "planes.F_5E_3"


def saved_games() -> Path:
    home = Path(os.environ.get("USERPROFILE", Path.home()))
    for folder in ("DCS", "DCS.openbeta"):
        if (home / "Saved Games" / folder).exists():
            return home / "Saved Games" / folder
    return home / "Saved Games" / "DCS"


def default_db() -> Path:
    return saved_games() / "LatamCampaign" / "campaign.sqlite"


def _open(db: Path) -> Hangar:
    db.parent.mkdir(parents=True, exist_ok=True)
    return Hangar(db)


def cmd_init(args) -> int:
    if args.db.exists() and not args.force:
        print(f"Ya existe una campaña en {args.db}. Usá --force para empezar de cero.")
        return 1
    if args.db.exists():
        args.db.unlink()
    hangar = _open(args.db)
    faction = load_faction(args.faction)
    theater = load_theater(args.theater)
    base = next(b for b in theater["bases"] if b["owner"] == faction.id)
    tails = create_squadron(hangar, faction.id, faction.flyable(args.unit), base["id"],
                            args.count, args.first_number)
    hangar.log(None, f"Campaña creada: {len(tails)} {faction.flyable(args.unit).display} en {base['name']}",
               datetime.now())
    print(f"Campaña creada en {args.db}")
    print(f"{len(tails)} aviones en {base['name']}: {', '.join(tails)}")
    return 0


def cmd_hangar(args) -> int:
    hangar = _open(args.db)
    now = datetime.now()
    hangar.refresh(now)
    print(f"{'Matrícula':<10} {'Modelo':<24} {'Horas':>6} {'Cond.':>6}  Estado")
    for a in hangar.all():
        status = a.status
        if a.maintenance_until:
            left = max(0, int((a.maintenance_until - now).total_seconds() // 60))
            status += f" ({left} min restantes)"
        print(f"{a.tail:<10} {a.display[:24]:<24} {a.hours:>6.2f} {a.condition:>5.0f}%  {status}")
    print("\nÚltimos eventos:")
    for at, tail, message in hangar.recent_log(args.log):
        print(f"  {at}  {tail or '':<9} {message}")
    return 0


def cmd_generate(args) -> int:
    from .mission.generator import SortieRequest, write_sortie

    hangar = _open(args.db)
    ready = hangar.available(args.unit, now=datetime.now())
    if len(ready) < args.size:
        print(f"Solo hay {len(ready)} aviones disponibles; se necesitan {args.size}.")
        return 1
    chosen = ready[: args.size]
    theater = load_theater(args.theater)
    camp = args.camp or theater["camps"][0]["id"]
    out = args.out or saved_games() / "Missions" / f"LatAm - {camp}.miz"
    write_sortie(SortieRequest(args.theater, args.faction, chosen, target_camp_id=camp,
                               seed=args.seed), out)
    print(f"Misión generada: {out}")
    print(f"Aviones: {', '.join(a.tail for a in chosen)} (vos volás {chosen[0].tail})")
    print("Abrí DCS > Misión > cargá ese archivo. Dejá corriendo `latam listen` mientras volás.")
    return 0


_LABELS = {"takeoff": "despega", "land": "aterriza", "hit": "impacto en", "crash": "se estrella",
           "dead": "destruido", "unit_lost": "perdido", "ejection": "eyección de"}


def _describe(event: dict) -> str:
    def name(key):
        part = event.get(key)
        return part.get("name", "?") if isinstance(part, dict) else "?"

    kind = event.get("kind", "")
    if kind == "hit":
        weapon = f" ({event['weapon']})" if event.get("weapon") else ""
        return f"impacto en {name('target')} desde {name('initiator')}{weapon}"
    return f"{_LABELS.get(kind, kind)} {name('initiator')}"


def cmd_listen(args) -> int:
    hangar = _open(args.db)
    applier = EventApplier(hangar)
    log = args.log_file or default_dcs_log()
    print(f"Escuchando {log} (Ctrl+C para salir)")
    try:
        for event in follow(log, from_start=args.from_start):
            kind = applier.apply(event)
            if kind and kind != "positions":
                print(f"[{datetime.now():%H:%M:%S}] {_describe(event)}", flush=True)
            elif event.get("kind") == "bridge_start":
                print(f"[{datetime.now():%H:%M:%S}] misión iniciada, puente v{event.get('version')}",
                      flush=True)
    except KeyboardInterrupt:
        pass
    print("Listo. Usá `latam hangar` para ver el estado.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="latam", description="Campaña dinámica LatAm para DCS")
    p.add_argument("--db", type=Path, default=default_db(), help="archivo de la campaña")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("init", help="crear campaña nueva")
    s.add_argument("--faction", default=DEFAULT_FACTION)
    s.add_argument("--theater", default=DEFAULT_THEATER)
    s.add_argument("--unit", default=DEFAULT_UNIT)
    s.add_argument("--count", type=int, default=6)
    s.add_argument("--first-number", type=int, default=5101)
    s.add_argument("--force", action="store_true")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("hangar", help="ver aviones")
    s.add_argument("--log", type=int, default=10, help="cantidad de eventos a mostrar")
    s.set_defaults(func=cmd_hangar)

    s = sub.add_parser("generate", help="generar misión .miz")
    s.add_argument("--faction", default=DEFAULT_FACTION)
    s.add_argument("--theater", default=DEFAULT_THEATER)
    s.add_argument("--unit", default=DEFAULT_UNIT)
    s.add_argument("--camp", help="id del campamento objetivo (ver data/theaters)")
    s.add_argument("--size", type=int, default=2)
    s.add_argument("--seed", type=int)
    s.add_argument("--out", type=Path)
    s.set_defaults(func=cmd_generate)

    s = sub.add_parser("listen", help="escuchar eventos de DCS en vivo")
    s.add_argument("--log-file", type=Path)
    s.add_argument("--from-start", action="store_true", help="leer dcs.log desde el principio")
    s.set_defaults(func=cmd_listen)
    return p


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
