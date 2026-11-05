"""Prueba el script Lua real con un DCS simulado (lupa) y lo conecta con el hangar."""
from datetime import datetime, timedelta

import pytest

from latam_campaign.bridge import bridge_lua
from latam_campaign.bridge.listener import EventApplier, parse_line, read_new
from latam_campaign.factions import load_faction
from latam_campaign.hangar import LOST, MAINTENANCE, Hangar, create_squadron

lupa = pytest.importorskip("lupa.lua51")  # DCS usa Lua 5.1

FAKE_DCS = r"""
log_lines = {}
clock = 0
env = { info = function(s) log_lines[#log_lines + 1] = s end,
        error = function(s) log_lines[#log_lines + 1] = "ERROR " .. s end, mission = { date = { Year = 2005 } } }
timer = { getTime = function() return clock end, getAbsTime = function() return 28800 + clock end,
          scheduleFunction = function(fn, arg, t) scheduled = fn end }
world = { event = { S_EVENT_TAKEOFF = 3, S_EVENT_LAND = 4, S_EVENT_HIT = 2, S_EVENT_CRASH = 5,
                    S_EVENT_DEAD = 8, S_EVENT_MISSION_END = 12 },
          addEventHandler = function(h) handler = h end }
coalition = { side = { RED = 1, BLUE = 2 } }
Group = { Category = { AIRPLANE = 0, HELICOPTER = 1 } }
coord = { LOtoLL = function(p) return 42.2, 42.0, p.y end }
function makeUnit(name, typeName, side)
  return { getName = function() return name end, getTypeName = function() return typeName end,
           getDesc = function() return { typeName = typeName } end, getCoalition = function() return side end,
           isExist = function() return true end, inAir = function() return true end,
           getPoint = function() return { x = 1, y = 2000, z = 3 } end }
end
local f5 = makeUnit("FAV-5101", "F-5E-3", 2)
coalition.getGroups = function(side, cat)
  if side == 2 and cat == 0 then return { { getUnits = function() return { f5 } end } } end
  return {}
end
"""


def run_lua_session():
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(FAKE_DCS)
    lua.execute(bridge_lua())
    lua.execute(r"""
      local f5 = makeUnit("FAV-5101", "F-5E-3", 2)
      local zu = makeUnit("Campamento \"FARC\" Unit #3", "ZU-23 Insurgent", 1)
      clock = 120;  handler:onEvent({ id = 3, initiator = f5, place = { getName = function() return "Senaki-Kolkhi" end } })
      clock = 900;  handler:onEvent({ id = 2, initiator = zu, target = f5, weapon = { getTypeName = function() return "ZU-23" end } })
      clock = 1000; scheduled()
      clock = 3720; handler:onEvent({ id = 4, initiator = f5 })
      clock = 3800; handler:onEvent({ id = 99, initiator = f5 })  -- evento no vigilado
    """)
    return [str(v) for v in lua.globals().log_lines.values()]


def test_lua_bridge_emits_parseable_json():
    lines = run_lua_session()
    assert not [line for line in lines if line.startswith("ERROR")], lines
    events = [parse_line(line) for line in lines]
    assert all(events), lines
    kinds = [e["kind"] for e in events]
    assert kinds == ["bridge_start", "takeoff", "hit", "positions", "land"]
    hit = events[2]
    assert hit["target"]["name"] == "FAV-5101"
    assert hit["initiator"]["name"] == 'Campamento "FARC" Unit #3'
    assert events[3]["units"][0]["alt"] == 2000


def test_lua_events_drive_the_hangar(tmp_path):
    hangar = Hangar(":memory:")
    entry = load_faction("venezuela_2005").flyable("planes.F_5E_3")
    create_squadron(hangar, "venezuela_2005", entry, "ba_landaeta", 2, 5101)
    now = datetime(2026, 11, 5, 12, 0)
    applier = EventApplier(hangar, clock=lambda: now)

    log = tmp_path / "dcs.log"
    log.write_text("\n".join(f"2026-11-05 12:00:00.000 INFO    SCRIPTING (Main): {line}"
                             for line in run_lua_session()) + "\n", encoding="utf-8")
    events = list(_read_all(log))
    for event in events:
        applier.apply(event)

    a = hangar.get("FAV-5101")
    assert a.status == MAINTENANCE
    assert round(a.hours * 60) == 60          # 3720 s - 120 s = 1 h
    assert a.maintenance_until == now + timedelta(minutes=24)
    assert a.condition == 100 - 15 - 3
    assert "FAV-5101" in applier.positions


def test_crash_marks_aircraft_lost():
    hangar = Hangar(":memory:")
    entry = load_faction("venezuela_2005").flyable("planes.F_5E_3")
    create_squadron(hangar, "venezuela_2005", entry, "ba_landaeta", 1, 5101)
    applier = EventApplier(hangar)
    applier.apply({"kind": "takeoff", "t": 10, "initiator": {"name": "FAV-5101"}})
    applier.apply({"kind": "crash", "t": 50, "initiator": {"name": "FAV-5101"}})
    assert hangar.get("FAV-5101").status == LOST


def test_follow_skips_half_written_lines(tmp_path):
    log = tmp_path / "dcs.log"
    log.write_bytes(b'x LATAM|{"kind":"takeoff"}\nx LATAM|{"kind":"la')
    assert [e["kind"] for e in _read_all(log)] == ["takeoff"]


def _read_all(path):
    events, _ = read_new(path, 0)
    return events
