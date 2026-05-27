"""Subset of major IATA airport coordinates. Production would load full dataset."""

AIRPORTS = {
    'LHR': (51.4700, -0.4543, 'London Heathrow'),
    'LGW': (51.1537, -0.1821, 'London Gatwick'),
    'STN': (51.8860, 0.2389, 'London Stansted'),
    'LCY': (51.5053, 0.0553, 'London City'),
    'MAN': (53.3537, -2.2750, 'Manchester'),
    'BHX': (52.4539, -1.7480, 'Birmingham'),
    'EDI': (55.9500, -3.3725, 'Edinburgh'),
    'GLA': (55.8642, -4.4331, 'Glasgow'),
    'DUB': (53.4213, -6.2701, 'Dublin'),
    'CDG': (49.0097, 2.5479, 'Paris CDG'),
    'AMS': (52.3105, 4.7683, 'Amsterdam Schiphol'),
    'FRA': (50.0379, 8.5622, 'Frankfurt'),
    'MUC': (48.3538, 11.7861, 'Munich'),
    'ZRH': (47.4647, 8.5492, 'Zurich'),
    'MAD': (40.4719, -3.5626, 'Madrid'),
    'BCN': (41.2974, 2.0833, 'Barcelona'),
    'JFK': (40.6413, -73.7781, 'New York JFK'),
    'EWR': (40.6895, -74.1745, 'Newark'),
    'LAX': (33.9416, -118.4085, 'Los Angeles'),
    'ORD': (41.9742, -87.9073, 'Chicago O\'Hare'),
    'SFO': (37.6213, -122.3790, 'San Francisco'),
    'BOS': (42.3656, -71.0096, 'Boston'),
    'DXB': (25.2532, 55.3657, 'Dubai'),
    'DOH': (25.2731, 51.6080, 'Doha'),
    'SIN': (1.3644, 103.9915, 'Singapore'),
    'HKG': (22.3080, 113.9185, 'Hong Kong'),
    'NRT': (35.7647, 140.3863, 'Tokyo Narita'),
    'HND': (35.5494, 139.7798, 'Tokyo Haneda'),
    'PEK': (40.0801, 116.5846, 'Beijing'),
    'SYD': (-33.9399, 151.1753, 'Sydney'),
    'BOM': (19.0896, 72.8656, 'Mumbai'),
    'DEL': (28.5562, 77.1000, 'Delhi'),
    'YYZ': (43.6777, -79.6248, 'Toronto'),
    'YVR': (49.1967, -123.1815, 'Vancouver'),
    'GRU': (-23.4356, -46.4731, 'São Paulo'),
    'JNB': (-26.1392, 28.2460, 'Johannesburg'),
}


def haversine_km(lat1, lon1, lat2, lon2):
    from math import radians, sin, cos, sqrt, asin
    R = 6371.0
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * R * asin(sqrt(a))


def airport_distance(origin_iata, dest_iata):
    o = AIRPORTS.get(origin_iata.upper()) if origin_iata else None
    d = AIRPORTS.get(dest_iata.upper()) if dest_iata else None
    if not o or not d:
        return None
    return round(haversine_km(o[0], o[1], d[0], d[1]), 2)
