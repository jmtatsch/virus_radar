"""Tests for the province mapping and location handling in location_manager."""

import pandas as pd
import pytest
import reverse_geocoder as rg

from location_manager import (
    canonical_province_key,
    find_province_index,
    province2region,
    province_short2english,
    province_short2german,
    province_to_short,
)

VALID_REGIONS = ["Mitte (West)", "Norden (West)", "Osten", "Sueden"]

# how our sources spell a Bundesland, and the short code it has to resolve to
PROVINCE_SPELLINGS = [
    ("Bayern", "BY"),
    ("Bavaria", "BY"),  # reverse_geocoder and ipinfo
    ("Baden-Württemberg", "BW"),
    ("Baden-Wuerttemberg", "BW"),  # reverse_geocoder and the RKI data sets
    ("Baden-Wurttemberg", "BW"),
    ("Thüringen", "TH"),
    ("Thueringen", "TH"),  # the RKI data sets
    ("Thuringia", "TH"),  # reverse_geocoder
    ("Hesse", "HE"),
    ("Hessen", "HE"),
    ("Lower Saxony", "NI"),
    ("Niedersachsen", "NI"),
    ("North Rhine-Westphalia", "NW"),
    ("Mecklenburg-Western Pomerania", "MV"),
    ("Mecklenburg-Vorpommern", "MV"),
    ("  bayern  ", "BY"),
]

# one coordinate inside every Bundesland
COORDINATES = {
    "BW": (48.7758, 9.1829),
    "BY": (48.1372, 11.5755),
    "BE": (52.5200, 13.4050),
    "BB": (52.4000, 13.0600),
    "HB": (53.0793, 8.8017),
    "HH": (53.5511, 9.9937),
    "HE": (50.1109, 8.6821),
    "MV": (53.6355, 11.4012),
    "NI": (52.3759, 9.7320),
    "NW": (51.2277, 6.7735),
    "RP": (49.9929, 8.2473),
    "SL": (49.2402, 6.9969),
    "SN": (51.0504, 13.7373),
    "ST": (52.1205, 11.6276),
    "SH": (54.3233, 10.1228),
    "TH": (50.9848, 11.0299),
}

ARE_DATA = "data/ARE-Konsultationsinzidenz/ARE-Konsultationsinzidenz.tsv"


@pytest.mark.parametrize("name, expected_short", PROVINCE_SPELLINGS)
def test_province_to_short_accepts_every_spelling(name, expected_short):
    """Every spelling our sources use has to resolve to the same short code."""
    assert province_to_short(name) == expected_short


@pytest.mark.parametrize("short, coordinates", sorted(COORDINATES.items()))
def test_reverse_geocoding_resolves_every_bundesland(short, coordinates):
    """Coordinates -> province name -> short code -> region for all 16 Bundesländer."""
    province = rg.search(coordinates, mode=1)[0]["admin1"]
    assert province_to_short(province) == short, f"{province} did not resolve to {short}"
    assert province2region[short] in VALID_REGIONS


def test_geretsried_location():
    """The location from the logs that the region preselection was built on."""
    province = rg.search((47.8578, 11.4805), mode=1)[0]["admin1"]
    assert province_to_short(province) == "BY"
    assert province2region["BY"] == "Sueden"


def test_all_bundeslaender_are_mapped():
    """German name, English name and region must cover the same 16 short codes."""
    assert set(province_short2german) == set(province_short2english)
    assert set(province_short2german) == set(province2region)
    assert len(province2region) == 16
    for short, region in province2region.items():
        assert region in VALID_REGIONS, f"invalid region {region} for {short}"


def test_find_province_index_matches_rki_bundesland_names():
    """An English province name has to find the German name used in the RKI data."""
    bundeslaender = sorted(pd.read_csv(ARE_DATA, sep="\t")["Bundesland"].unique())

    for short, english_name in province_short2english.items():
        index = find_province_index(bundeslaender, english_name)
        assert index is not None, f"{english_name} not found in {bundeslaender}"
        assert province_to_short(bundeslaender[index]) == short


def test_find_province_index_reports_no_match_as_none():
    """None rather than 0, so a match on the first entry stays distinguishable."""
    assert find_province_index(["Baden-Wuerttemberg", "Bayern"], "Bavaria") == 1
    assert find_province_index(["Baden-Wuerttemberg", "Bayern"], "Baden-Württemberg") == 0
    assert find_province_index(["Baden-Wuerttemberg", "Bayern"], "Vienna") is None
    assert find_province_index([], "Bayern") is None


def test_unknown_province_is_rejected():
    """A province outside Germany must not be mapped to a Bundesland."""
    assert province_to_short("Vienna") is None
    assert province_to_short("Île-de-France") is None
    assert province_to_short(None) is None
    assert province_to_short("") is None


def test_canonical_key_folds_umlaut_spellings():
    """Different umlaut spellings fold together, different states stay apart."""
    assert canonical_province_key("Thüringen") == canonical_province_key("Thueringen")
    assert canonical_province_key("Baden-Württemberg") == canonical_province_key(
        "Baden-Wuerttemberg"
    )
    assert canonical_province_key("Sachsen") != canonical_province_key("Sachsen-Anhalt")
    assert len(set(map(canonical_province_key, province_short2german.values()))) == 16


def test_location_outside_germany_keeps_coordinate_keys(monkeypatch):
    """
    A visitor outside Germany used to leave location without latitude/longitude,
    which made the Abwasser tab raise a KeyError.
    """
    import location_manager as lm

    class ForeignResult:
        """An ipinfo result for a visitor outside Germany."""

        country = "AT"
        city = "Vienna"
        province = "Vienna"
        lat = 48.2082
        lng = 16.3738

    class ForeignLookup:
        error = False
        current_result = ForeignResult()

    monkeypatch.setattr(lm, "get_forwarded_ip", lambda: "1.2.3.4")
    monkeypatch.setattr(lm.geocoder, "ipinfo", lambda ip: ForeignLookup())
    monkeypatch.setattr(lm.st, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        lm, "streamlit_geolocation", lambda: {"latitude": None, "longitude": None}
    )

    location = lm.LocationManager().location

    assert location["latitude"] is None
    assert location["longitude"] is None
    assert location["province_short"] is None
    assert location["region"] == "Unknown"


def test_location_inside_germany_is_resolved(monkeypatch):
    """The happy path fills in short code, German name and region."""
    import location_manager as lm

    class GermanResult:
        """An ipinfo result for a visitor in Germany."""

        country = "DE"
        city = "Geretsried"
        province = "Bavaria"
        lat = 47.8578
        lng = 11.4805

    class GermanLookup:
        error = False
        current_result = GermanResult()

    monkeypatch.setattr(lm, "get_forwarded_ip", lambda: "1.2.3.4")
    monkeypatch.setattr(lm.geocoder, "ipinfo", lambda ip: GermanLookup())

    location = lm.LocationManager().location

    assert location["city"] == "Geretsried"
    assert location["latitude"] == 47.8578
    assert location["province_short"] == "BY"
    assert location["province_de"] == "Bayern"
    assert location["region"] == "Sueden"
