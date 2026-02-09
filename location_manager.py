"""A class to manage location derived from ip address or from self localization via streamlit_geolocation."""

import logging
from typing import Optional, Dict, Any

import streamlit as st
from streamlit_geolocation import streamlit_geolocation
import reverse_geocoder as rg  # reverse geocode from coordinates
import geocoder  # geocode from ip address

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# map admin2 to short name e.g. 'bavaria' to 'BY'
province2short: Dict[str, str] = {
    "Baden-Wurttemberg": "BW",
    "Bavaria": "BY",
    "Berlin": "BE",
    "Brandenburg": "BB",
    "Bremen": "HB",
    "Hamburg": "HH",
    "Hessen": "HE",
    "Mecklenburg-Vorpommern": "MV",
    "Niedersachsen": "NI",
    "Nordrhein-Westfalen": "NW",
    "Rheinland-Pfalz": "RP",
    "Saarland": "SL",
    "Sachsen": "SN",
    "Sachsen-Anhalt": "ST",
    "Schleswig-Holstein": "SH",
    "Thuringen": "TH",
}

# check that all short provinces are in province2short
for province in [
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
]:
    assert province in province2short.values()

# map admin2 to ['Mitte (West)', 'Norden (West)', 'Osten', 'Sueden']
province2region: Dict[str, str] = {
    "BW": "Sueden",
    "BY": "Sueden",
    "BE": "Mitte (West)",
    "BB": "Osten",
    "HB": "Norden (West)",
    "HH": "Norden (West)",
    "HE": "Mitte (West)",
    "MV": "Osten",
    "NI": "Norden (West)",
    "NW": "Mitte (West)",
    "RP": "Mitte (West)",
    "SL": "Mitte (West)",
    "SN": "Osten",
    "ST": "Osten",
    "SH": "Norden (West)",
    "TH": "Osten",
}

# check that all short provinces are in province2region
for province in [
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
]:
    assert province in province2region.keys(), f"{province} not in province2region"


def get_forwarded_ip() -> str | None:
    """
    Get the IP address from the X-Forwarded-For header.
    This is useful when the app is behind a reverse proxy or load balancer.
    """
    logger.debug("Getting forwarded IP address")
    headers = st.context.headers
    # Example: "X-Forwarded-For': '13.51.91.225, 162.158.90.188'"
    if "X-Forwarded-For" in headers:
        x_forwarded_for = headers["X-Forwarded-For"]
        first_ip = x_forwarded_for.split(", ")[0]
        logger.info("Forwarded IP: %s", first_ip)
        return first_ip
    else:
        logger.debug("No X-Forwarded-For header found")
        return None


class LocationManager:
    """A class to manage location derived from ip address or from self localization."""

    def __init__(self) -> None:
        """
        Initialize the LocationManager with the path to the geonames file.

        Args:
            geonames_file (str): The path to the geonames file.
            delimiter (str): The delimiter used in the geonames file. Default is tab.
        """
        self.ip_address: Optional[str] = get_forwarded_ip()
        self.location: Dict[str, Any] = {}
        if self.ip_address:
            logger.info("Using IP address: %s", self.ip_address)
            geocoder_result = geocoder.ipinfo(self.ip_address)
            if geocoder_result.error is False:
                # geocode was successful
                if geocoder_result.current_result.country == "DE":
                    logger.info(
                        "Location determined: %s, %s",
                        geocoder_result.current_result.city,
                        geocoder_result.current_result.country,
                    )
                    self.location["city"] = geocoder_result.current_result.city
                    self.location["country"] = geocoder_result.current_result.country
                    self.location["province"] = geocoder_result.current_result.province
                    self.location["latitude"] = geocoder_result.current_result.lat
                    self.location["longitude"] = geocoder_result.current_result.lng
                else:
                    logger.warning(
                        "User outside Germany: %s",
                        geocoder_result.current_result.country,
                    )
                    st.warning(
                        "You seem to be outside of Germany but the data is only available for Germany. Please select your location of interest manually."
                    )
            else:
                logger.error("Geocoding failed for IP %s", self.ip_address)
                st.warning(
                    f"Could not determine your location from IP address {self.ip_address}. Please accept localization via browser or select your location of interest manually."
                )
                self.get_location_from_browser()
        else:
            logger.warning("No IP address available for localization")
            st.warning(
                "Could not determine your IP address for localization. Please accept localization via browser or select your location of interest manually."
            )
            self.get_location_from_browser()

        self.add_province()
        self.add_province_short()
        logger.debug("Final location: %s", self.location)

    def get_location_from_browser(self) -> None:
        """
        Get the location from the browser using streamlit_geolocation.
        """
        logger.info("Getting location from browser")
        location_result = streamlit_geolocation()
        self.location["latitude"] = location_result["latitude"]
        self.location["longitude"] = location_result["longitude"]

    def add_province(self) -> None:
        """
        Get the province from the location if necessary.
        """
        if (
            "latitude" in self.location
            and self.location["latitude"] is not None
            and "longitude" in self.location
            and self.location["longitude"] is not None
            and not "province" in self.location
        ):
            logger.info("Adding province to location via reverse geocoding")
            # add province to location
            # get the coordinates from the location
            coordinates = (self.location["latitude"], self.location["longitude"])
            # use reverse geocoding to get the province from the coordinates
            geocode = rg.search(coordinates, mode=1)
            # transform administrative area to bundesland, bavaria to BY
            self.location["province"] = geocode[0]["admin1"]
            logger.debug("Province determined: %s", self.location["province"])

    def add_province_short(self) -> None:
        """
        Add the province short name to the location.
        """
        if "province" in self.location:
            logger.debug("Adding province short name and region")
            # add province short name to location and region
            self.location["province_short"] = province2short[self.location["province"]]
            self.location["region"] = province2region[self.location["province_short"]]
            logger.debug(
                "Province short: %s, Region: %s",
                self.location.get("province_short"),
                self.location.get("region"),
            )
