#!/usr/bin/env python3
"""
MQTT Publisher for RTL_433 data
Use this script to publish RTL_433 JSON output to MQTT broker
Example usage:
    rtl_433 -F json -s 1000k -f 868.3M -R 263 | python mqtt_publisher.py --host 192.168.1.100
"""

import json
import sys
import argparse
from datetime import datetime

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("Error: paho-mqtt not installed. Install with: pip install paho-mqtt")
    sys.exit(1)


class RTL433MQTTPublisher:
    def __init__(self, host, port=1883, topic_prefix="rtl_433"):
        self.host = host
        self.port = port
        self.topic_prefix = topic_prefix
        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        
    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print(f"✓ Connected to MQTT broker at {self.host}:{self.port}")
        else:
            print(f"✗ Connection failed with code: {rc}")
    
    def on_disconnect(self, client, userdata, rc):
        if rc != 0:
            print(f"✗ Unexpected disconnection. Code: {rc}")
    
    def connect(self):
        try:
            self.client.connect(self.host, self.port, keepalive=60)
            self.client.loop_start()
        except Exception as e:
            print(f"✗ Failed to connect: {e}")
            sys.exit(1)
    
    def publish_from_stdin(self):
        """Read JSON lines from stdin and publish to MQTT"""
        print(f"📡 Listening for RTL_433 JSON data...")
        print(f"Publishing to: {self.topic_prefix}/* on {self.host}:{self.port}")
        print("Press Ctrl+C to exit")
        
        try:
            for line in sys.stdin:
                line = line.strip()
                if not line:
                    continue
                
                try:
                    data = json.loads(line)
                    
                    # Extract device identifiers
                    model = data.get('model', 'unknown')
                    id_val = data.get('id', data.get('address', 'unknown'))
                    name = data.get('name', f"{model}_{id_val}")
                    
                    # Create topic path
                    topic = f"{self.topic_prefix}/devices/{name}"
                    
                    # Publish the full JSON payload
                    self.client.publish(topic, json.dumps(data))
                    print(f"📨 {datetime.now().strftime('%H:%M:%S')} -> {topic}")
                    print(f"   Data: {json.dumps(data, indent=2)[:100]}...")
                    
                except json.JSONDecodeError:
                    print(f"✗ Invalid JSON: {line}")
                except Exception as e:
                    print(f"✗ Error publishing: {e}")
        
        except KeyboardInterrupt:
            print("\n✓ Shutting down...")
        finally:
            self.client.loop_stop()
            self.client.disconnect()


def main():
    parser = argparse.ArgumentParser(
        description="Publish RTL_433 JSON data to MQTT broker"
    )
    parser.add_argument('--host', '-H', required=True, help='MQTT broker hostname or IP')
    parser.add_argument('--port', '-p', type=int, default=1883, help='MQTT broker port (default: 1883)')
    parser.add_argument('--topic', '-t', default='rtl_433', help='MQTT topic prefix (default: rtl_433)')
    
    args = parser.parse_args()
    
    publisher = RTL433MQTTPublisher(args.host, args.port, args.topic)
    publisher.connect()
    publisher.publish_from_stdin()


if __name__ == "__main__":
    main()
