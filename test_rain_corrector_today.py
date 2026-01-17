#!/usr/bin/env python3
"""
Test Daily Rain Reconstructor - Dry Run
Tests the corrector with today's data to verify restart detection and correction
"""

import os
import sys
from datetime import datetime, timedelta
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

def test_reconstruct_today():
    """Test reconstruct daily_rain_current using today's data (dry run)"""
    
    # InfluxDB connection
    url = os.getenv('INFLUXDB_URL', 'http://localhost:8086')
    token = os.getenv('INFLUXDB_ADMIN_TOKEN')
    org = os.getenv('INFLUXDB_ORG') 
    bucket = os.getenv('INFLUXDB_BUCKET')
    
    if not all([token, org, bucket]):
        print("ERROR: Missing required environment variables")
        print(f"Token: {'✓' if token else '✗'}")
        print(f"Org: {org}")
        print(f"Bucket: {bucket}")
        return False
    
    client = InfluxDBClient(url=url, token=token, org=org)
    query_api = client.query_api()
    
    try:
        # Get TODAY's data (instead of yesterday for testing)
        today = datetime.now()
        start_time = today.replace(hour=0, minute=0, second=0, microsecond=0)
        end_time = start_time + timedelta(days=1)
        
        print(f"🧪 TESTING: Analyzing today's rain data ({today.strftime('%Y-%m-%d')})")
        print(f"Time range: {start_time} to {end_time}")
        print()
        
        # Query both daily_rain_current and rain_mm for today
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
        
        print("📊 Querying daily_rain_current data...")
        daily_rain_result = query_api.query(daily_rain_query)
        
        print("📊 Querying rain_mm data...")
        rain_mm_result = query_api.query(rain_mm_query)
        
        if not daily_rain_result or not rain_mm_result:
            print(f"❌ Missing data for {today.strftime('%Y-%m-%d')}")
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
            print("❌ Not enough data points to analyze")
            print(f"Daily rain points: {len(daily_rain_points)}")
            print(f"Rain mm points: {len(rain_mm_points)}")
            return True
        
        print(f"✅ Found {len(daily_rain_points)} daily_rain_current points and {len(rain_mm_points)} rain_mm points")
        print()
        
        # Show current daily_rain_current values
        print("📈 Current daily_rain_current values:")
        for i, point in enumerate(daily_rain_points[-10:]):  # Show last 10 points
            time_str = point['time'].strftime('%H:%M:%S')
            print(f"  {time_str}: {point['daily_rain']:.2f}mm")
        print()
        
        # STEP 1: Detect restarts in daily_rain_current
        print("🔍 ANALYZING FOR RESTARTS...")
        restarts_detected = []
        
        for i in range(1, len(daily_rain_points)):
            current = daily_rain_points[i]['daily_rain']
            previous = daily_rain_points[i-1]['daily_rain']
            time_current = daily_rain_points[i]['time']
            time_previous = daily_rain_points[i-1]['time']
            
            # Restart detected: current value is significantly smaller than previous
            if current < previous - 0.5:  # 0.5mm tolerance
                restart_info = {
                    'time': time_current,
                    'previous_value': previous,
                    'current_value': current,
                    'drop': previous - current
                }
                restarts_detected.append(restart_info)
                
                print(f"🚨 RESTART DETECTED at {time_current.strftime('%H:%M:%S')}")
                print(f"   Previous: {previous:.2f}mm at {time_previous.strftime('%H:%M:%S')}")
                print(f"   Current:  {current:.2f}mm")
                print(f"   Drop:     {restart_info['drop']:.2f}mm")
                print()
        
        if not restarts_detected:
            print("✅ No restarts detected - daily rain data looks good!")
            return True
        
        print(f"Found {len(restarts_detected)} restart(s)")
        print()
        
        # STEP 2: Get start-of-day rain_mm baseline
        start_rain_mm = rain_mm_points[0]['rain_mm']
        end_rain_mm = rain_mm_points[-1]['rain_mm']
        print(f"📊 Rain_mm baseline analysis:")
        print(f"   Start of day: {start_rain_mm:.2f}mm at {rain_mm_points[0]['time'].strftime('%H:%M:%S')}")
        print(f"   Current:      {end_rain_mm:.2f}mm at {rain_mm_points[-1]['time'].strftime('%H:%M:%S')}")
        print(f"   Total change: {end_rain_mm - start_rain_mm:.2f}mm")
        print()
        
        # STEP 3: Show what the corrected values would be
        print("🔧 RECONSTRUCTING ENTIRE DAY (since restart detected):")
        print("Processing ALL data points for the day...")
        print()
        
        # Create a mapping of rain_mm values by time for quick lookup
        rain_mm_by_time = {point['time']: point['rain_mm'] for point in rain_mm_points}
        
        corrections_made = 0
        max_corrected = 0.0
        total_points_processed = 0
        significant_corrections = []
        
        print("Sample corrections (showing every 100th point):")
        print("Time     | Original | Rain_mm | Corrected | Difference")
        print("-" * 60)
        
        for i, point in enumerate(daily_rain_points):  # Process ALL points, not just last 10
            current_time = point['time']
            original_daily = point['daily_rain']
            
            # Find closest rain_mm value for this timestamp
            closest_rain_mm = None
            min_time_diff = None
            
            for rain_time, rain_value in rain_mm_by_time.items():
                time_diff = abs((current_time - rain_time).total_seconds())
                if min_time_diff is None or time_diff < min_time_diff:
                    min_time_diff = time_diff
                    closest_rain_mm = rain_value
            
            if closest_rain_mm is not None:
                # Calculate what the corrected value would be
                daily_rain_corrected = max(0.0, closest_rain_mm - start_rain_mm)
                difference = daily_rain_corrected - original_daily
                max_corrected = max(max_corrected, daily_rain_corrected)
                total_points_processed += 1
                
                if abs(difference) > 0.1:  # Count significant corrections
                    corrections_made += 1
                    significant_corrections.append({
                        'time': current_time,
                        'original': original_daily,
                        'corrected': daily_rain_corrected,
                        'difference': difference
                    })
                
                # Show every 100th point as sample
                if i % 100 == 0 or i < 5 or i >= len(daily_rain_points) - 5:
                    time_str = current_time.strftime('%H:%M:%S')
                    print(f"{time_str} | {original_daily:8.2f} | {closest_rain_mm:7.2f} | {daily_rain_corrected:9.2f} | {difference:+8.2f}")
        
        print()
        print(f"✅ FULL DAY RECONSTRUCTION SUMMARY:")
        print(f"   Total data points processed: {total_points_processed}")
        print(f"   Points needing correction: {corrections_made}")
        print(f"   Correction rate: {corrections_made/total_points_processed*100:.1f}%")
        print(f"   Max corrected daily rain: {max_corrected:.2f}mm")
        
        # Show time periods with significant corrections
        if significant_corrections:
            print()
            print("📊 Periods with significant corrections:")
            for correction in significant_corrections[:10]:  # Show first 10 significant corrections
                time_str = correction['time'].strftime('%H:%M:%S')
                print(f"   {time_str}: {correction['original']:.2f}mm → {correction['corrected']:.2f}mm ({correction['difference']:+.2f}mm)")
            
            if len(significant_corrections) > 10:
                print(f"   ... and {len(significant_corrections) - 10} more corrections")
        
        # Show precipitation rate impact
        print()
        print("💧 PRECIPITATION RATE RECONSTRUCTION:")
        precip_corrections = 0
        sample_precip_rates = []
        
        prev_daily_corrected = 0.0
        prev_time = None
        
        for point in daily_rain_points[::50]:  # Check every 50th point for precip rate
            current_time = point['time']
            
            # Find corrected daily rain for this point
            closest_rain_mm = None
            min_time_diff = None
            for rain_time, rain_value in rain_mm_by_time.items():
                time_diff = abs((current_time - rain_time).total_seconds())
                if min_time_diff is None or time_diff < min_time_diff:
                    min_time_diff = time_diff
                    closest_rain_mm = rain_value
            
            if closest_rain_mm is not None and prev_time is not None:
                daily_rain_corrected = max(0.0, closest_rain_mm - start_rain_mm)
                time_diff = (current_time - prev_time).total_seconds()
                
                if time_diff >= 300:  # 5-minute window
                    rain_diff = daily_rain_corrected - prev_daily_corrected
                    if time_diff > 0 and rain_diff >= 0:
                        precip_rate = (rain_diff / time_diff) * 3600.0
                        if precip_rate > 0.1:  # Significant precipitation rate
                            precip_corrections += 1
                            sample_precip_rates.append({
                                'time': current_time,
                                'rate': precip_rate
                            })
                        
                    prev_daily_corrected = daily_rain_corrected
                    prev_time = current_time
            else:
                if closest_rain_mm is not None:
                    prev_daily_corrected = max(0.0, closest_rain_mm - start_rain_mm)
                    prev_time = current_time
        
        print(f"   Precipitation rate calculations: {precip_corrections} periods with measurable rain")
        if sample_precip_rates:
            print("   Sample rates:")
            for rate_info in sample_precip_rates[:5]:
                time_str = rate_info['time'].strftime('%H:%M:%S')
                print(f"     {time_str}: {rate_info['rate']:.2f} mm/h")
        else:
            print("   No significant precipitation rates detected")
        
        print()
        print("🧪 DRY RUN COMPLETE - No data was written to InfluxDB")
        print("   To apply corrections, run the real daily_rain_corrector.py")
        
        return True
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        client.close()

if __name__ == "__main__":
    success = test_reconstruct_today()
    sys.exit(0 if success else 1)