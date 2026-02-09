"""
This script defines a local Geocoder class that downloads, extracts, and parses geospatial data from the GeoNames dataset.
It provides functionality to locally reverse geocode cities by retrieving their latitude and longitude from the dataset.
The Geocoder class is initialized with a URL to the GeoNames cities1000 dataset, and it handles downloading,
extracting, and loading the data into a pandas DataFrame.
The geocode method allows users to find the coordinates of a specified city, with optional country filtering.
"""

import logging
import os
import zipfile
from typing import Optional, Tuple

import requests
import pandas as pd

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class Geocoder:
    """
    The Geocoder class is designed to handle the process of downloading, extracting, and parsing geospatial data
    from the GeoNames dataset (specifically the cities1000 dataset). It facilitates geocoding operations by loading
    the dataset into a pandas DataFrame and providing a method to retrieve the latitude and longitude of a specified
    city (with optional country filtering).

    Attributes:
        url (str): The URL to download the GeoNames cities1000 dataset ZIP file.
        download_path (str): The local file path where the downloaded ZIP file is saved.
        extract_dir (str): The directory where the ZIP file's contents are extracted.
        file_path (str): The path to the extracted data file (expected to be in the 'cities1000/cities1000.txt' location).
        data (pandas.DataFrame): The DataFrame containing the geospatial data loaded from the extracted file.

    Methods:
        __init__:
            Initializes the Geocoder by checking for the existence of the required data file. If the file does not exist,
            it triggers the download and extraction process and subsequently loads the data into a DataFrame.

        download_zip():
            Downloads the ZIP file from the specified URL and saves it to the local download_path. If the HTTP request fails,
            an HTTPError is raised.

        unzip_file():
            Unzips the downloaded ZIP file into the specified extract_dir. This method assumes that the ZIP file contains
            exactly one file and returns the full path to the extracted file. It automatically creates the extraction directory
            if it does not already exist.

        load_dataframe(filepath, delimiter="\t"):
            Reads the tab-delimited data file given by filepath into a pandas DataFrame using predefined column names.

        geocode(city: str, country=None) -> tuple[float, float] | tuple[None, None]:
            Locates and returns the latitude and longitude of the specified city by filtering the DataFrame (with an optional
            country filter). It tries to match the city against multiple columns (name, asciiname, alternatenames) and returns
            the coordinates of the most likely match, preferably by population ranking if multiple matches are found.

    Example:
        geocoder = Geocoder()
        latitude, longitude = geocoder.geocode("Berlin", country="DE")
        if latitude is not None and longitude is not None:
            print(f"Coordinates of Berlin: {latitude}, {longitude}")
            print("City not found.")
    """

    def __init__(
        self,
        url: str = "https://download.geonames.org/export/dump/cities1000.zip",
        download_path: str = "cities1000.zip",
        extract_dir: str = "cities1000",
    ) -> None:
        self.url = url
        self.download_path = download_path
        self.extract_dir = extract_dir
        self.file_path = "cities1000/cities1000.txt"
        # check if file cities1000/cities1000.txt exists
        if os.path.exists(self.file_path):
            logger.info("File %s already exists.", self.file_path)
        else:
            logger.info("File %s does not exist. Downloading...", self.file_path)
            self.download_zip()
            self.file_path = self.unzip_file()
            os.remove(self.download_path)
        self.data = self.load_dataframe(self.file_path)

    def download_zip(self) -> str:
        """
        Downloads a file from the URL specified in the instance and saves it as a ZIP file to the download path.

        This method makes an HTTP GET request to the URL stored in the instance attribute 'url'. It raises an HTTPError
        if the request fails. Upon a successful response, it writes the binary content of the response to a file located at
        the path specified by the instance attribute 'download_path' and returns this path.

        Returns:
            str: The file path where the ZIP file has been saved.

        Raises:
            HTTPError: If the HTTP request returned an unsuccessful status code.
        """
        logger.info("Downloading file from %s", self.url)
        response = requests.get(self.url, timeout=30)
        response.raise_for_status()
        with open(self.download_path, "wb") as f:
            f.write(response.content)
        logger.info("Downloaded file to %s", self.download_path)
        return self.download_path

    def unzip_file(self) -> Optional[str]:
        """
        Extracts the first file from the zip archive specified by self.download_path and returns its full path.

        This method performs the following actions:
            1. Checks if the directory given by self.extract_dir exists and creates it if not.
            2. Opens the zip file at self.download_path and extracts its contents into self.extract_dir.
            3. Retrieves the list of files in the zip archive and returns the full path to the first file.
            4. If the zip file is empty, it returns None.

        Assumes:
            - The zip archive contains exactly one file.
        """
        logger.info("Extracting file to %s", self.extract_dir)
        if not os.path.exists(self.extract_dir):
            os.makedirs(self.extract_dir)
        with zipfile.ZipFile(self.download_path, "r") as zip_ref:
            zip_ref.extractall(self.extract_dir)
            # Assuming the zip contains one file
            files = zip_ref.namelist()
        logger.info("Extracted %d file(s)", len(files))
        return os.path.join(self.extract_dir, files[0]) if files else None

    def load_dataframe(self, filepath: str, delimiter: str = "\t") -> pd.DataFrame:
        """
        Loads a tabular dataset from a specified file into a pandas DataFrame using predefined column names.

        Parameters:
            filepath (str): The path to the input file containing the data.
            delimiter (str, optional): The delimiter used to separate the values in the file.
                                       Defaults to tab ("\t").

        Returns:
            pandas.DataFrame: A DataFrame with the following columns:
                - "geonameid"
                - "name"
                - "asciiname"
                - "alternatenames"
                - "latitude"
                - "longitude"
                - "feature_class"
                - "feature_code"
                - "country_code"
                - "cc2"
                - "admin1_code"
                - "admin2_code"
                - "admin3_code"
                - "admin4_code"
                - "population"
                - "elevation"
                - "dem"
                - "timezone"
                - "modification_date"
        """
        logger.info("Loading dataframe from %s", filepath)
        # Column names
        columns = [
            "geonameid",
            "name",
            "asciiname",
            "alternatenames",
            "latitude",
            "longitude",
            "feature_class",
            "feature_code",
            "country_code",
            "cc2",
            "admin1_code",
            "admin2_code",
            "admin3_code",
            "admin4_code",
            "population",
            "elevation",
            "dem",
            "timezone",
            "modification_date",
        ]
        df = pd.read_csv(
            filepath,
            delimiter=delimiter,
            low_memory=False,
            names=columns,
            encoding="utf-8",
        )
        logger.info("Loaded %d records", len(df))
        return df

    def geocode(
        self, city: str, country: Optional[str] = None
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        Geocode a city using the geonames database.
        Parameters:
            city (str): The name of the city.
            state (str, optional): The state or province.
            country (str, optional): The country.
        Returns:
            tuple: A tuple containing the latitude and longitude of the city.
        """
        logger.debug("Geocoding city: %s, country: %s", city, country)
        data = self.data.copy()

        # these require a different table to resolve admin code and thus are not active
        # filter the dataframe based on city, state, and country
        # if state:
        #    data = data[data['admin1_code'].str.lower() == state.lower()]

        if country:
            data = data[data["country_code"].str.lower() == country.lower()]

        result = data[data["name"].str.lower() == city.lower()]

        # if there are no results, try to match the city name with the 'asciiname' column
        if result.empty:
            result = data[data["asciiname"].str.lower() == city.lower()]

        # if there are no results, try to match the city name with the 'alternatenames' column
        if result.empty:
            result = data[
                data["alternatenames"].str.contains(
                    city.lower(), case=False, na=False, regex=False
                )
            ]

        # if there are multiple results, return the most likely one
        if len(result) > 1:
            # Sort by population (descending) and take the first one
            result = result.sort_values(by="population", ascending=False).head(1)

        if not result.empty:
            lat = result.iloc[0]["latitude"]
            lon = result.iloc[0]["longitude"]
            logger.debug("Found coordinates for %s: (%s, %s)", city, lat, lon)
            return float(lat), float(lon)
        else:
            logger.warning("Could not find coordinates for city: %s", city)
            return None, None


if __name__ == "__main__":
    geocoder = Geocoder()

    CITY = "München"
    geocode_result = geocoder.geocode(CITY)
    logger.info("Coordinates of %s: %s", CITY, geocode_result)
