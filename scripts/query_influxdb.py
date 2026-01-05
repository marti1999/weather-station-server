#!/usr/bin/env python3
"""
Simple InfluxDB Query Tool
Displays data in SQL-like table format
"""

import os
import sys
from influxdb import InfluxDBClient
from tabulate import tabulate
from datetime import datetime, timedelta

# Configuration
INFLUXDB_HOST = os.getenv('INFLUXDB_HOST', 'localhost')
INFLUXDB_PORT = int(os.getenv('INFLUXDB_PORT', '8086'))
INFLUXDB_DB = os.getenv('INFLUXDB_DB', 'weather_data')
INFLUXDB_USER = os.getenv('INFLUXDB_USER', 'admin')
INFLUXDB_PASSWORD = os.getenv('INFLUXDB_PASSWORD', 'adminpassword')

def connect_db():
    """Connect to InfluxDB"""
    try:
        client = InfluxDBClient(host=INFLUXDB_HOST, port=INFLUXDB_PORT,
                               username=INFLUXDB_USER, password=INFLUXDB_PASSWORD,
                               database=INFLUXDB_DB)
        return client
    except Exception as e:
        print(f"✗ Failed to connect to InfluxDB: {e}")
        sys.exit(1)

def get_measurements(client):
    """Get all measurements in database"""
    result = client.query('SHOW MEASUREMENTS')
    measurements = []
    for point in result.get_points():
        measurements.append(point['name'])
    return sorted(measurements)

def query_data(client, measurement, limit=100, time_range=None):
    """Query data from a measurement"""
    if time_range:
        query = f'SELECT * FROM "{measurement}" WHERE time > now() - {time_range} LIMIT {limit}'
    else:
        query = f'SELECT * FROM "{measurement}" LIMIT {limit}'
    
    result = client.query(query)
    return result

def format_output(result, measurement):
    """Format query result as table"""
    points = list(result.get_points())
    
    if not points:
        print(f"  No data found in measurement: {measurement}")
        return
    
    # Convert points to table format
    print(f"\n📊 Measurement: {measurement}")
    print(f"   Records: {len(points)}")
    print()
    
    # Prepare table data
    headers = set()
    for point in points:
        headers.update(point.keys())
    
    headers = sorted(list(headers), key=lambda x: (x != 'time', x))  # time first
    
    table_data = []
    for point in points:
        row = []
        for header in headers:
            value = point.get(header, '')
            # Format timestamps
            if header == 'time' and isinstance(value, str):
                try:
                    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
                    value = dt.strftime('%Y-%m-%d %H:%M:%S')
                except:
                    pass
            # Format floats
            elif isinstance(value, float):
                value = round(value, 2)
            row.append(value)
        table_data.append(row)
    
    print(tabulate(table_data, headers=headers, tablefmt="grid", floatfmt=".2f"))
    print()

def main():
    """Main function"""
    print("=" * 70)
    print("InfluxDB Weather Data Query Tool")
    print("=" * 70)
    
    client = connect_db()
    print(f"✓ Connected to InfluxDB at {INFLUXDB_HOST}:{INFLUXDB_PORT}/{INFLUXDB_DB}\n")
    
    # Get measurements
    measurements = get_measurements(client)
    
    if not measurements:
        print("❌ No measurements found in database")
        return
    
    print(f"📈 Found {len(measurements)} measurement(s):")
    for i, m in enumerate(measurements, 1):
        print(f"   {i}. {m}")
    
    # Query all measurements
    print("\n" + "=" * 70)
    print("RECENT DATA (Last 100 records per measurement)")
    print("=" * 70)
    
    for measurement in measurements:
        try:
            result = query_data(client, measurement, limit=100)
            format_output(result, measurement)
        except Exception as e:
            print(f"✗ Error querying {measurement}: {e}")
    
    client.close()
    print("=" * 70)

if __name__ == "__main__":
    main()
