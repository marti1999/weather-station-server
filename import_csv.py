#!/usr/bin/env python3
"""
CSV Import Script for Weather Station Data
Imports historical weather data from CSV into InfluxDB
"""

import csv
import sys
import os
from datetime import datetime
from typing import Dict, List, Tuple, Set
import pytz
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# InfluxDB Configuration
INFLUXDB_URL = os.getenv('INFLUXDB_URL', 'http://localhost:8086')
INFLUXDB_TOKEN = os.getenv('INFLUXDB_ADMIN_TOKEN')
INFLUXDB_ORG = os.getenv('INFLUXDB_ORG', 'weather')
INFLUXDB_BUCKET = os.getenv('INFLUXDB_BUCKET', 'weather_data')
TIMEZONE = os.getenv('TZ', 'Europe/Madrid')

# Constants
MEASUREMENT = 'rtl433'
MADRID_TZ = pytz.timezone(TIMEZONE)
UTC_TZ = pytz.UTC

# Compass to degrees mapping
COMPASS_TO_DEGREES = {
    'N': 0, 'NORTH': 0,
    'NNE': 22.5,
    'NE': 45, 'NORTHEAST': 45,
    'ENE': 67.5,
    'E': 90, 'EAST': 90,
    'ESE': 112.5,
    'SE': 135, 'SOUTHEAST': 135,
    'SSE': 157.5,
    'S': 180, 'SOUTH': 180,
    'SSW': 202.5,
    'SW': 225, 'SOUTHWEST': 225,
    'WSW': 247.5,
    'W': 270, 'WEST': 270,
    'WNW': 292.5,
    'NW': 315, 'NORTHWEST': 315,
    'NNW': 337.5
}

def parse_decimal(value: str) -> float:
    """Convert decimal string to float (handles both comma and dot)"""
    # Handle both European (comma) and US (dot) decimal separators
    if ',' in value and '.' not in value:
        # European format: 25,17
        return float(value.replace(',', '.'))
    else:
        # US/International format: 25.17
        return float(value)

def compass_to_degrees(direction: str) -> float:
    """Convert compass direction to degrees"""
    direction = direction.strip().upper()
    return float(COMPASS_TO_DEGREES.get(direction, 0))

def parse_timestamp(date_str: str, time_str: str) -> int:
    """Parse CSV date/time to UTC timestamp in nanoseconds"""
    datetime_str = f"{date_str} {time_str}"
    dt_naive = datetime.strptime(datetime_str, "%Y/%m/%d %I:%M %p")
    dt_madrid = MADRID_TZ.localize(dt_naive)
    dt_utc = dt_madrid.astimezone(UTC_TZ)
    return int(dt_utc.timestamp() * 1_000_000_000)

def calculate_wind_chill(temp_c: float, wind_kmh: float) -> float:
    """Calculate wind chill temperature (Environment Canada formula)"""
    if temp_c < 10 and wind_kmh > 4.8:
        wc = (13.12 + 0.6215 * temp_c - 11.37 * (wind_kmh ** 0.16) +
              0.3965 * temp_c * (wind_kmh ** 0.16))
        return round(wc, 2)
    return temp_c

def calculate_heat_index(temp_c: float, humidity: float) -> float:
    """Calculate heat index (Rothfusz regression, Celsius)"""
    if temp_c > 27 and humidity > 40:
        c1, c2, c3 = -8.78469475556, 1.61139411, 2.33854883889
        c4, c5, c6 = -0.14611605, -0.012308094, -0.0164248277778
        c7, c8, c9 = 0.002211732, 0.00072546, -0.000003582

        T = temp_c
        RH = humidity

        hi = (c1 + c2*T + c3*RH + c4*T*RH + c5*T*T + c6*RH*RH +
              c7*T*T*RH + c8*T*RH*RH + c9*T*T*RH*RH)
        return round(hi, 2)
    return temp_c

def calculate_feels_like(temp_c: float, humidity: float, wind_kmh: float) -> float:
    """Calculate feels-like temperature"""
    if temp_c < 10 and wind_kmh > 4.8:
        return calculate_wind_chill(temp_c, wind_kmh)
    elif temp_c > 27 and humidity > 40:
        return calculate_heat_index(temp_c, humidity)
    else:
        return temp_c

def calculate_beaufort(wind_kmh: float) -> int:
    """Calculate Beaufort wind scale from km/h"""
    if wind_kmh < 1: return 0
    elif wind_kmh < 5: return 1
    elif wind_kmh < 11: return 2
    elif wind_kmh < 19: return 3
    elif wind_kmh < 28: return 4
    elif wind_kmh < 38: return 5
    elif wind_kmh < 49: return 6
    elif wind_kmh < 61: return 7
    elif wind_kmh < 74: return 8
    elif wind_kmh < 88: return 9
    elif wind_kmh < 102: return 10
    elif wind_kmh < 117: return 11
    else: return 12

def calculate_uv_risk(uvi: float) -> int:
    """Calculate UV risk level from UV index"""
    if uvi < 3: return 0  # Low
    elif uvi < 6: return 1  # Moderate
    elif uvi < 8: return 2  # High
    elif uvi < 11: return 3  # Very High
    else: return 4  # Extreme

def calculate_light_lux(solar_radiation_w_m2: float) -> float:
    """Calculate light_lux from solar radiation"""
    return round(solar_radiation_w_m2 * 126.7, 2)

def parse_csv_row(row: Dict[str, str]) -> Tuple[int, Dict[str, any], Dict[str, float]]:
    """Parse a CSV row and return (timestamp, tags, fields)"""

    # Parse timestamp
    timestamp_ns = parse_timestamp(row['Date'], row['Time'])

    # Parse raw values with decimal conversion
    temp_c = parse_decimal(row['Temperature_C'])
    dew_point_c = parse_decimal(row['Dew_Point_C'])
    humidity = parse_decimal(row['Humidity_%'])
    wind_dir = compass_to_degrees(row['Wind'])
    wind_avg_kmh = parse_decimal(row['Speed_kmh'])
    wind_max_kmh = parse_decimal(row['Gust_kmh'])
    pressure_hpa = parse_decimal(row['Pressure_hPa'])
    precip_rate_mmh = parse_decimal(row['Precip_Rate_mm'])
    daily_rain_current = parse_decimal(row['Precip_Accum_mm'])
    uvi = parse_decimal(row['UV'])
    solar_radiation = parse_decimal(row['Solar_w/m2'])

    # Calculate derived fields
    feels_like_c = calculate_feels_like(temp_c, humidity, wind_avg_kmh)
    wind_beaufort = calculate_beaufort(wind_avg_kmh)
    uv_risk = calculate_uv_risk(uvi)
    light_lux = calculate_light_lux(solar_radiation)

    # Tags (constant for CSV imports)
    tags = {
        'model': 'CSV_Import',
        'id': 'imported',
        'channel': '0',
        'battery_ok': '1',
        'mic': 'CHECKSUM',
        'mod': 'CSV',
        'topic': 'import/csv',
        'host': 'import-script'
    }

    # Fields (19 total)
    fields = {
        # Raw sensor fields
        'temperature_C': temp_c,
        'humidity': humidity,
        'wind_avg_km_h': wind_avg_kmh,
        'wind_max_km_h': wind_max_kmh,
        'wind_dir_deg': wind_dir,
        'rain_mm': daily_rain_current,  # Use daily as cumulative for CSV
        'light_lux': light_lux,
        'uvi': uvi,
        'battery_ok': 1.0,
        'pressure_hPa': pressure_hpa,  # NEW FIELD

        # Derived fields
        'dew_point_C': dew_point_c,
        'feels_like_C': feels_like_c,
        'daily_rain_current': daily_rain_current,
        'daily_rain_total': 0.0,  # Cannot determine from CSV
        'precipitation_rate_mm_h': precip_rate_mmh,
        'solar_radiation_w_m2': solar_radiation,
        'wind_speed_beaufort': wind_beaufort,
        'uv_risk_level': uv_risk,
        'battery_status_pct': 100.0
    }

    return timestamp_ns, tags, fields

def get_existing_timestamps(client: InfluxDBClient, start_ns: int, end_ns: int) -> Set[int]:
    """Query InfluxDB for existing timestamps in range"""
    query = f'''
    from(bucket: "{INFLUXDB_BUCKET}")
      |> range(start: {start_ns}, stop: {end_ns})
      |> filter(fn: (r) => r._measurement == "{MEASUREMENT}")
      |> keep(columns: ["_time"])
      |> group()
      |> distinct(column: "_time")
    '''

    query_api = client.query_api()
    result = query_api.query(query, org=INFLUXDB_ORG)

    existing = set()
    for table in result:
        for record in table.records:
            # Convert to nanoseconds
            existing.add(int(record.get_time().timestamp() * 1_000_000_000))

    return existing

def import_csv(csv_file_path: str, dry_run: bool = False):
    """Import CSV file into InfluxDB"""

    print(f"Starting CSV import from: {csv_file_path}")
    print(f"Dry run mode: {dry_run}")
    print(f"Timezone: {TIMEZONE}")
    print(f"InfluxDB: {INFLUXDB_URL}")
    print(f"Organization: {INFLUXDB_ORG}")
    print(f"Bucket: {INFLUXDB_BUCKET}")
    print("-" * 60)

    # Parse CSV file
    data_points = []
    with open(csv_file_path, 'r', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile, delimiter=',')

        for row_num, row in enumerate(reader, start=2):  # Start at 2 (header is row 1)
            try:
                timestamp_ns, tags, fields = parse_csv_row(row)
                data_points.append((timestamp_ns, tags, fields))
            except Exception as e:
                print(f"ERROR parsing row {row_num}: {e}")
                print(f"Row data: {row}")
                continue

    print(f"Parsed {len(data_points)} rows from CSV")

    if len(data_points) == 0:
        print("No data to import. Exiting.")
        return

    # Get timestamp range
    timestamps = [dp[0] for dp in data_points]
    min_ts = min(timestamps)
    max_ts = max(timestamps)

    min_dt = datetime.fromtimestamp(min_ts / 1_000_000_000, UTC_TZ)
    max_dt = datetime.fromtimestamp(max_ts / 1_000_000_000, UTC_TZ)

    print(f"Date range: {min_dt} to {max_dt}")
    print("-" * 60)

    # Connect to InfluxDB
    client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)

    # Check for existing timestamps
    print("Checking for existing data in InfluxDB...")
    existing_timestamps = get_existing_timestamps(client, min_ts, max_ts + 1)
    print(f"Found {len(existing_timestamps)} existing timestamps in range")

    # Filter out existing data
    new_data_points = [dp for dp in data_points if dp[0] not in existing_timestamps]
    skipped_count = len(data_points) - len(new_data_points)

    print(f"Skipping {skipped_count} existing data points")
    print(f"Importing {len(new_data_points)} new data points")
    print("-" * 60)

    if dry_run:
        print("DRY RUN - No data will be written")
        if len(new_data_points) > 0:
            print("\nSample of first data point to be imported:")
            ts, tags, fields = new_data_points[0]
            dt = datetime.fromtimestamp(ts / 1_000_000_000, UTC_TZ)
            print(f"  Timestamp: {dt}")
            print(f"  Tags: {tags}")
            print(f"  Fields ({len(fields)}):")
            for key, value in sorted(fields.items()):
                print(f"    {key}: {value}")
        client.close()
        return

    # Write data to InfluxDB
    write_api = client.write_api(write_options=SYNCHRONOUS)

    batch_size = 1000
    total_written = 0

    for i in range(0, len(new_data_points), batch_size):
        batch = new_data_points[i:i+batch_size]
        points = []

        for timestamp_ns, tags, fields in batch:
            point = Point(MEASUREMENT)

            # Add tags
            for tag_key, tag_value in tags.items():
                point.tag(tag_key, tag_value)

            # Add fields
            for field_key, field_value in fields.items():
                point.field(field_key, field_value)

            # Set timestamp
            point.time(timestamp_ns, WritePrecision.NS)

            points.append(point)

        # Write batch
        write_api.write(bucket=INFLUXDB_BUCKET, org=INFLUXDB_ORG, record=points)
        total_written += len(points)

        print(f"Progress: {total_written}/{len(new_data_points)} data points written", end='\r')

    print(f"\nImport complete: {total_written} data points written")

    # Close connection
    write_api.close()
    client.close()

def main():
    if len(sys.argv) < 2:
        print("Usage: python import_csv.py <csv_file> [--dry-run]")
        print("")
        print("Example:")
        print("  python import_csv.py weather_data.csv --dry-run")
        print("  python import_csv.py weather_data.csv")
        sys.exit(1)

    csv_file = sys.argv[1]
    dry_run = '--dry-run' in sys.argv

    if not os.path.exists(csv_file):
        print(f"ERROR: File not found: {csv_file}")
        sys.exit(1)

    if not INFLUXDB_TOKEN:
        print("ERROR: INFLUXDB_ADMIN_TOKEN not set in .env file")
        sys.exit(1)

    import_csv(csv_file, dry_run=dry_run)

if __name__ == '__main__':
    main()
