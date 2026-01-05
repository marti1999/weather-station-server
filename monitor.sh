#!/bin/bash
# Weather Station Server - Monitoring Dashboard
# Quick commands to monitor the system

echo "=================================================="
echo "Weather Station Server - Monitoring Dashboard"
echo "=================================================="
echo ""

echo "📊 Container Status:"
docker-compose ps
echo ""

echo "💾 Resource Usage:"
docker stats --no-stream
echo ""

echo "📋 Recent Logs (Mosquitto):"
docker-compose logs --tail 10 mosquitto
echo ""

echo "📋 Recent Logs (Bridge):"
docker logs --tail 10 weather-mqtt-bridge
echo ""

echo "📋 Recent Logs (InfluxDB):"
docker-compose logs --tail 10 influxdb
echo ""

echo "🔌 MQTT Connections:"
docker exec weather-mosquitto mosquitto_sub -h localhost -t '$SYS/broker/clients/total' -W 1 -C 1 || echo "Unable to read MQTT stats"
echo ""

echo "💾 Data Volume Usage:"
du -sh influxdb_data/ mosquitto_data/ mosquitto_logs/ 2>/dev/null || echo "Data directories not yet created"
echo ""

echo "=================================================="
