import dcs

from latam_campaign.factions import load_faction
from latam_campaign.hangar import Hangar, create_squadron
from latam_campaign.mission.generator import SortieRequest, write_sortie


def test_generated_mission_reloads_with_tails_targets_and_bridge(tmp_path):
    hangar = Hangar(":memory:")
    entry = load_faction("venezuela_2005").flyable("planes.F_5E_3")
    create_squadron(hangar, "venezuela_2005", entry, "ba_landaeta", 6, 5101)
    out = write_sortie(SortieRequest("caucasus_frontera", "venezuela_2005",
                                     hangar.available()[:2], target_camp_id="eln_dl", seed=3),
                       tmp_path / "test.miz")

    mission = dcs.Mission()
    mission.load_file(str(out))
    assert mission.terrain.name == "Caucasus"

    venezuela = mission.coalition["blue"].countries["Venezuela"]
    flight = venezuela.plane_group[0]
    assert [u.name for u in flight.units] == ["FAV-5101", "FAV-5102"]
    assert flight.units[0].skill == dcs.unit.Skill.Player
    assert flight.units[0].pylons, "el avión debería salir armado"
    assert any(t.Id == "AttackGroup" for p in flight.points for t in p.tasks)

    insurgents = mission.coalition["red"].countries["Insurgents"]
    assert len(insurgents.vehicle_group) == 3

    scripts = [a for t in mission.triggerrules.triggers for a in t.actions]
    assert scripts, "falta el trigger del puente Lua"
