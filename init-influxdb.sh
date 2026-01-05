#!/bin/bash
# Wait for InfluxDB to start
sleep 5

# Check if the setup is already done
if [ ! -f /var/lib/influxdb2/.initialized ]; then
    echo "Setting up InfluxDB..."
    
    # Create initial setup (this will fail if already setup, which is fine)
    influx setup \
        --bucket weather_data \
        --org weather_org \
        --username admin \
        --password adminpassword \
        --token weather-token-default \
        --retention 30d \
        --force || echo "Setup already complete or skipped"
    
    touch /var/lib/influxdb2/.initialized
fi

echo "InfluxDB initialization complete"
