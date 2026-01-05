#!/usr/bin/env python3
"""
MQTT to InfluxDB Bridge
Subscribes to MQTT topics and forwards data to InfluxDB
"""

import json
import os
from datetime import datetime

import paho.mqtt.client as mqtt
from influxdb import InfluxDBClient

# Configuration
MQTT_HOST = os.getenv('MQTT_HOST', 'localhost')
MQTT_PORT = int(os.getenv('MQTT_PORT', '1883'))
MQTT_TOPIC = os.getenv('MQTT_TOPIC', 'rtl_433/#')

INFLUXDB_HOST = os.getenv('INFLUXDB_HOST', 'localhost')
INFLUXDB_PORT = int(os.getenv('INFLUXDB_PORT', '8086'))
INFLUXDB_DB = os.getenv('INFLUXDB_DB', 'weather_data')
INFLUXDB_USER = os.getenv('INFLUXDB_USER', 'admin')
INFLUXDB_PASSWORD = os.getenv('INFLUXDB_PASSWORD', 'adminpassword')

# InfluxDB client - initialize in main() with error handling
influx_client = None
write_api = None

def on_connect(client, userdata, flags, rc):
    """Callback for MQTT connection"""
    if rc == 0:
        print(f"✓ Connected to MQTT broker at {MQTT_HOST}:{MQTT_PORT}")
        client.subscribe(MQTT_TOPIC)
        print(f"✓ Subscribed to topic: {MQTT_TOPIC}")
    else:
        print(f"✗ Failed to connect, return code: {rc}")

def on_disconnect(client, userdata, rc):
    """Callback for MQTT disconnection"""
    if rc != 0:
        print(f"✗ Unexpected disconnection. Return code: {rc}")

def on_message(client, userdata, msg):
    """Callback for receiving MQTT messages"""
    try:
        # Parse MQTT topic and payload
        topic = msg.topic
        payload = msg.payload.decode('utf-8')
        
        print(f"📨 Received: {topic} = {payload}")
        
        # Try to parse as JSON
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            data = {"value": payload}
        
        # Prepare InfluxDB point
        points = prepare_influx_point(topic, data)
        
        if points:
            # Write to InfluxDB
            influx_client.write_points(points)
            print(f"✓ Written to InfluxDB: {len(points)} point(s)")
    
    except Exception as e:
        print(f"✗ Error processing message: {e}")
        import traceback
        traceback.print_exc()

def prepare_influx_point(topic, data):
    """Prepare InfluxDB points from MQTT data"""
    try:
        # Extract measurement name from topic
        parts = topic.split('/')
        measurement = '_'.join(parts) if len(parts) > 1 else parts[0]
        
        if not isinstance(data, dict):
            return None
        
        # Build point
        point = {
            "measurement": measurement,
            "tags": {},
            "fields": {},
        }
        
        # Define which fields are measurements (numeric values to graph)
        # Everything else becomes tags (metadata)
        measurement_fields = {
            'temperature_C', 'humidity', 'wind_avg_km_h', 'wind_max_km_h',
            'wind_dir_deg', 'rain_mm', 'uvi', 'light_lux', 'rssi',
            'snr', 'noise', 'temperature', 'temp', 'temp_c'  # common aliases
        }
        
        # Extract timestamp if available
        timestamp = None
        if 'time' in data:
            try:
                from datetime import datetime
                # Parse ISO format or custom format
                time_str = data['time']
                # Try ISO format first
                try:
                    timestamp = datetime.fromisoformat(time_str)
                except:
                    # Try common RTL_433 format: "2026-01-05 18:44:20"
                    timestamp = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
                # Use nanosecond timestamp for InfluxDB 1.8
                point["time"] = int(timestamp.timestamp() * 1e9)
            except Exception as e:
                print(f"⚠ Warning: Could not parse timestamp: {data.get('time')} - {e}")
        
        # Extract fields and tags
        for key, value in data.items():
            if key == 'time':
                continue  # Already handled
            
            # Check if this should be a field (measurement)
            is_measurement = key in measurement_fields
            
            if isinstance(value, (int, float)):
                if is_measurement:
                    point["fields"][key] = float(value)
                else:
                    # Non-measurement numeric values become string tags
                    point["tags"][key] = str(value)
            elif isinstance(value, bool):
                point["fields"][key] = int(value)  # Convert bool to int (0/1)
            else:
                # Convert everything else to tag
                point["tags"][key] = str(value)
        
        # Ensure we have fields
        if not point["fields"]:
            print(f"⚠ Warning: No measurement fields found in data: {data}")
            return None
        
        return [point]
    
    except Exception as e:
        print(f"✗ Error preparing InfluxDB point: {e}")
        import traceback
        traceback.print_exc()
        return None

def main():
    """Main function"""
    global influx_client
    import sys
    sys.stdout.flush()
    sys.stderr.flush()
    print("=" * 60)
    print("MQTT to InfluxDB Bridge")
    print("=" * 60)
    print(f"MQTT Broker: {MQTT_HOST}:{MQTT_PORT}")
    print(f"InfluxDB: {INFLUXDB_HOST}:{INFLUXDB_PORT}/{INFLUXDB_DB}")
    print(f"Topic: {MQTT_TOPIC}")
    print("=" * 60)
    sys.stdout.flush()
    sys.stderr.flush()
    
    # Initialize InfluxDB client
    try:
        influx_client = InfluxDBClient(host=INFLUXDB_HOST, port=INFLUXDB_PORT, 
                                       username=INFLUXDB_USER, password=INFLUXDB_PASSWORD,
                                       database=INFLUXDB_DB)
        influx_client.create_database(INFLUXDB_DB)
        print("✓ InfluxDB client initialized")
        sys.stdout.flush()
    except Exception as e:
        print(f"✗ Failed to initialize InfluxDB: {e}")
        import traceback
        traceback.print_exc()
        print("Continuing anyway, will retry connection...")
        sys.stdout.flush()
    
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    
    try:
        print(f"Connecting to MQTT broker...")
        sys.stdout.flush()
        client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
        client.loop_forever()
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        client.disconnect()
        if influx_client:
            try:
                influx_client.close()
            except:
                pass

if __name__ == "__main__":
    main()
