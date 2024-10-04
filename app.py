from flask import Flask, render_template, request, jsonify
import pandas as pd
import folium
import re
import sqlite3
import os
import math

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

# Function to reset the game state
def reset_game_state():
    global guessed_cities
    guessed_cities = []  # Reset the guessed cities list to an empty list
    # You may also want to reset other game-related variables here, if necessary

@app.route('/start_new_game', methods=['POST'])
def start_new_game():
    # Reset the game state when the player starts a new game
    reset_game_state()
    return jsonify({'status': 'new_game_started'})

# Insert a new leaderboard entry
def add_leaderboard_entry(player_name, cities_found, population_percentage, smallest_cities, time_taken, score):
    conn = sqlite3.connect('leaderboard.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO leaderboard (player_name, cities_found, population_percentage, smallest_cities, time_taken, score)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (player_name, cities_found, population_percentage, ','.join(smallest_cities), time_taken, score))
    conn.commit()
    conn.close()



def init_db():
    conn = sqlite3.connect('leaderboard.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS leaderboard (
            id INTEGER PRIMARY KEY,
            player_name TEXT NOT NULL,
            cities_found INTEGER NOT NULL,
            population_percentage REAL NOT NULL,
            smallest_cities TEXT NOT NULL,
            time_taken INTEGER NOT NULL,
            score REAL NOT NULL
        )
    ''')
    conn.commit()
    conn.close()




# Map Initialization
def initialize_map():
    game_map = folium.Map(location=[31.0461, 34.8516], zoom_start=7, tiles=None)
    folium.TileLayer('https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png',
                     attr='CartoDB', name='No Labels').add_to(game_map)

    # Add city markers to the map
    for index, row in original_data.iterrows():
        if pd.notna(row['Latitude']) and pd.notna(row['Longitude']):
            city_name = row['שם יישוב']
            population = row['סך הכל אוכלוסייה 2021']

            # Adjust circle size by population, using a log scale for better visualization
            radius = max(2, min(20, population / 1000))  # Ensure a minimum and maximum size

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
    initialize_map()  # Ensure the map is initialized
    return render_template('index.html', guessed_cities=guessed_cities)



# Helper function to normalize city names by removing special characters and converting to lowercase
def normalize_city_name(city_name):
    return re.sub(r'[^\w\s]', '', city_name).strip().lower()


@app.route('/submit_city', methods=['POST'])
def submit_city():
    city_name_input = request.json['city_name'].strip()

    # Normalize the user's input, handling special characters, hyphens, and י typos
    normalized_input = normalize_city_name_with_y_variation(city_name_input)

    # Check if the city was already guessed (main name or alternate names)
    for city in guessed_cities:
        # Check against the main guessed city name
        if normalized_input == normalize_city_name_with_y_variation(city['name']):
            return jsonify({'status': 'duplicate'})  # City already guessed
        
        # Check against alternate names for the guessed city
        if 'Alternate Names' in city and city['Alternate Names']:
            for alt_name in city['Alternate Names']:
                if normalized_input == normalize_city_name_with_y_variation(alt_name):
                    return jsonify({'status': 'duplicate'})  # City already guessed via alternate name

    city_found = False
    city_info = None
    matched_city_name = None  # Store the original city name even if an alternative is matched

    # Check if the city exists in the main city data or in its alternate names
    for city_name, city_data in city_data_dict.items():
        normalized_city_name = normalize_city_name_with_y_variation(city_name)

        # Check against the normalized main city name
        if normalized_input == normalized_city_name:
            city_found = True
            city_info = city_data
            matched_city_name = city_name  # The original city name is matched
            break

        # Check against alternate names (if they exist in city_data)
        if 'Alternate Names' in city_data:
            normalized_alternates = [normalize_city_name_with_y_variation(alt_name) for alt_name in city_data['Alternate Names']]
            if normalized_input in normalized_alternates:
                city_found = True
                city_info = city_data
                matched_city_name = city_name  # Match the original city name even if alternate name is used
                break

    # If the city is found and not already guessed, return success
    if city_found and matched_city_name not in [city['name'] for city in guessed_cities]:
        guessed_cities.append({
            'name': matched_city_name,  # Return the original city name
            'latitude': city_info['Latitude'],
            'longitude': city_info['Longitude'],
            'population': city_info['Population'],
            'Alternate Names': city_info.get('Alternate Names', [])  # Ensure alternate names are tracked
        })

        # Sort the guessed cities by population in descending order
        guessed_cities.sort(key=lambda city: city['population'], reverse=True)

        # Calculate the total guessed population
        guessed_population = sum(city['population'] for city in guessed_cities)

        # Calculate the total population of all cities in the dataset
        total_population = sum(city['Population'] for city in city_data_dict.values() if city['Population'] is not None)

        # Calculate the percentage of the guessed population
        population_percentage = (guessed_population / total_population) * 100 if total_population > 0 else 0

        return jsonify({
            'status': 'correct',
            'guessed_city': {
                'name': matched_city_name,  # Return the main city name, not the alternative
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


# Helper function to normalize city names by handling variations of י
def normalize_city_name_with_y_variation(city_name):
    # Normalize by removing special characters
    city_name = re.sub(r'[^\w\s]', '', city_name).strip().lower()

    # Handle variations in י: replace multiple יs with a single י, remove יs altogether
    city_name = re.sub(r'י{2,}', 'י', city_name)  # Replace multiple יs with a single י
    city_name = re.sub(r'י', '', city_name)  # Also allow no י

    return city_name


@app.route('/submit_leaderboard', methods=['POST'])
def submit_leaderboard():
    data = request.json
    player_name = data['player_name']
    time_taken = data['time_taken']

    # Sort the guessed cities by population to get the 5 smallest
    smallest_cities = sorted(guessed_cities, key=lambda x: x['population'])[:5]
    smallest_city_names = [city['name'] for city in smallest_cities]

    # Get the number of cities found and the population percentage
    cities_found = len(guessed_cities)
    guessed_population = sum(city['population'] for city in guessed_cities)
    total_population = sum(city['Population'] for city in city_data_dict.values() if city['Population'] is not None)
    population_percentage = (guessed_population / total_population) * 100 if total_population > 0 else 0

    # Calculate the player's score (you can adjust this formula)
    score = (cities_found * population_percentage) * math.tanh(200/time_taken)

    # Insert the data into the leaderboard
    add_leaderboard_entry(player_name, cities_found, population_percentage, smallest_city_names, time_taken, score)

    return jsonify({
        'status': 'success',
        'cities_found': cities_found,
        'smallest_cities': smallest_city_names,
        'population_percentage': population_percentage,
        'time_taken': time_taken,
    })

@app.route('/skip_leaderboard', methods=['POST'])
def skip_leaderboard():
    data = request.json
    time_taken = data['time_taken']  # We still need the time for the game summary

    # Sort the guessed cities by population to get the 5 smallest
    smallest_cities = sorted(guessed_cities, key=lambda x: x['population'])[:5]
    smallest_city_names = [city['name'] for city in smallest_cities]

    # Get the number of cities found and the population percentage
    cities_found = len(guessed_cities)
    guessed_population = sum(city['population'] for city in guessed_cities)
    total_population = sum(city['Population'] for city in city_data_dict.values() if city['Population'] is not None)
    population_percentage = (guessed_population / total_population) * 100 if total_population > 0 else 0

    # Return the game summary without saving the score to the leaderboard
    return jsonify({
        'status': 'success',
        'cities_found': cities_found,
        'smallest_cities': smallest_city_names,
        'population_percentage': population_percentage,
        'time_taken': time_taken,
    })


# Function to get the top 10 players from the leaderboard based on score
def get_top_leaderboard():
    conn = sqlite3.connect('leaderboard.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT player_name, cities_found, population_percentage, time_taken, score 
        FROM leaderboard
        ORDER BY score DESC
        LIMIT 10
    ''')
    leaderboard_entries = cursor.fetchall()
    conn.close()

    leaderboard = []
    for entry in leaderboard_entries:
        leaderboard.append({
            'player_name': entry[0],
            'cities_found': entry[1],
            'population_percentage': entry[2],
            'time_taken': entry[3],
            'score': entry[4]
        })

    return leaderboard


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


@app.route('/get_leaderboard', methods=['GET'])
def get_leaderboard():
    # Fetch the top 10 players from the leaderboard
    leaderboard = get_top_leaderboard()
    return jsonify({'leaderboard': leaderboard})


# Example of loading the data from the CSV
if __name__ == "__main__":
    city_data_dict = load_data_from_file('data.csv')
    init_db()
    reset_game_state()
    print("City data loaded successfully.")
    port = int(os.environ.get("PORT", 5000))  # Default to 5000 for local dev
    app.run(host='0.0.0.0', port=port)
    app.run(debug=True)
