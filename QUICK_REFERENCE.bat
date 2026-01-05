@echo off
REM Weather Station Server - Quick Reference
REM Windows batch file with useful commands

echo.
echo ====================================
echo Weather Station Server - Quick Ref
echo ====================================
echo.
echo Starting Services:
echo   docker-compose up -d
echo.
echo Stopping Services:
echo   docker-compose down
echo.
echo View Logs:
echo   docker-compose logs -f
echo   docker-compose logs -f mosquitto
echo   docker-compose logs -f influxdb
echo   docker logs -f weather-mqtt-bridge
echo.
echo Check Status:
echo   docker-compose ps
echo   docker stats
echo.
echo Test MQTT Connection:
echo   mosquitto_pub -h localhost -t test -m "hello"
echo   mosquitto_sub -h localhost -t "rtl_433/#"
echo.
echo InfluxDB Web UI:
echo   http://localhost:8086
echo.
echo Stop All:
echo   docker-compose down
echo.
echo Reset Everything (WARNING: Deletes data!):
echo   docker-compose down -v
echo   docker-compose up -d
echo.
echo ====================================
echo.
