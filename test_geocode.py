from geocode import Geocoder   

def test_geocode():
    """
    Test the geocode function of the Geocoder class.
    """
    # Create an instance of the Geocoder class
    geocoder = Geocoder()

    # Test cases
    test_cases = [
        ("Los Angeles", "CA", None),
        ("Munich", None, None),
        ("München", None, None),
        ("Altötting", "BY", "DE"),
    ]

    for city, state, country in test_cases:
        result = geocoder.geocode(city, state, country)
        print(f"Coordinates of {city}, {state}, {country}: {result}")

        assert result != (None,None), f"Geocode failed for {city}, {state}, {country}"

