import pandas as pd
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import requests
from bs4 import BeautifulSoup
import re



# Function to convert DMS (Degrees, Minutes, Seconds) to decimal format
def dms_to_decimal(dms, direction):
    dms = list(map(float, dms)) + [0] * (3 - len(dms))  # Ensure 3 values: degrees, minutes, seconds
    degrees, minutes, seconds = dms
    decimal = degrees + minutes / 60 + seconds / 3600
    if direction in ['S', 'W']:  # South or West should be negative
        decimal *= -1
    return decimal

# Set up retry strategy for requests
retry_strategy = Retry(
    total=3,
    status_forcelist=[429, 500, 502, 503, 504],
    method_whitelist=["GET"],
    backoff_factor=1
)
adapter = HTTPAdapter(max_retries=retry_strategy)
http = requests.Session()
http.mount("https://", adapter)
http.mount("http://", adapter)


def fetch_wikipedia_coordinates(city_name, lang='en'):
    """
    Scrape coordinates from Wikipedia using BeautifulSoup, with retry and error handling.
    Supports both English ('en') and Hebrew ('he') Wikipedia.
    Tries appending "(יישוב)", "(כפר)", "(קיבוץ)", "(מושב)" to the city name if no coordinates are found in Hebrew.
    """
    if pd.isna(city_name):
        return None, None  # Return if the city name is missing
    
  # Add a delay to avoid being blocked by Wikipedia
    if lang == 'en':
        url = f"https://en.wikipedia.org/wiki/{city_name.replace(' ', '_')}"
    else:  # Hebrew Wikipedia
        url = f"https://he.wikipedia.org/wiki/{city_name.replace(' ', '_')}"

    try:
        response = http.get(url)

        # Check if the page exists
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Locate the infobox and search for the coordinates section
            infobox = soup.find('table', class_='infobox')
            if infobox:
                coordinates_section = infobox.find('span', class_='geo-dms')
                if coordinates_section:
                    try:
                        latitude_span = coordinates_section.find('span', class_='latitude')
                        longitude_span = coordinates_section.find('span', class_='longitude')
                        if latitude_span and longitude_span:
                            lat_text = latitude_span.text
                            lon_text = longitude_span.text

                            lat_parts = lat_text.replace('°', ' ').replace("′", ' ').replace('″', ' ').split()
                            lon_parts = lon_text.replace('°', ' ').replace("′", ' ').replace('″', ' ').split()

                            lat_direction = lat_parts.pop()
                            lon_direction = lon_parts.pop()

                            latitude = dms_to_decimal(lat_parts, lat_direction)
                            longitude = dms_to_decimal(lon_parts, lon_direction)

                            print(f"Found coordinates for {city_name}: Latitude = {latitude}, Longitude = {longitude}")
                            return latitude, longitude
                        else:
                            print(f"Coordinates not found for {city_name}")
                    except Exception as e:
                        print(f"Error parsing coordinates for {city_name}: {e}")
                else:
                    print(f"Could not find 'geo-dms' for {city_name}")
            else:
                print(f"No infobox found for {city_name}")
        else:
            print(f"Failed to retrieve Wikipedia page for {city_name}: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"Request failed for {city_name}: {e}")
    
    # If the page was not found, try appending "(יישוב)", "(כפר)", "(קיבוץ)", and "(מושב)" for Hebrew Wikipedia
    if lang == 'he':
        suffixes = ["(יישוב)", "(כפר)", "(קיבוץ)", "(מושב)"]
        for suffix in suffixes:
            print(f"Trying '{city_name} {suffix}' for {city_name}...")
            url = f"https://he.wikipedia.org/wiki/{city_name.replace(' ', '_')}_{suffix.replace(' ', '_')}"
            try:
                response = http.get(url)

                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Locate the infobox and search for the coordinates section
                    infobox = soup.find('table', class_='infobox')
                    if infobox:
                        coordinates_section = infobox.find('span', class_='geo-dms')
                        if coordinates_section:
                            try:
                                latitude_span = coordinates_section.find('span', class_='latitude')
                                longitude_span = coordinates_section.find('span', class_='longitude')
                                if latitude_span and longitude_span:
                                    lat_text = latitude_span.text
                                    lon_text = longitude_span.text

                                    lat_parts = lat_text.replace('°', ' ').replace("′", ' ').replace('″', ' ').split()
                                    lon_parts = lon_text.replace('°', ' ').replace("′", ' ').replace('″', ' ').split()

                                    lat_direction = lat_parts.pop()
                                    lon_direction = lon_parts.pop()

                                    latitude = dms_to_decimal(lat_parts, lat_direction)
                                    longitude = dms_to_decimal(lon_parts, lon_direction)

                                    print(f"Found coordinates for {city_name} {suffix}: Latitude = {latitude}, Longitude = {longitude}")
                                    return latitude, longitude
                                else:
                                    print(f"Coordinates not found for {city_name} {suffix}")
                            except Exception as e:
                                print(f"Error parsing coordinates for {city_name} {suffix}: {e}")
                        else:
                            print(f"Could not find 'geo-dms' for {city_name} {suffix}")
                    else:
                        print(f"No infobox found for {city_name} {suffix}")
                else:
                    print(f"Failed to retrieve Wikipedia page for {city_name} {suffix}: {response.status_code}")
            except requests.exceptions.RequestException as e:
                print(f"Request failed for {city_name} {suffix}: {e}")

    return None, None




def load_city_data(file_path='data.csv'):
    # Load the data from the CSV file into a DataFrame
    original_data = pd.read_csv(file_path)

    # Add columns if they don't exist
    if 'Latitude' not in original_data.columns:
        original_data['Latitude'] = None
    if 'Longitude' not in original_data.columns:
        original_data['Longitude'] = None
    if 'Alternate Names' not in original_data.columns:
        original_data['Alternate Names'] = None

    # Dictionary to hold the city data
    city_data_dict = {}

    # Process each row in the dataset
    for index, row in original_data.iterrows():
        city_name = row['שם יישוב']
        english_name = row['שם יישוב באנגלית']
        alternate_names = row.get('Alternate Names', '')
        population = row['סך הכל אוכלוסייה 2021']

        # Skip rows where both city name and English name are missing, or population is NaN or 0
        if pd.isna(city_name) and pd.isna(english_name):
            continue
        if pd.isna(population) or population == 0:
            continue

        # Check if latitude and longitude are present, otherwise fetch from Wikipedia
        if pd.notna(row['Latitude']) and pd.notna(row['Longitude']):
            latitude, longitude = row['Latitude'], row['Longitude']
        else:
            # Try fetching coordinates first using the English name, then Hebrew
            latitude, longitude = fetch_wikipedia_coordinates(english_name)
            if not latitude or not longitude:
                latitude, longitude = fetch_wikipedia_coordinates(city_name, lang='he')

        # If valid coordinates are found, store the data and update the DataFrame
        if latitude and longitude:
            city_data_dict[city_name] = {
                'Latitude': latitude,
                'Longitude': longitude,
                'Population': population,
                'alternate_names': alternate_names.split(',') if pd.notna(alternate_names) else []
            }
            # Update the DataFrame with the fetched coordinates
            original_data.at[index, 'Latitude'] = latitude
            original_data.at[index, 'Longitude'] = longitude
        else:
            print(f"Coordinates not found for {city_name}")

    # Save the progress back to the CSV
    original_data.to_csv(file_path, index=False)
    return city_data_dict
# If running the script manually
if __name__ == "__main__":
    city_data_dict = load_city_data()
    print("City data loaded successfully.")
