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

# Outlier detection thresholds
MAX_WIND_GUST_KMH = 80.0  # Max reasonable wind gust for this location
MAX_PRECIP_DELTA_MM = 5.0  # Max mm accumulation change per 5-minute interval (= 60 mm/h max rate)
MAX_PRECIP_RATE_MMH = 60.0  # Max reasonable precipitation rate mm/h

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


def convert_daily_precip_to_cumulative_rain(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    Convert daily-resetting Precip_Accum_mm to cumulative rain_mm.
    
    The CSV contains Precip_Accum_mm that resets daily at midnight (00:00).
    InfluxDB stores rain_mm as a continuous historical value that never resets.
    
    Algorithm:
    - Track running offset that accumulates when resets are detected
    - When current_accum < previous_accum: reset detected, add previous_max to offset
    - rain_mm = offset + current_accum
    
    Returns: rows with Precip_Accum_mm converted to cumulative values
    """
    converted_rows = []
    running_offset = 0.0
    prev_accum = None
    daily_max = 0.0
    
    for row in rows:
        converted_row = row.copy()
        
        try:
            current_accum = parse_decimal(row['Precip_Accum_mm'])
        except (ValueError, KeyError):
            converted_rows.append(converted_row)
            continue
        
        if prev_accum is not None:
            if current_accum < prev_accum:
                # Daily reset detected: accumulation went backwards
                # Add the previous day's maximum to the running offset
                running_offset += daily_max
                daily_max = current_accum
            else:
                # Normal case: accumulation increased or stayed flat
                daily_max = max(daily_max, current_accum)
        else:
            # First row: initialize with current value
            daily_max = current_accum
        
        # Convert to cumulative rain_mm
        cumulative_rain = running_offset + current_accum
        converted_row['Precip_Accum_mm'] = str(round(cumulative_rain, 2))
        
        prev_accum = current_accum
        converted_rows.append(converted_row)
    
    return converted_rows


def detect_and_fix_outliers(rows: List[Dict[str, str]], show_fixes: bool = False) -> Tuple[List[Dict[str, str]], dict, List[dict]]:
    """
    Detect and fix outliers in the CSV data.

    Wind gust outliers: Replace with neighbor average
    Precipitation outliers: Cap accumulation delta, recalculate rate from accumulation

    Returns: (fixed_rows, stats_dict, fixes_list)
    """
    stats = {
        'wind_gust_outliers': 0,
        'precip_accum_outliers': 0,
        'precip_rate_recalculated': 0,
    }
    fixes = []  # List to store detailed fix information

    fixed_rows = []
    prev_accum_original = None  # Track original values to detect flat readings
    prev_accum_corrected = None  # Track corrected values for output
    prev_time = None
    recent_deltas = []  # Track last N deltas for trend detection
    TREND_WINDOW = 5  # Number of intervals to consider for trend
    SPIKE_MULTIPLIER = 6.0  # Current delta must be > this * recent_avg to be outlier
    CALM_THRESHOLD = 10.0  # Wind gust values below this are considered "calm"

    for i, row in enumerate(rows):
        fixed_row = row.copy()

        # Parse current values
        try:
            wind_avg = parse_decimal(row['Speed_kmh'])
            wind_gust = parse_decimal(row['Gust_kmh'])
            precip_accum = parse_decimal(row['Precip_Accum_mm'])
            precip_rate = parse_decimal(row['Precip_Rate_mm'])
            current_time = parse_timestamp(row['Date'], row['Time'])
        except (ValueError, KeyError):
            fixed_rows.append(fixed_row)
            continue

        # === WIND GUST OUTLIER DETECTION ===
        # Outlier if:
        # 1. Gust > absolute threshold (80 km/h) with low wind, OR
        # 2. Gust is a sudden spike compared to neighbors (spike detection)
        is_gust_outlier = False

        # Check absolute threshold
        if wind_gust > MAX_WIND_GUST_KMH:
            if wind_avg < 1.0 or wind_gust > wind_avg * 10:
                is_gust_outlier = True

        # Check for sudden spikes by comparing to calm neighbors (search for non-spike values)
        if not is_gust_outlier and wind_gust > 15.0:
            # Search for calm values before and after (skip potential consecutive spikes)
            prev_calm = None
            next_calm = None

            # Search backwards for a calm value
            for j in range(1, min(6, i + 1)):
                try:
                    candidate = parse_decimal(rows[i-j]['Gust_kmh'])
                    if candidate < CALM_THRESHOLD:
                        prev_calm = candidate
                        break
                except (ValueError, KeyError):
                    pass

            # Search forwards for a calm value
            for j in range(1, min(6, len(rows) - i)):
                try:
                    candidate = parse_decimal(rows[i+j]['Gust_kmh'])
                    if candidate < CALM_THRESHOLD:
                        next_calm = candidate
                        break
                except (ValueError, KeyError):
                    pass

            # If we found calm values on both sides, and current is a spike
            if prev_calm is not None and next_calm is not None:
                calm_avg = (prev_calm + next_calm) / 2
                # If current gust is >5x the calm average, it's an outlier
                if wind_gust > calm_avg * 5 and calm_avg < 5.0:
                    is_gust_outlier = True

        if is_gust_outlier:
            # Get average of previous N valid (already corrected) values
            # Use fixed_rows which contains corrected values for previous rows
            prev_valid_gusts = []
            NUM_PREV_VALUES = 5  # Average last N valid values

            for j in range(1, min(11, i + 1)):
                try:
                    # Use fixed_rows for corrected values from previous iterations
                    candidate = parse_decimal(fixed_rows[i-j]['Gust_kmh'])
                    if candidate < CALM_THRESHOLD:  # Only use calm values
                        prev_valid_gusts.append(candidate)
                        if len(prev_valid_gusts) >= NUM_PREV_VALUES:
                            break
                except (ValueError, KeyError, IndexError):
                    pass

            # Calculate replacement value from average of previous calm values
            if prev_valid_gusts:
                new_gust = round(sum(prev_valid_gusts) / len(prev_valid_gusts), 2)
            else:
                new_gust = wind_avg  # Fallback to average wind speed

            fixed_row['Gust_kmh'] = str(new_gust)
            stats['wind_gust_outliers'] += 1
            if show_fixes:
                fixes.append({
                    'type': 'wind_gust',
                    'row': i + 2,  # CSV row number (1-indexed + header)
                    'date': row.get('Date', ''),
                    'time': row.get('Time', ''),
                    'original': wind_gust,
                    'corrected': new_gust,
                    'wind_avg': wind_avg,
                    'method': 'neighbor_average'
                })

        # === PRECIPITATION ACCUMULATION OUTLIER DETECTION ===
        # Key insight: We need to track ORIGINAL deltas to detect flat readings (no rain)
        # vs actual rain. If original values are flat (57.4, 57.4, 57.4), no rain fell.
        # We only cap the first spike, then subsequent flat readings get delta=0.
        #
        # Trend-aware detection: Only flag as outlier if delta exceeds BOTH:
        # 1. The absolute threshold (MAX_PRECIP_DELTA_MM)
        # 2. Recent average * SPIKE_MULTIPLIER (to allow gradual increases during storms)

        corrected_accum = precip_accum  # Start with original value

        if prev_accum_original is not None and prev_time is not None:
            # Calculate delta from ORIGINAL values to detect actual rain vs flat readings
            original_delta = precip_accum - prev_accum_original
            time_delta_minutes = (current_time - prev_time) / (1_000_000_000 * 60)

            if time_delta_minutes > 0:
                # Scale max delta by time interval (default threshold is for 5 min)
                max_delta_for_interval = MAX_PRECIP_DELTA_MM * (time_delta_minutes / 5.0)

                # Calculate trend-based threshold
                is_outlier = False
                if original_delta > max_delta_for_interval:
                    # Check if this breaks the recent trend
                    if len(recent_deltas) >= 2:
                        # Get positive deltas only (ignore flat/reset periods)
                        positive_deltas = [d for d in recent_deltas if d > 0]
                        if positive_deltas:
                            recent_avg = sum(positive_deltas) / len(positive_deltas)
                            # Only flag as outlier if it's a sudden spike vs recent trend
                            # A gradual increase (1mm -> 2mm -> 3mm -> 5mm) is allowed
                            if original_delta > recent_avg * SPIKE_MULTIPLIER:
                                is_outlier = True
                        else:
                            # No recent rain, so any spike above threshold is suspicious
                            is_outlier = True
                    else:
                        # Not enough history - use absolute threshold only
                        is_outlier = True

                if is_outlier:
                    # This is a sensor error spike - ignore it (delta = 0)
                    # Keep the previous corrected accumulation unchanged
                    corrected_accum = prev_accum_corrected
                    fixed_row['Precip_Accum_mm'] = str(round(corrected_accum, 2))
                    stats['precip_accum_outliers'] += 1
                    if show_fixes:
                        recent_avg_str = ""
                        positive_deltas = [d for d in recent_deltas if d > 0]
                        if positive_deltas:
                            recent_avg_str = f", recent_avg: {sum(positive_deltas)/len(positive_deltas):.2f}"
                        fixes.append({
                            'type': 'precip_accum',
                            'row': i + 2,
                            'date': row.get('Date', ''),
                            'time': row.get('Time', ''),
                            'original': precip_accum,
                            'corrected': round(corrected_accum, 2),
                            'delta_original': round(original_delta, 2),
                            'delta_corrected': 0.0,
                            'method': 'spike_zeroed'
                        })
                    # DON'T add capped delta to recent history - keep using pre-outlier trend
                    # This ensures consecutive outliers are all caught
                elif original_delta >= 0:
                    # Normal rain or flat reading - apply same delta to corrected series
                    corrected_accum = prev_accum_corrected + original_delta
                    fixed_row['Precip_Accum_mm'] = str(round(corrected_accum, 2))
                    # Add to recent history
                    recent_deltas.append(original_delta)
                elif original_delta < 0:
                    # Accumulation reset (new day)
                    corrected_accum = precip_accum  # Start fresh with new value
                    fixed_row['Precip_Accum_mm'] = str(round(corrected_accum, 2))
                    # Clear recent history on reset
                    recent_deltas.clear()

                # Keep only last N deltas
                if len(recent_deltas) > TREND_WINDOW:
                    recent_deltas.pop(0)

                # Only recalculate rate if we modified the accumulation (outlier detected)
                # For normal rows, keep the original sensor rate
                if is_outlier:
                    corrected_delta = corrected_accum - prev_accum_corrected
                    time_delta_hours = time_delta_minutes / 60.0
                    if time_delta_hours > 0:
                        original_rate = parse_decimal(row['Precip_Rate_mm'])
                        calculated_rate = round(corrected_delta / time_delta_hours, 2)
                        calculated_rate = max(0, min(calculated_rate, MAX_PRECIP_RATE_MMH))
                        fixed_row['Precip_Rate_mm'] = str(calculated_rate)
                        stats['precip_rate_recalculated'] += 1
                        if show_fixes and abs(original_rate - calculated_rate) > 0.1:
                            fixes.append({
                                'type': 'precip_rate',
                                'row': i + 2,
                                'date': row.get('Date', ''),
                                'time': row.get('Time', ''),
                                'original': original_rate,
                                'corrected': calculated_rate,
                                'method': 'recalculated_from_accum'
                            })

        # Update previous values for next iteration
        prev_accum_original = precip_accum  # Always track original
        prev_accum_corrected = parse_decimal(fixed_row['Precip_Accum_mm'])  # Track corrected
        prev_time = current_time

        fixed_rows.append(fixed_row)

    return fixed_rows, stats, fixes


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
    rain_mm = parse_decimal(row['Precip_Accum_mm'])  # Already converted to cumulative by convert_daily_precip_to_cumulative_rain()
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

    # Fields - simplified rain architecture (16 fields)
    # Removed fields: daily_rain_current, daily_rain_total, precipitation_rate_mm_h
    # All rain calculations now done in Grafana using rain_mm
    fields = {
        # Raw sensor fields
        'temperature_C': temp_c,
        'humidity': humidity,
        'wind_avg_km_h': wind_avg_kmh,
        'wind_max_km_h': wind_max_kmh,
        'wind_dir_deg': wind_dir,
        'rain_mm': rain_mm,  # Cumulative historical rain (converted from daily-resetting precip_accum)
        'light_lux': light_lux,
        'uvi': uvi,
        'battery_ok': 1.0,
        'pressure_hPa': pressure_hpa,

        # Derived fields
        'dew_point_C': dew_point_c,
        'feels_like_C': feels_like_c,
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

    try:
        query_api = client.query_api()
        result = query_api.query(query, org=INFLUXDB_ORG)

        existing = set()
        for table in result:
            for record in table.records:
                try:
                    # Convert to nanoseconds
                    ts = record.get_time()
                    if ts is not None:
                        existing.add(int(ts.timestamp() * 1_000_000_000))
                except (KeyError, AttributeError):
                    # Skip records without _time or if get_time() fails
                    continue

        return existing
    except Exception as e:
        # If query fails (e.g., bucket is empty or connection issue), return empty set
        print(f"Warning: Could not query existing timestamps: {e}")
        return set()

def import_csv(csv_file_path: str, dry_run: bool = False, show_outlier_fixes: bool = False, overwrite: bool = False):
    """Import CSV file into InfluxDB"""

    print(f"Starting CSV import from: {csv_file_path}")
    print(f"Dry run mode: {dry_run}")
    print(f"Overwrite existing: {overwrite}")
    print(f"Show outlier fixes: {show_outlier_fixes}")
    print(f"Timezone: {TIMEZONE}")
    print(f"InfluxDB: {INFLUXDB_URL}")
    print(f"Organization: {INFLUXDB_ORG}")
    print(f"Bucket: {INFLUXDB_BUCKET}")
    print("-" * 60)

    # Parse CSV file
    raw_rows = []
    with open(csv_file_path, 'r', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile, delimiter=',')
        raw_rows = list(reader)

    print(f"Read {len(raw_rows)} rows from CSV")

    # Convert daily-resetting precip_accum to cumulative rain_mm
    print("Converting daily precipitation accumulation to cumulative rain_mm...")
    raw_rows = convert_daily_precip_to_cumulative_rain(raw_rows)

    # Detect and fix outliers
    print("Detecting and fixing outliers...")
    fixed_rows, outlier_stats, outlier_fixes = detect_and_fix_outliers(raw_rows, show_fixes=show_outlier_fixes)

    if outlier_stats['wind_gust_outliers'] > 0:
        print(f"  - Fixed {outlier_stats['wind_gust_outliers']} wind gust outliers (neighbor average)")
    if outlier_stats['precip_accum_outliers'] > 0:
        print(f"  - Fixed {outlier_stats['precip_accum_outliers']} precipitation accumulation outliers (spike zeroed)")
    if outlier_stats['precip_rate_recalculated'] > 0:
        print(f"  - Recalculated {outlier_stats['precip_rate_recalculated']} precipitation rates from accumulation")

    # Show detailed outlier fixes if requested
    if show_outlier_fixes and outlier_fixes:
        print("\n" + "=" * 60)
        print("DETAILED OUTLIER FIXES:")
        print("=" * 60)

        # Group fixes by type
        wind_fixes = [f for f in outlier_fixes if f['type'] == 'wind_gust']
        accum_fixes = [f for f in outlier_fixes if f['type'] == 'precip_accum']
        rate_fixes = [f for f in outlier_fixes if f['type'] == 'precip_rate']

        if wind_fixes:
            print(f"\n--- Wind Gust Outliers ({len(wind_fixes)}) ---")
            for fix in wind_fixes:
                print(f"  Row {fix['row']:5d} | {fix['date']} {fix['time']:8s} | "
                      f"Gust: {fix['original']:6.2f} -> {fix['corrected']:6.2f} km/h "
                      f"(avg wind: {fix['wind_avg']:.2f} km/h)")

        if accum_fixes:
            print(f"\n--- Precipitation Accumulation Outliers ({len(accum_fixes)}) ---")
            for fix in accum_fixes:
                print(f"  Row {fix['row']:5d} | {fix['date']} {fix['time']:8s} | "
                      f"Accum: {fix['original']:6.2f} -> {fix['corrected']:6.2f} mm "
                      f"(delta: {fix['delta_original']:.2f} -> {fix.get('delta_corrected', 0.0):.2f} mm)")

        if rate_fixes:
            print(f"\n--- Precipitation Rate Corrections ({len(rate_fixes)}) ---")
            for fix in rate_fixes:
                print(f"  Row {fix['row']:5d} | {fix['date']} {fix['time']:8s} | "
                      f"Rate: {fix['original']:6.2f} -> {fix['corrected']:6.2f} mm/h")

        print("=" * 60 + "\n")

    # Parse fixed rows into data points
    data_points = []
    for row_num, row in enumerate(fixed_rows, start=2):  # Start at 2 (header is row 1)
        try:
            timestamp_ns, tags, fields = parse_csv_row(row)
            data_points.append((timestamp_ns, tags, fields))
        except Exception as e:
            print(f"ERROR parsing row {row_num}: {e}")
            print(f"Row data: {row}")
            continue

    print(f"Parsed {len(data_points)} data points")

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

    # Check for existing timestamps (unless overwrite mode)
    if overwrite:
        print("Overwrite mode: will replace existing data points")
        new_data_points = data_points
        skipped_count = 0
        overwrite_count = 0  # We don't know exact count without checking
    else:
        print("Checking for existing data in InfluxDB...")
        existing_timestamps = get_existing_timestamps(client, min_ts, max_ts + 1)
        print(f"Found {len(existing_timestamps)} existing timestamps in range")

        # Filter out existing data
        new_data_points = [dp for dp in data_points if dp[0] not in existing_timestamps]
        skipped_count = len(data_points) - len(new_data_points)

        print(f"Skipping {skipped_count} existing data points")

    print(f"Importing {len(new_data_points)} data points")
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
        print("Usage: python import_csv.py <csv_file> [options]")
        print("")
        print("Options:")
        print("  --dry-run             Preview import without writing to database")
        print("  --overwrite           Overwrite existing data points (default: skip existing)")
        print("  --show-outlier-fixes  Show detailed information about each outlier correction")
        print("")
        print("Example:")
        print("  python import_csv.py weather_data.csv --dry-run")
        print("  python import_csv.py weather_data.csv --overwrite")
        print("  python import_csv.py weather_data.csv --show-outlier-fixes")
        print("  python import_csv.py weather_data.csv --dry-run --show-outlier-fixes")
        sys.exit(1)

    csv_file = sys.argv[1]
    dry_run = '--dry-run' in sys.argv
    overwrite = '--overwrite' in sys.argv
    show_outlier_fixes = '--show-outlier-fixes' in sys.argv

    if not os.path.exists(csv_file):
        print(f"ERROR: File not found: {csv_file}")
        sys.exit(1)

    if not INFLUXDB_TOKEN:
        print("ERROR: INFLUXDB_ADMIN_TOKEN not set in .env file")
        sys.exit(1)

    import_csv(csv_file, dry_run=dry_run, show_outlier_fixes=show_outlier_fixes, overwrite=overwrite)

if __name__ == '__main__':
    main()
