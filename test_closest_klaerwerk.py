"""Test script for find_closest_klaerwerk function."""

import pandas as pd
from app import find_closest_klaerwerk


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
    abwasser = pd.read_csv(
        "data/Abwassersurveillance_AMELAG/amelag_einzelstandorte.tsv", sep="\t"
    )

    print(f"Total rows in dataset: {len(abwasser)}")
    print(f"Total distinct standorte: {len(abwasser['standort'].unique())}")
    print()

    # Run the test
    result = find_closest_klaerwerk(abwasser, user_location)
    print(f"\nResult: {result}")

    # Assertion
    assert result == "Starnberg", f"Expected 'Starnberg' but got '{result}'"
    print("\n✓ Test passed: Starnberg is the closest Klärwerk to Geretsried")
