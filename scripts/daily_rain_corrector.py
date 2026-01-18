#!/usr/bin/env python3
"""
Daily Rain Reconstructor
Runs at midnight to reconstruct accurate daily_rain_current and precipitation_rate_mm_h 
from the ground truth rain_mm historical data, eliminating restart-induced errors.

Approach:
1. Get all rain_mm data for yesterday 
2. Calculate daily_rain_current = current_rain_mm - start_of_day_rain_mm
3. Handle sensor resets automatically
4. Reconstruct precipitation rates from corrected daily rain values

Usage: python3 daily_rain_corrector.py
Environment variables needed:
- INFLUXDB_URL (default: http://influxdb:8086)
- INFLUXDB_TOKEN
- INFLUXDB_ORG  
- INFLUXDB_BUCKET
"""

import os
import sys
from datetime import datetime, timedelta
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

def reconstruct_daily_rain():
    """Reconstruct daily_rain_current using rain_mm ground truth when restarts are detected"""
    
    # InfluxDB connection
    url = os.getenv('INFLUXDB_URL', 'http://influxdb:8086')
    token = os.getenv('INFLUXDB_TOKEN')
    org = os.getenv('INFLUXDB_ORG') 
    bucket = os.getenv('INFLUXDB_BUCKET')
    
    if not all([token, org, bucket]):
        print("ERROR: Missing required environment variables")
        return False
    
    client = InfluxDBClient(url=url, token=token, org=org)
    query_api = client.query_api()
    write_api = client.write_api(write_options=SYNCHRONOUS)
    
    try:
        # Get yesterday's date range (ensure we only process the target day)
        yesterday = datetime.now() - timedelta(days=1)
        start_time = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
        end_time = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        print(f"Reconstructing rain data for {yesterday.strftime('%Y-%m-%d')}")
        print(f"Time range: {start_time.isoformat()} to {end_time.isoformat()}")
        
        # Query both daily_rain_current and rain_mm for yesterday ONLY
        daily_rain_query = f'''
        from(bucket: "{bucket}")
          |> range(start: {start_time.isoformat()}Z, stop: {end_time.isoformat()}Z)
          |> filter(fn: (r) => r._measurement == "rtl433")
          |> filter(fn: (r) => r._field == "daily_rain_current")
          |> sort(columns: ["_time"])
        '''
        
        rain_mm_query = f'''
        from(bucket: "{bucket}")
          |> range(start: {start_time.isoformat()}Z, stop: {end_time.isoformat()}Z)
          |> filter(fn: (r) => r._measurement == "rtl433")
          |> filter(fn: (r) => r._field == "rain_mm")
          |> sort(columns: ["_time"])
        '''
        
        daily_rain_result = query_api.query(daily_rain_query)
        rain_mm_result = query_api.query(rain_mm_query)
        
        if not daily_rain_result or not rain_mm_result:
            print(f"Missing data for {yesterday.strftime('%Y-%m-%d')}")
            return True
        
        # Extract daily_rain_current points
        daily_rain_points = []
        for table in daily_rain_result:
            for record in table.records:
                daily_rain_points.append({
                    'time': record.get_time(),
                    'daily_rain': record.get_value()
                })
        
        # Extract rain_mm points  
        rain_mm_points = []
        for table in rain_mm_result:
            for record in table.records:
                rain_mm_points.append({
                    'time': record.get_time(),
                    'rain_mm': record.get_value()
                })
        
        if len(daily_rain_points) < 2 or len(rain_mm_points) < 2:
            print("Not enough data points to analyze")
            return True
        
        print(f"Processing {len(daily_rain_points)} daily_rain_current points and {len(rain_mm_points)} rain_mm points")
        
        # STEP 1: Detect restarts in daily_rain_current (where it drops unexpectedly)
        restarts_detected = False
        for i in range(1, len(daily_rain_points)):
            current = daily_rain_points[i]['daily_rain']
            previous = daily_rain_points[i-1]['daily_rain']
            
            # Restart detected: current value is significantly smaller than previous
            if current < previous - 0.5:  # 0.5mm tolerance for small variations
                restarts_detected = True
                print(f"Restart detected at {daily_rain_points[i]['time']}: daily_rain dropped from {previous:.2f}mm to {current:.2f}mm")
        
        if not restarts_detected:
            print("✅ No restarts detected - no corrections needed")
            return True
        
        print("🔧 Restart detected - reconstructing ALL daily rain values for the entire day")
        
        # STEP 2: Get start-of-day rain_mm baseline
        start_rain_mm = rain_mm_points[0]['rain_mm']
        print(f"Start-of-day rain_mm baseline: {start_rain_mm:.2f}mm")
        
        # STEP 3: Reconstruct ALL daily_rain_current using rain_mm ground truth
        corrected_points = []
        precip_points = []
        
        prev_daily_rain = 0.0
        prev_time = None
        
        # Create a mapping of rain_mm values by time for quick lookup
        rain_mm_by_time = {point['time']: point['rain_mm'] for point in rain_mm_points}
        
        print(f"Reconstructing {len(daily_rain_points)} daily_rain_current data points...")
        
        for i, point in enumerate(daily_rain_points):  # Process ALL points
            current_time = point['time']
            
            # Find closest rain_mm value for this timestamp
            closest_rain_mm = None
            min_time_diff = None
            
            for rain_time, rain_value in rain_mm_by_time.items():
                time_diff = abs((current_time - rain_time).total_seconds())
                if min_time_diff is None or time_diff < min_time_diff:
                    min_time_diff = time_diff
                    closest_rain_mm = rain_value
            
            if closest_rain_mm is not None:
                # Reconstruct daily_rain_current from ground truth
                daily_rain_corrected = max(0.0, closest_rain_mm - start_rain_mm)
                
                # Create corrected daily rain point
                daily_point = Point("rtl433") \
                    .tag("host", "weather-station") \
                    .field("daily_rain_current", daily_rain_corrected) \
                    .time(current_time)
                
                corrected_points.append(daily_point)
                
                # STEP 4: Calculate precipitation rate (5-minute windows)
                if prev_time is not None:
                    time_diff = (current_time - prev_time).total_seconds()
                    
                    # Use 5-minute windows (300 seconds)
                    if time_diff >= 300:
                        rain_diff = daily_rain_corrected - prev_daily_rain
                        
                        # Convert to mm/hour
                        if time_diff > 0 and rain_diff >= 0:
                            precip_rate = (rain_diff / time_diff) * 3600.0
                        else:
                            precip_rate = 0.0
                        
                        # Create precipitation rate point
                        precip_point = Point("rtl433") \
                            .tag("host", "weather-station") \
                            .field("precipitation_rate_mm_h", precip_rate) \
                            .time(current_time)
                        
                        precip_points.append(precip_point)
                        
                        # Update tracking variables for next calculation
                        prev_daily_rain = daily_rain_corrected
                        prev_time = current_time
                else:
                    # First point
                    prev_daily_rain = daily_rain_corrected
                    prev_time = current_time
            
            # Progress indicator for large datasets
            if (i + 1) % 1000 == 0:
                print(f"  Processed {i + 1}/{len(daily_rain_points)} points...")
        
        print(f"Completed reconstruction of {len(corrected_points)} corrected daily rain points")
        
        # STEP 5: Write corrected data to InfluxDB
        all_points = corrected_points + precip_points
        
        if all_points:
            write_api.write(bucket=bucket, record=all_points)
            print(f"✅ Overwrote {len(corrected_points)} daily_rain_current points")
            print(f"✅ Overwrote {len(precip_points)} precipitation_rate_mm_h points")
            
            # Show summary statistics
            if corrected_points:
                max_daily = max(p._fields['daily_rain_current'] for p in corrected_points)
                print(f"✅ Max daily rain (updated): {max_daily:.2f}mm")
        else:
            print("✅ No corrected data points generated")
        
        return True
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        client.close()

if __name__ == "__main__":
    success = reconstruct_daily_rain()
    sys.exit(0 if success else 1)