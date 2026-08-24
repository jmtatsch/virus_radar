"""A class to manage location derived from ip address or from self localization via streamlit_geolocation."""

import logging
from typing import Optional, Dict, Any, Sequence

import streamlit as st
from streamlit_geolocation import streamlit_geolocation
import reverse_geocoder as rg  # reverse geocode from coordinates
import geocoder  # geocode from ip address

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# canonical German name of every Bundesland, keyed by its official short code
province_short2german: Dict[str, str] = {
    "BW": "Baden-Württemberg",
    "BY": "Bayern",
    "BE": "Berlin",
    "BB": "Brandenburg",
    "HB": "Bremen",
    "HH": "Hamburg",
    "HE": "Hessen",
    "MV": "Mecklenburg-Vorpommern",
    "NI": "Niedersachsen",
    "NW": "Nordrhein-Westfalen",
    "RP": "Rheinland-Pfalz",
    "SL": "Saarland",
    "SN": "Sachsen",
    "ST": "Sachsen-Anhalt",
    "SH": "Schleswig-Holstein",
    "TH": "Thüringen",
}

# English name of every Bundesland as returned by reverse_geocoder and ipinfo
province_short2english: Dict[str, str] = {
    "BW": "Baden-Wuerttemberg",
    "BY": "Bavaria",
    "BE": "Berlin",
    "BB": "Brandenburg",
    "HB": "Bremen",
    "HH": "Hamburg",
    "HE": "Hesse",
    "MV": "Mecklenburg-Western Pomerania",
    "NI": "Lower Saxony",
    "NW": "North Rhine-Westphalia",
    "RP": "Rhineland-Palatinate",
    "SL": "Saarland",
    "SN": "Saxony",
    "ST": "Saxony-Anhalt",
    "SH": "Schleswig-Holstein",
    "TH": "Thuringia",
}

# map short province to ['Mitte (West)', 'Norden (West)', 'Osten', 'Sueden']
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


def canonical_province_key(name: str) -> str:
    """
    Fold a Bundesland name into a spelling-insensitive lookup key.

    Our sources disagree on how to write umlauts: reverse_geocoder returns
    'Baden-Wuerttemberg', the RKI data sets use 'Thueringen' and we write
    'Thüringen'. Expanding the umlaut and then collapsing the digraph maps all
    three spellings ('ü', 'ue', 'u') onto the same key, so a lookup no longer
    depends on which spelling a source happens to use.
    """
    folded = name.strip().lower()
    for umlaut, digraph in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        folded = folded.replace(umlaut, digraph)
    for digraph, vowel in (("ae", "a"), ("oe", "o"), ("ue", "u")):
        folded = folded.replace(digraph, vowel)
    return "".join(char for char in folded if char.isalpha())


# every known spelling of a Bundesland, mapped to its short code
_province_short_by_key: Dict[str, str] = {
    canonical_province_key(name): short
    for mapping in (province_short2german, province_short2english)
    for short, name in mapping.items()
}


def province_to_short(province: Optional[str]) -> Optional[str]:
    """
    Resolve any German or English spelling of a Bundesland to its short code.

    Returns None when the name is empty or does not belong to a Bundesland,
    e.g. for a province outside Germany.
    """
    if not province:
        return None
    return _province_short_by_key.get(canonical_province_key(province))


def find_province_index(
    options: Sequence[str], province: Optional[str]
) -> Optional[int]:
    """
    Locate a Bundesland within a data set's own list of Bundesland names.

    Matching goes through the short code, so an English province name from
    reverse_geocoder also finds the German name used in the RKI data sets.
    Returns None when the province is unknown or not among options, which lets
    callers tell 'no match' apart from 'matched the first entry'.
    """
    short = province_to_short(province)
    if short is None:
        return None
    keys = {
        canonical_province_key(province_short2german[short]),
        canonical_province_key(province_short2english[short]),
    }
    for index, option in enumerate(options):
        if canonical_province_key(option) in keys:
            return index
    return None


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
        Determine the visitor's location from their IP address, falling back to
        browser geolocation whenever that does not yield a German location.

        'latitude' and 'longitude' are always present in self.location, so
        callers can test them without guarding every single lookup; any
        localization path may leave them None.
        """
        self.ip_address: Optional[str] = get_forwarded_ip()
        self.location: Dict[str, Any] = {"latitude": None, "longitude": None}
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
                        "You seem to be outside of Germany but the data is only available for Germany. Please accept localization via browser or select your location of interest manually."
                    )
                    # the IP is of no use here, but the browser may still report a
                    # German position, e.g. when the visitor is behind a VPN
                    self.get_location_from_browser()
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
            self.location["latitude"] is not None
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
        Add the short code, the canonical German name and the region of the
        province to the location.
        """
        province = self.location.get("province")
        province_short = province_to_short(province)
        if province_short is None:
            if province:
                logger.warning(
                    "Province '%s' could not be resolved to a Bundesland", province
                )
            self.location["province_short"] = None
            self.location["province_de"] = None
            self.location["region"] = "Unknown"
            return

        self.location["province_short"] = province_short
        # the German name is what the RKI data sets use to label a Bundesland
        self.location["province_de"] = province_short2german[province_short]
        self.location["region"] = province2region[province_short]
        logger.debug(
            "Province: %s, short: %s, Region: %s",
            self.location["province_de"],
            self.location["province_short"],
            self.location["region"],
        )
