#!/usr/bin/env python3
"""
Weather Station Rain Simulator

Simulates rain events by publishing realistic weather station MQTT messages.
Useful for testing Grafana dashboards and rain calculations without real rainfall.

Three simulation modes:
- gradual: Realistic incremental accumulation (0.5mm every 30 seconds)
- burst: Intense rainfall event (50mm in 5 minutes)
- reset: Sensor reset simulation (rain_mm drops to 0 mid-sequence)
"""

import argparse
import json
import sys
import time
from datetime import datetime

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("Error: paho-mqtt library not installed")
    print("Install it with: pip install paho-mqtt")
    sys.exit(1)

# MQTT Configuration
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_TOPIC = "rtl_433/Vevor-7in1/3092"

# Weather station default values (non-rain fields)
DEFAULT_TEMP = 15.0
DEFAULT_HUMIDITY = 65
DEFAULT_WIND_AVG = 5.0
DEFAULT_WIND_MAX = 8.0
DEFAULT_WIND_DIR = 180.0
DEFAULT_LIGHT = 10000.0
DEFAULT_UVI = 2.0


def create_weather_message(rain_mm, temperature=DEFAULT_TEMP, humidity=DEFAULT_HUMIDITY,
                           wind_avg=DEFAULT_WIND_AVG, wind_max=DEFAULT_WIND_MAX,
                           wind_dir=DEFAULT_WIND_DIR, light_lux=DEFAULT_LIGHT, uvi=DEFAULT_UVI):
    """
    Create a weather station JSON message.
    
    Args:
        rain_mm: Cumulative rainfall in millimeters
        temperature: Temperature in Celsius
        humidity: Relative humidity percentage
        wind_avg: Average wind speed in km/h
        wind_max: Maximum wind gust in km/h
        wind_dir: Wind direction in degrees
        light_lux: Light intensity in lux
        uvi: UV index
    
    Returns:
        JSON string matching weather station format
    """
    message = {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "model": "Vevor-7in1",
        "id": 3092,
        "channel": 0,
        "battery_ok": 1,
        "temperature_C": temperature,
        "humidity": humidity,
        "wind_avg_km_h": wind_avg,
        "wind_max_km_h": wind_max,
        "wind_dir_deg": wind_dir,
        "rain_mm": rain_mm,
        "light_lux": light_lux,
        "uvi": uvi,
        "mic": "CHECKSUM",
        "mod": "FSK"
    }
    return json.dumps(message)


def publish_message(client, rain_mm, extra_info=""):
    """Publish a single weather message to MQTT."""
    message = create_weather_message(rain_mm)
    result = client.publish(MQTT_TOPIC, message)
    
    if result.rc == mqtt.MQTT_ERR_SUCCESS:
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] Published: rain_mm={rain_mm:.1f} {extra_info}")
    else:
        print(f"Error publishing message: {result.rc}")


def simulate_gradual(client, duration_minutes=10, increment_mm=0.5, interval_seconds=30):
    """
    Simulate gradual rain accumulation.
    
    Args:
        client: MQTT client
        duration_minutes: Total simulation duration
        increment_mm: Rain increment per message
        interval_seconds: Time between messages
    """
    print("\n=== GRADUAL RAIN SIMULATION ===")
    print(f"Duration: {duration_minutes} minutes")
    print(f"Increment: {increment_mm} mm every {interval_seconds} seconds")
    print(f"Total expected: {(duration_minutes * 60 / interval_seconds) * increment_mm:.1f} mm\n")
    
    base_rain = 150.0  # Starting cumulative value
    iterations = int((duration_minutes * 60) / interval_seconds)
    
    for i in range(iterations):
        current_rain = base_rain + (i * increment_mm)
        extra_info = f"(+{i * increment_mm:.1f} mm total)"
        publish_message(client, current_rain, extra_info)
        
        if i < iterations - 1:  # Don't sleep after last message
            time.sleep(interval_seconds)
    
    print(f"\n✓ Gradual simulation complete: {iterations} messages sent")


def simulate_burst(client, total_rain_mm=50, duration_minutes=5):
    """
    Simulate intense rainfall burst.
    
    Args:
        client: MQTT client
        total_rain_mm: Total rainfall amount
        duration_minutes: Duration of burst
    """
    print("\n=== BURST RAIN SIMULATION ===")
    print(f"Total rain: {total_rain_mm} mm in {duration_minutes} minutes")
    print(f"Rate: {(total_rain_mm / duration_minutes) * 60:.1f} mm/h\n")
    
    base_rain = 200.0
    messages = duration_minutes * 2  # 2 messages per minute
    increment = total_rain_mm / messages
    interval = (duration_minutes * 60) / messages
    
    for i in range(messages):
        current_rain = base_rain + (i * increment)
        progress = (i / messages) * 100
        extra_info = f"({progress:.0f}% - intense rainfall)"
        publish_message(client, current_rain, extra_info)
        
        if i < messages - 1:
            time.sleep(interval)
    
    print(f"\n✓ Burst simulation complete: {total_rain_mm} mm in {duration_minutes} minutes")


def simulate_reset(client):
    """
    Simulate sensor reset (rain_mm drops to 0).
    
    Tests system handling of cumulative counter resets.
    """
    print("\n=== SENSOR RESET SIMULATION ===")
    print("Simulating rain accumulation followed by sensor reset\n")
    
    # Phase 1: Normal accumulation
    print("Phase 1: Accumulating rain...")
    base_rain = 150.0
    for i in range(5):
        current_rain = base_rain + (i * 2.0)
        publish_message(client, current_rain, "(before reset)")
        time.sleep(10)
    
    # Phase 2: Sensor reset
    print("\nPhase 2: SENSOR RESET (rain_mm → 0)")
    publish_message(client, 0.0, "⚠️  RESET EVENT")
    time.sleep(10)
    
    # Phase 3: Continue accumulation from 0
    print("\nPhase 3: Accumulating after reset...")
    for i in range(5):
        current_rain = i * 2.0
        publish_message(client, current_rain, "(after reset)")
        time.sleep(10)
    
    print("\n✓ Reset simulation complete: sensor reset handled")


def main():
    parser = argparse.ArgumentParser(
        description="Simulate weather station rain events via MQTT",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Gradual rain over 10 minutes (default)
  python simulate_rain.py --mode gradual
  
  # Custom gradual rain: 1mm every minute for 30 minutes
  python simulate_rain.py --mode gradual --duration 30 --increment 1.0 --interval 60
  
  # Intense burst: 50mm in 5 minutes
  python simulate_rain.py --mode burst
  
  # Custom burst: 100mm in 10 minutes
  python simulate_rain.py --mode burst --total 100 --duration 10
  
  # Sensor reset simulation
  python simulate_rain.py --mode reset
  
  # Custom MQTT broker
  python simulate_rain.py --mode gradual --broker 192.168.1.100 --port 1883
        """
    )
    
    parser.add_argument(
        "--mode",
        choices=["gradual", "burst", "reset"],
        required=True,
        help="Simulation mode: gradual (realistic), burst (intense), reset (sensor reset)"
    )
    
    parser.add_argument(
        "--broker",
        default=MQTT_BROKER,
        help=f"MQTT broker hostname or IP (default: {MQTT_BROKER})"
    )
    
    parser.add_argument(
        "--port",
        type=int,
        default=MQTT_PORT,
        help=f"MQTT broker port (default: {MQTT_PORT})"
    )
    
    # Gradual mode options
    parser.add_argument(
        "--duration",
        type=int,
        default=10,
        help="Duration in minutes for gradual/burst modes (default: 10)"
    )
    
    parser.add_argument(
        "--increment",
        type=float,
        default=0.5,
        help="Rain increment in mm for gradual mode (default: 0.5)"
    )
    
    parser.add_argument(
        "--interval",
        type=int,
        default=30,
        help="Seconds between messages for gradual mode (default: 30)"
    )
    
    # Burst mode options
    parser.add_argument(
        "--total",
        type=float,
        default=50.0,
        help="Total rainfall in mm for burst mode (default: 50)"
    )
    
    args = parser.parse_args()
    
    # Connect to MQTT broker
    print(f"Connecting to MQTT broker at {args.broker}:{args.port}...")
    client = mqtt.Client()
    
    try:
        client.connect(args.broker, args.port, 60)
        print("✓ Connected successfully")
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        print("\nTroubleshooting:")
        print("1. Check that MQTT broker is running: docker ps | grep mqtt-broker")
        print("2. Verify broker address and port")
        print("3. Check firewall settings")
        sys.exit(1)
    
    # Run selected simulation
    try:
        if args.mode == "gradual":
            simulate_gradual(client, args.duration, args.increment, args.interval)
        elif args.mode == "burst":
            simulate_burst(client, args.total, args.duration)
        elif args.mode == "reset":
            simulate_reset(client)
    except KeyboardInterrupt:
        print("\n\n⚠️  Simulation interrupted by user")
    except Exception as e:
        print(f"\n✗ Simulation error: {e}")
        sys.exit(1)
    finally:
        client.disconnect()
        print("Disconnected from MQTT broker\n")


if __name__ == "__main__":
    main()
