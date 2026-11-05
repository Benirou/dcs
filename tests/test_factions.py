import pytest

from latam_campaign.factions import FactionError, list_factions, load_faction, load_theater, resolve_unit


@pytest.mark.parametrize("faction_id", list_factions())
def test_every_faction_resolves_against_pydcs(faction_id):
    faction = load_faction(faction_id)
    assert faction.unit_paths()


def test_unknown_unit_is_rejected():
    with pytest.raises(FactionError):
        resolve_unit("planes.Kfir_C7")


def test_theater_camps_reference_existing_factions():
    theater = load_theater("caucasus_frontera")
    for camp in theater["camps"]:
        faction = load_faction(camp["faction"])
        assert camp["template"] in faction.camp_templates
