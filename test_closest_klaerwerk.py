"""Tests for the helper functions in app.py."""

import pandas as pd
from app import find_closest_klaerwerk, render_traffic_lights

ABWASSER_DATA = "data/Abwassersurveillance_AMELAG/amelag_einzelstandorte.tsv"


def test_find_closest_klaerwerk():
    """
    Test the find_closest_klaerwerk function with a known location and dataset.
    """
    # Test location from logs
    user_location = {
        "city": "Geretsried",
        "country": "DE",
        "province": "Bavaria",
        "latitude": 47.8578,
        "longitude": 11.4805,
        "province_short": "BY",
        "region": "Sueden",
    }

    print("Loading Abwasser data...")
    abwasser = pd.read_csv(ABWASSER_DATA, sep="\t")

    print(f"Total rows in dataset: {len(abwasser)}")
    print(f"Total distinct standorte: {len(abwasser['standort'].unique())}")
    print()

    # Run the test
    result = find_closest_klaerwerk(abwasser, user_location)
    print(f"\nResult: {result}")

    # Assertion
    assert result == "Starnberg", f"Expected 'Starnberg' but got '{result}'"
    print("\n✓ Test passed: Starnberg is the closest Klärwerk to Geretsried")


def test_find_closest_klaerwerk_uses_geodesic_distance():
    """
    Measuring in raw degrees rather than kilometres used to pick the wrong plant.

    For this location in northern Baden-Württemberg, squared degree distance
    favours Stuttgart (57 km away) over Heidelberg (39 km away), because it
    treats a degree of longitude as if it were as wide as a degree of latitude.
    """
    user_location = {"latitude": 49.3, "longitude": 9.2}
    abwasser = pd.read_csv(ABWASSER_DATA, sep="\t")

    assert find_closest_klaerwerk(abwasser, user_location) == "Heidelberg"


def test_find_closest_klaerwerk_without_any_standort():
    """An empty data set yields no plant instead of raising."""
    empty = pd.DataFrame({"standort": pd.Series(dtype="object")})

    assert find_closest_klaerwerk(empty, {"latitude": 48.0, "longitude": 11.0}) is None


def test_render_traffic_lights_without_data():
    """
    An empty selection must not reach st.columns(0), which raises.

    This happens whenever the user deselects every age group.
    """
    render_traffic_lights({})
    render_traffic_lights({}, "Some heading")
