from datetime import datetime, timedelta

from latam_campaign.factions import load_faction
from latam_campaign.hangar import (AVAILABLE, FLYING, LOST, MAINTENANCE, Hangar, create_squadron,
                                   maintenance_duration)

T0 = datetime(2026, 11, 5, 12, 0, 0)


def make_hangar():
    hangar = Hangar(":memory:")
    entry = load_faction("venezuela_2005").flyable("planes.F_5E_3")
    create_squadron(hangar, "venezuela_2005", entry, "ba_landaeta", 4, 5101)
    return hangar


def test_one_hour_flight_means_24_minutes_in_the_shop():
    # ratio real del F-5 = 2 h de taller por hora de vuelo; 20 % de eso = 24 min
    assert maintenance_duration(1.0, 2.0, 100) == timedelta(minutes=24)


def test_low_condition_takes_longer():
    assert maintenance_duration(1.0, 2.0, 40) == timedelta(minutes=36)


def test_full_sortie_cycle():
    hangar = make_hangar()
    hangar.on_takeoff("FAV-5101", 100.0, T0)
    assert hangar.get("FAV-5101").status == FLYING
    hangar.on_hit("FAV-5101", T0)
    hangar.on_land("FAV-5101", 100.0 + 3600, T0 + timedelta(hours=1))
    a = hangar.get("FAV-5101")
    assert a.status == MAINTENANCE
    assert round(a.hours, 3) == 1.0
    assert a.condition == 100 - 15 - 3
    assert a.maintenance_until == T0 + timedelta(hours=1, minutes=24)
    # todavía en taller: no aparece disponible
    assert "FAV-5101" not in [x.tail for x in hangar.available(now=T0 + timedelta(hours=1, minutes=10))]
    # terminó el mantenimiento
    assert "FAV-5101" in [x.tail for x in hangar.available(now=T0 + timedelta(hours=1, minutes=25))]
    assert hangar.get("FAV-5101").status == AVAILABLE


def test_lost_aircraft_stays_lost():
    hangar = make_hangar()
    hangar.on_takeoff("FAV-5102", 0, T0)
    hangar.on_lost("FAV-5102", "crash", T0)
    hangar.on_land("FAV-5102", 600, T0)
    assert hangar.get("FAV-5102").status == LOST
    assert len(hangar.available(now=T0)) == 3


def test_unknown_units_are_ignored():
    hangar = make_hangar()
    hangar.on_takeoff("Campamento Unit #1", 0, T0)
    assert len(hangar.all()) == 4
