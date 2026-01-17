#!/usr/bin/env python3
"""
Test the Daily Rain Corrector manually
"""

import os
import sys
sys.path.append('/home/marti/weather-station-server/scripts')

# Set environment variables for testing
os.environ['INFLUXDB_URL'] = 'http://localhost:8086'
os.environ['INFLUXDB_TOKEN'] = os.getenv('INFLUXDB_ADMIN_TOKEN', '')
os.environ['INFLUXDB_ORG'] = os.getenv('INFLUXDB_ORG', 'weather_org')
os.environ['INFLUXDB_BUCKET'] = os.getenv('INFLUXDB_BUCKET', 'weather_data')

if __name__ == "__main__":
    from daily_rain_corrector import reconstruct_daily_rain
    
    print("Testing Daily Rain Reconstructor...")
    print(f"InfluxDB URL: {os.environ['INFLUXDB_URL']}")
    print(f"InfluxDB Org: {os.environ['INFLUXDB_ORG']}")
    print(f"InfluxDB Bucket: {os.environ['INFLUXDB_BUCKET']}")
    print()
    
    success = reconstruct_daily_rain()
    
    if success:
        print("✅ Rain reconstructor test completed successfully")
    else:
        print("❌ Rain reconstructor test failed")
        sys.exit(1)