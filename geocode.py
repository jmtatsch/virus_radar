# download zip file from geonames
import os
import requests
import zipfile
import pandas as pd

class Geocoder:
    def __init__(self, url="https://download.geonames.org/export/dump/cities1000.zip", download_path="cities1000.zip", extract_dir="cities1000"):
        self.url = url
        self.download_path = download_path
        self.extract_dir = extract_dir
        self.file_path = 'cities1000/cities1000.txt'
        # check if file cities1000/cities1000.txt exists
        if os.path.exists(self.file_path):
            print(f"File {self.file_path} already exists.")
        else:
            print(f"File {self.file_path} does not exist. Downloading...")
            self.download_zip()
            self.file_path = self.unzip_file()
        self.data = self.load_dataframe(self.file_path)


    def download_zip(self):
        response = requests.get(self.url)
        response.raise_for_status()
        with open(self.download_path, "wb") as f:
            f.write(response.content)
        return self.download_path

    def unzip_file(self):
        if not os.path.exists(self.extract_dir):
            os.makedirs(self.extract_dir)
        with zipfile.ZipFile(self.download_path, "r") as zip_ref:
            zip_ref.extractall(self.extract_dir)
            # Assuming the zip contains one file
            files = zip_ref.namelist()
        return os.path.join(self.extract_dir, files[0]) if files else None

    def load_dataframe(self, filepath, delimiter="\t"):
        # Column names
        columns = [
                "geonameid", "name", "asciiname", "alternatenames", "latitude", "longitude",
                "feature_class", "feature_code", "country_code", "cc2", "admin1_code",
                "admin2_code", "admin3_code", "admin4_code", "population", "elevation",
                "dem", "timezone", "modification_date"
        ]
        return pd.read_csv(filepath, delimiter=delimiter, low_memory=False, names=columns, encoding="utf-8")

    def geocode(self, city, state=None, country=None) -> tuple[float, float] | tuple[None, None]:
        """"
        "Geocode a city using the geonames database.
        Parameters:
            city (str): The name of the city.
            state (str, optional): The state or province.
            country (str, optional): The country.
        Returns:
            tuple: A tuple containing the latitude and longitude of the city.
        """ 
        data = self.data.copy()

        # these require a different table to resolve admin code and thus are not active
        # filter the dataframe based on city, state, and country
        #if state:
        #    data = data[data['admin1_code'].str.lower() == state.lower()]

        if country:
            data = data[data['country_code'].str.lower() == country.lower()]
        
        result = data[data['name'].str.lower() == city.lower()]

        # if there are no results, try to match the city name with the 'asciiname' column
        if result.empty:
            result = data[data['asciiname'].str.lower() == city.lower()]

        # if there are no results, try to match the city name with the 'alternatenames' column
        if result.empty:
            result = data[data['alternatenames'].str.contains(city.lower(), case=False, na=False)]

        # if there are multiple results, return the most likely one
        if len(result) > 1:
            # Sort by population (descending) and take the first one
            result = result.sort_values(by='population', ascending=False).head(1)

        if not result.empty:
            lat = result.iloc[0]['latitude']
            lon = result.iloc[0]['longitude']
            return float(lat), float(lon)
        else:
            return None, None

if __name__ == "__main__":
    geocoder = Geocoder()

    city = "München"
    result = geocoder.geocode(city)
    print(f"Coordinates of {city}: {result}")
