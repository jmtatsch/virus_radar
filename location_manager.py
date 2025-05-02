"""A class to manage location derived from ip address or from self localization vis streamlit_geolocation."""
import streamlit as st
from streamlit_geolocation import streamlit_geolocation
import reverse_geocoder as rg # reverse geocode from coordinates
import geocoder # geocode from ip adress

# map admin2 to short name e.g. 'bavaria' to 'BY'
province2short = {
    'Baden-Wurttemberg': 'BW',
    'Bavaria': 'BY',
    'Berlin': 'BE',
    'Brandenburg': 'BB',
    'Bremen': 'HB',
    'Hamburg': 'HH',
    'Hessen': 'HE',
    'Mecklenburg-Vorpommern': 'MV',
    'Niedersachsen': 'NI',
    'Nordrhein-Westfalen': 'NW',
    'Rheinland-Pfalz': 'RP',
    'Saarland': 'SL',
    'Sachsen': 'SN',
    'Sachsen-Anhalt': 'ST',
    'Schleswig-Holstein': 'SH',
    'Thuringen': 'TH'
}

# check that all short provinces are in province2short
for province in ['BB', 'BE', 'BW', 'BY', 'HB', 'HE', 'HH', 'MV', 'NI', 'NW', 'RP', 'SH', 'SL', 'SN', 'ST', 'TH']:
    assert province in province2short.values()

# map admin2 to ['Mitte (West)', 'Norden (West)', 'Osten', 'Sueden']
province2region = {
    'BW': 'Sueden',
    'BY': 'Sueden',
    'BE': 'Mitte (West)',
    'BB': 'Osten',
    'HB': 'Norden (West)',
    'HH': 'Norden (West)',
    'HE': 'Mitte (West)',
    'MV': 'Osten',
    'NI': 'Norden (West)',
    'NW': 'Mitte (West)',
    'RP': 'Mitte (West)',
    'SL': 'Mitte (West)',
    'SN': 'Osten',
    'ST': 'Osten',
    'SH': 'Norden (West)',
    'TH': 'Osten'
}

# check that all short provinces are in province2region
for province in ['BB', 'BE', 'BW', 'BY', 'HB', 'HE', 'HH', 'MV', 'NI', 'NW', 'RP', 'SH', 'SL', 'SN', 'ST', 'TH']:
    assert province in province2region.keys(), f'{province} not in province2region'


def get_forwarded_ip() -> str | None:
    """
    Get the IP address from the X-Forwarded-For header.
    This is useful when the app is behind a reverse proxy or load balancer.
    """
    headers = st.context.headers
    # Example: "X-Forwarded-For': '13.51.91.225, 162.158.90.188'"
    if 'X-Forwarded-For' in headers:
        x_forwarded_for = headers['X-Forwarded-For']
        first_ip = x_forwarded_for.split(', ')[0]

        return first_ip
    else:
        return None

class LocationManager:
    """A class to manage location derived from ip address or from self localization."""

    def __init__(self):
        """
        Initialize the LocationManager with the path to the geonames file.

        Args:
            geonames_file (str): The path to the geonames file.
            delimiter (str): The delimiter used in the geonames file. Default is tab.
        """
        self.ip_address = get_forwarded_ip()
        self.location = {}
        if self.ip_address:
            geocoder_result = geocoder.ipinfo(self.ip_address)
            if geocoder_result.error is False:
                # geocode was successful
                if geocoder_result.current_result.country == 'DE':
                    self.location['city'] = geocoder_result.current_result.city
                    self.location['country'] = geocoder_result.current_result.country
                    self.location['province'] = geocoder_result.current_result.province
                    self.location['latitude'] = geocoder_result.current_result.lat
                    self.location['longitude'] = geocoder_result.current_result.lng
                else:
                    st.warning("You seem to be outside of Germany but the data is only available for Germany. Please select your location of interest manually.")
            else:
                st.warning(f"Could not determine your location from IP address {self.ip_address}. Please accept localization via browser or select your location of interest manually.")
                self.get_location_from_browser()
        else:
            st.warning("Could not determine your IP address for localization. Please accept localization via browser or select your location of interest manually.")
            self.get_location_from_browser()

        self.add_province()
        self.add_province_short()
        print(self.location)

    def get_location_from_browser(self):
        """
        Get the location from the browser using streamlit_geolocation.
        """
        location_result = streamlit_geolocation()
        self.location['latitude'] = location_result['latitude']
        self.location['longitude'] = location_result['longitude']

    def add_province(self):
        """
        Get the province from the location if necessary.
        """
        if 'latitude' in self.location and self.location['latitude'] is not None and 'longitude' in self.location and self.location['longitude'] is not None and not 'province' in self.location:
            # add province to location
            # get the coordinates from the location
            coordinates = (self.location['latitude'], self.location['longitude'])
            # use reverse geocoding to get the province from the coordinates
            geocode = rg.search(coordinates, mode=1)
            # transform administrative area to bundesland, bavaria to BY
            self.location['province'] = geocode[0]['admin1']

    def add_province_short(self):
        """
        Add the province short name to the location.
        """
        if 'province' in self.location :
            # add province short name to location and region
            self.location['province_short'] = province2short[self.location['province']]
            self.location['region'] = province2region[self.location['province_short']]
