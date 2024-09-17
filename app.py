from flask import Flask, render_template, request, jsonify
import pandas as pd
import folium
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import re

app = Flask(__name__)

# Load the dataset with existing coordinates and alternate names
city_data_path = 'data.csv'
original_data = pd.read_csv(city_data_path)

# Add Latitude, Longitude, and Alternate Names columns if they don't exist
if 'Latitude' not in original_data.columns:
    original_data['Latitude'] = None
if 'Longitude' not in original_data.columns:
    original_data['Longitude'] = None
if 'Alternate Names' not in original_data.columns:
    original_data['Alternate Names'] = None

# Initialize the city data dictionary
city_data_dict = {}

# Initialize guessed cities list to track which cities have been guessed during gameplay
guessed_cities = []

# Set up retry strategy for requests
retry_strategy = Retry(
    total=3,  # Retry 3 times
    status_forcelist=[429, 500, 502, 503, 504],  # Retry on these status codes
    allowed_methods=["GET"],  # Use 'allowed_methods' instead of 'method_whitelist'
    backoff_factor=1  # Exponential backoff factor
)
adapter = HTTPAdapter(max_retries=retry_strategy)
http = requests.Session()
http.mount("https://", adapter)
http.mount("http://", adapter)

# Function to convert DMS (Degrees, Minutes, Seconds) to decimal format
def dms_to_decimal(dms, direction):
    dms = list(map(float, dms)) + [0] * (3 - len(dms))  # Ensure 3 values: degrees, minutes, seconds
    degrees, minutes, seconds = dms
    decimal = degrees + minutes / 60 + seconds / 3600
    if direction in ['S', 'W']:  # South or West should be negative
        decimal *= -1
    return decimal

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

        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            infobox = soup.find('table', class_='infobox')
            if infobox:
                coordinates_section = infobox.find('span', class_='geo-dms')
                if coordinates_section:
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
            else:
                print(f"No infobox found for {city_name}")
        else:
            print(f"Failed to retrieve Wikipedia page for {city_name}: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"Request failed for {city_name}: {e}")

    return None, None

# Process each row in the dataset
def load_from_scratch():
    for index, row in original_data.iterrows():
        city_name = row['שם יישוב']  # Hebrew name for "City Name"
        english_name = row['שם יישוב באנגלית']  # English name for "City Name"
        alternate_names = row.get('Alternate Names', '')  # Get the alternate names if available
        population = row['סך הכל אוכלוסייה 2021']  # Population of the city

        if pd.isna(city_name) and pd.isna(english_name):
            print(f"Skipping row {index} due to missing city name")
            continue

        if pd.isna(population) or population == 0:
            print(f"Skipping {city_name} due to zero or missing population.")
            continue

        if pd.notna(row['Latitude']) and pd.notna(row['Longitude']):
            city_data_dict[city_name] = {
                'Latitude': row['Latitude'],
                'Longitude': row['Longitude'],
                'Population': population,
                'Alternate Names': alternate_names
            }
            continue

        latitude, longitude = fetch_wikipedia_coordinates(english_name)

        if not latitude or not longitude:
            latitude, longitude = fetch_wikipedia_coordinates(city_name, lang='he')

        if latitude and longitude:
            original_data.at[index, 'Longitude'] = longitude
            city_data_dict[city_name] = {
                'Latitude': latitude,
                'Longitude': longitude,
                'Population': population,
                'Alternate Names': alternate_names
            }

        original_data.to_csv(city_data_path, index=False)

# Map Initialization
def initialize_map():
    game_map = folium.Map(location=[31.0461, 34.8516], zoom_start=6, tiles=None)
    folium.TileLayer('https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png',
                     attr='CartoDB', name='No Labels').add_to(game_map)

    for index, row in original_data.iterrows():
        if pd.notna(row['Latitude']) and pd.notna(row['Longitude']):
            city_name = row['שם יישוב']
            population = row['סך הכל אוכלוסייה 2021']
            radius = max(2, min(20, population / 1000))

            folium.CircleMarker(
                location=[row['Latitude'], row['Longitude']],
                radius=radius,
                color='blue',
                fill=True,
                fill_opacity=0.7,
                tooltip=f"{city_name}: {population} residents"
            ).add_to(game_map)

    game_map.save('static/map.html')

@app.route('/')
def index():
    initialize_map()
    return render_template('index.html', guessed_cities=guessed_cities)

# Helper function to normalize city names by handling variations of י
def normalize_city_name_with_y_variation(city_name):
    city_name = re.sub(r'[^\w\s]', '', city_name).strip().lower()
    city_name = re.sub(r'י{2,}', 'י', city_name)  # Replace multiple יs with a single י
    city_name = re.sub(r'י', '', city_name)  # Also allow no י
    return city_name

@app.route('/submit_city', methods=['POST'])
def submit_city():
    city_name_input = request.json['city_name'].strip()
    normalized_input = normalize_city_name_with_y_variation(city_name_input)
    city_found = False
    city_info = None
    matched_city_name = None

    for city_name, city_data in city_data_dict.items():
        normalized_city_name = normalize_city_name_with_y_variation(city_name)

        if normalized_input == normalized_city_name:
            city_found = True
            city_info = city_data
            matched_city_name = city_name
            break

        if 'Alternate Names' in city_data:
            normalized_alternates = [normalize_city_name_with_y_variation(alt_name) for alt_name in city_data['Alternate Names']]
            if normalized_input in normalized_alternates:
                city_found = True
                city_info = city_data
                matched_city_name = city_name
                break

    if city_found and matched_city_name not in [city['name'] for city in guessed_cities]:
        guessed_cities.append({
            'name': matched_city_name,
            'latitude': city_info['Latitude'],
            'longitude': city_info['Longitude'],
            'population': city_info['Population']
        })

        guessed_cities.sort(key=lambda city: city['population'], reverse=True)
        guessed_population = sum(city['population'] for city in guessed_cities)
        total_population = sum(city['Population'] for city in city_data_dict.values() if city['Population'] is not None)
        population_percentage = (guessed_population / total_population) * 100 if total_population > 0 else 0

        return jsonify({
            'status': 'correct',
            'guessed_city': {
                'name': matched_city_name,
                'latitude': city_info['Latitude'],
                'longitude': city_info['Longitude'],
                'population': city_info['Population']
            },
            'guessed_cities': guessed_cities,
            'guessed_population': guessed_population,
            'total_population': total_population,
            'population_percentage': population_percentage
        })
    else:
        return jsonify({'status': 'incorrect', 'guessed_cities': guessed_cities})

# Load data from file
def load_data_from_file(file_path='data.csv'):
    # Load the data from the CSV file into a DataFrame
    original_data = pd.read_csv(file_path)
    
    # Initialize a dictionary to store the city data
    city_data_dict = {}

    # Process each row in the dataset and load the necessary columns
    for index, row in original_data.iterrows():
        city_name = row['שם יישוב']  # Hebrew name for "City Name"
        population = row['סך הכל אוכלוסייה 2021']  # Population of the city

        # Skip cities with no population or zero population
        if pd.isna(population) or population == 0:
            print(f"Skipping {city_name} due to missing or zero population.")
            continue

        alternate_names = row.get('Alternate Names', '')  # Alternate names if available

        # Directly assign latitude and longitude (assuming they exist as you stated)
        city_data_dict[city_name] = {
            'Latitude': row['Latitude'],
            'Longitude': row['Longitude'],
            'Population': population,
            'Alternate Names': alternate_names.split(',') if pd.notna(alternate_names) else []
        }

    return city_data_dict

# Initialize city data when the app starts
city_data_dict = load_data_from_file(city_data_path)

# Ensure the app binds to the correct port for deployment on Render or similar platforms
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))  # Get the port from the environment variable or default to 5000
    app.run(host="0.0.0.0", port=port, debug=True)

