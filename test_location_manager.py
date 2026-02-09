"""Test script for LocationManager functionality."""

import reverse_geocoder as rg
from location_manager import province2short, province2region


def test_province_mappings():
    """Test that province mappings are correct."""
    print("Testing province mappings...")

    # Test case from logs
    test_province = "Bavaria"
    expected_short = "BY"
    expected_region = "Sueden"

    actual_short = province2short.get(test_province)
    assert (
        actual_short == expected_short
    ), f"Expected {expected_short} for {test_province}, got {actual_short}"

    actual_region = province2region.get(actual_short)
    assert (
        actual_region == expected_region
    ), f"Expected {expected_region} for {actual_short}, got {actual_region}"

    print(f"✓ {test_province} -> {actual_short} -> {actual_region}")


def test_reverse_geocoding():
    """Test reverse geocoding for known locations."""
    print("\nTesting reverse geocoding...")

    # Test case from logs: Geretsried, Bavaria
    test_cases = [
        {
            "name": "Geretsried, Bavaria",
            "coords": (47.8578, 11.4805),
            "expected_province": "Bavaria",
            "expected_short": "BY",
            "expected_region": "Sueden",
        },
        {
            "name": "Berlin",
            "coords": (52.5200, 13.4050),
            "expected_province": "Berlin",
            "expected_short": "BE",
            "expected_region": "Mitte (West)",
        },
        {
            "name": "Hamburg",
            "coords": (53.5511, 9.9937),
            "expected_province": "Hamburg",
            "expected_short": "HH",
            "expected_region": "Norden (West)",
        },
    ]

    for test_case in test_cases:
        print(f"\n  Testing {test_case['name']}...")

        # Reverse geocode
        geocode = rg.search(test_case["coords"], mode=1)
        province = geocode[0]["admin1"]

        print(f"    Coordinates: {test_case['coords']}")
        print(f"    Province: {province}")

        # Verify province
        assert (
            province == test_case["expected_province"]
        ), f"Expected province {test_case['expected_province']}, got {province}"

        # Get short name and region
        province_short = province2short[province]
        region = province2region[province_short]

        print(f"    Province short: {province_short}")
        print(f"    Region: {region}")

        # Verify mappings
        assert (
            province_short == test_case["expected_short"]
        ), f"Expected province short {test_case['expected_short']}, got {province_short}"
        assert (
            region == test_case["expected_region"]
        ), f"Expected region {test_case['expected_region']}, got {region}"

        print(f"    ✓ All checks passed for {test_case['name']}")


def test_all_provinces():
    """Test that all provinces have mappings."""
    print("\nTesting all province mappings...")

    all_provinces = [
        "BB",
        "BE",
        "BW",
        "BY",
        "HB",
        "HE",
        "HH",
        "MV",
        "NI",
        "NW",
        "RP",
        "SH",
        "SL",
        "SN",
        "ST",
        "TH",
    ]

    for short in all_provinces:
        # Check that short province is in province2region
        assert short in province2region, f"{short} not in province2region"
        region = province2region[short]

        # Check that region is valid
        valid_regions = ["Mitte (West)", "Norden (West)", "Osten", "Sueden"]
        assert region in valid_regions, f"Invalid region {region} for {short}"

        print(f"  {short} -> {region}")

    print(f"\n✓ All {len(all_provinces)} provinces have valid mappings")


def test_geretsried_location():
    """Test the specific location from logs."""
    print("\nTesting Geretsried location from logs...")

    # Expected location from logs
    expected = {
        "city": "Geretsried",
        "country": "DE",
        "province": "Bavaria",
        "latitude": 47.8578,
        "longitude": 11.4805,
        "province_short": "BY",
        "region": "Sueden",
    }

    # Verify reverse geocoding
    coords = (expected["latitude"], expected["longitude"])
    geocode = rg.search(coords, mode=1)
    province = geocode[0]["admin1"]

    print(f"  City: {expected['city']}")
    print(f"  Coordinates: ({expected['latitude']}, {expected['longitude']})")
    print(f"  Province: {province}")

    assert (
        province == expected["province"]
    ), f"Expected province {expected['province']}, got {province}"

    province_short = province2short[province]
    region = province2region[province_short]

    print(f"  Province short: {province_short}")
    print(f"  Region: {region}")

    assert (
        province_short == expected["province_short"]
    ), f"Expected {expected['province_short']}, got {province_short}"
    assert region == expected["region"], f"Expected {expected['region']}, got {region}"

    print(f"\n✓ Geretsried location validated successfully")


if __name__ == "__main__":
    print("=" * 60)
    print("LocationManager Test Suite")
    print("=" * 60)

    try:
        test_province_mappings()
        test_all_provinces()
        test_reverse_geocoding()
        test_geretsried_location()

        print("\n" + "=" * 60)
        print("✓ All tests passed!")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        raise
    except Exception as e:
        print(f"\n✗ Error: {e}")
        raise
