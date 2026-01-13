# Testing the Data Flow

This guide helps you verify that data is flowing correctly through the entire weather station pipeline.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Step 1: Verify RTL_433 Reception](#step-1-verify-rtl_433-reception)
- [Step 2: Monitor MQTT Messages](#step-2-monitor-mqtt-messages)
- [Step 3: Check Telegraf Processing](#step-3-check-telegraf-processing)
- [Step 4: Verify InfluxDB Storage](#step-4-verify-influxdb-storage)
- [Step 5: Test Grafana Dashboards](#step-5-test-grafana-dashboards)
- [Validation Checklist](#validation-checklist)

---

## Prerequisites

All Docker containers must be running:

```bash
docker compose ps
```

Expected output - all services should show `Up`:
```
NAME         STATUS
grafana      Up
influxdb     Up
mosquitto    Up
rtl433       Up (if using Docker RTL_433)
telegraf     Up
```

---

## Step 1: Verify RTL_433 Reception

### If Running RTL_433 in Docker

Check the container logs for decoded messages:

```bash
docker compose logs -f rtl433 --tail 50
```

**Expected output**: JSON objects with weather data every 10-20 seconds:
```json
{"time": "2026-01-13 12:34:56", "model": "Vevor-7in1", "id": 3092, "channel": 0,
 "battery_ok": 1, "temperature_C": 15.2, "humidity": 65, "wind_avg_km_h": 12.5, ...}
```

**Troubleshooting**:
- **No output**: Check USB device passthrough in `docker-compose.yml`
- **CRC errors**: Normal occasionally, but should not be constant
- **Wrong frequency**: Adjust `-f` parameter (868.3M for EU, 433.92M for US)

### If Running RTL_433 Externally

Your RTL_433 terminal should show similar JSON output. If not:

```bash
# Test RTL-SDR device
rtl_test

# Check if device is detected
lsusb | grep Realtek  # Linux
# or
Get-PnpDevice | Where-Object {$_.FriendlyName -like "*RTL*"}  # Windows PowerShell
```

---

## Step 2: Monitor MQTT Messages

Subscribe to all RTL_433 topics to verify MQTT broker is receiving data:

### Using Docker (Recommended)

```bash
docker exec -it mqtt-broker mosquitto_sub -t "rtl_433/#" -v
```

### Using Local MQTT Client

```bash
# Linux/Mac/Git Bash
mosquitto_sub -h localhost -t "rtl_433/#" -v

# Windows PowerShell (if mosquitto installed locally)
mosquitto_sub.exe -h localhost -t "rtl_433/#" -v
```

**Expected output**: Topic names followed by JSON payloads:
```
rtl_433/Vevor-7in1/3092 {"time": "2026-01-13 12:34:56", "model": "Vevor-7in1", ...}
```

**Troubleshooting**:
- **No output**: Check if RTL_433 is publishing (verify MQTT broker address)
- **Permission denied**: Check Mosquitto allows anonymous connections
- **Connection refused**:
  - Verify port 1883 is exposed: `docker port mqtt-broker`
  - Check for conflicting MQTT brokers: `netstat -ano | findstr :1883` (Windows)

### Test MQTT Publishing

Send a test message:

```bash
# Using Docker
docker exec -it mqtt-broker mosquitto_pub -t "test/topic" -m "test message"

# Using local client
mosquitto_pub -h localhost -t "test/topic" -m "test message"
```

Then subscribe to verify:

```bash
docker exec -it mqtt-broker mosquitto_sub -t "test/#" -v
```

---

## Step 3: Check Telegraf Processing

View Telegraf logs to confirm it's receiving MQTT messages and writing to InfluxDB:

```bash
docker compose logs -f telegraf --tail 50
```

**Expected output**:
```
2026-01-13T12:34:56Z D! [outputs.influxdb_v2] Wrote batch of 1 metrics in 12ms
2026-01-13T12:35:06Z D! [outputs.influxdb_v2] Wrote batch of 1 metrics in 8ms
```

**Troubleshooting**:
- **No metrics**: Check Telegraf MQTT subscription topics match RTL_433 publish topics
- **"Error writing to InfluxDB"**: Verify `INFLUXDB_ADMIN_TOKEN` in `.env` matches
- **"Connection refused"**: InfluxDB container may not be ready (wait 30 seconds after startup)

### Enable Debug Mode

If logs don't show enough detail, enable debug mode:

Edit `telegraf/telegraf.conf`:
```toml
[agent]
  debug = true  # Already enabled by default
```

Restart Telegraf:
```bash
docker compose restart telegraf
```

### Verify Starlark Processor

Check logs for Starlark processing messages:

```bash
docker compose logs telegraf | grep -i starlark
```

No errors should appear. If you see Starlark errors, check syntax in `telegraf.conf`.

---

## Step 4: Verify InfluxDB Storage

### Using InfluxDB Web UI

1. Open http://localhost:8086
2. Login with credentials from `.env`:
   - Username: `admin`
   - Password: Value of `INFLUXDB_ADMIN_PASSWORD`
3. Click **Data Explorer** (icon on left sidebar)
4. Select:
   - **Bucket**: `weather_data`
   - **Measurement**: `rtl433`
   - **Field**: `temperature_C` (or any other field)
5. Click **Submit**

**Expected result**: A graph showing temperature data over time.

### Using Command Line

Query recent temperature data:

```bash
docker exec influxdb influx query \
  'from(bucket:"weather_data")
   |> range(start: -1h)
   |> filter(fn: (r) => r._measurement == "rtl433" and r._field == "temperature_C")
   |> limit(n: 10)' \
  --org weather --raw
```

**Expected output**: CSV-formatted data with timestamps and temperature values.

### Verify All Fields

Check that derived fields are being stored:

```bash
docker exec influxdb influx query \
  'from(bucket:"weather_data")
   |> range(start: -10m)
   |> filter(fn: (r) => r._measurement == "rtl433")
   |> filter(fn: (r) =>
     r._field == "dew_point_C" or
     r._field == "feels_like_C" or
     r._field == "daily_rain_current" or
     r._field == "precipitation_rate_mm_h" or
     r._field == "solar_radiation_w_m2")
   |> limit(n: 5)' \
  --org weather --raw
```

**Expected output**: Data for all derived fields.

**Troubleshooting**:
- **No data**: Telegraf may not be running or configured correctly
- **Only raw fields, no derived**: Check Starlark processor in Telegraf logs
- **Error: unauthorized**: Verify `INFLUXDB_ADMIN_TOKEN` is correct

### Count Total Records

```bash
docker exec influxdb influx query \
  'from(bucket:"weather_data")
   |> range(start: -24h)
   |> count()' \
  --org weather --raw
```

**Expected**: Several thousand records for a 24-hour period (due to ASK+FSK dual transmission).

---

## Step 5: Test Grafana Dashboards

### Access Grafana

1. Open http://localhost:3000
2. Login:
   - Username: `admin`
   - Password: Value of `GRAFANA_ADMIN_PASSWORD` from `.env`
3. Navigate to **Dashboards** (icon on left sidebar)

### Available Dashboards

Three dashboards should be provisioned automatically:

1. **Weather Station Dashboard**
   - Real-time view (last 24 hours by default)
   - Panels: Temperature, Humidity, Wind, Precipitation, UV Index, Solar Radiation
   - Refresh: Every 30 seconds

2. **Weather Monthly Trends**
   - 30-day historical view
   - Daily aggregations (avg/max/min)
   - Refresh: Every 5 minutes

3. (Optional) **Current Weather Conditions** - Removed in latest version

### Verify Dashboard Functionality

**Test 1: Check Data Appears**
- Open "Weather Station Dashboard"
- All panels should show data
- No "No Data" messages

**Test 2: Verify Real-Time Updates**
- Watch the "Last updated" indicator
- Data should refresh every 30 seconds
- Temperature should change gradually

**Test 3: Check Derived Fields**
- **Temperature panel**: Should show 3 lines (Temperature, Dew Point, Feels Like)
- **Precipitation panel**: Should show Daily Rain (bars) and Rain Rate (line)
- **Solar Radiation panel**: Should show calculated W/m² values

**Test 4: Verify Monthly Aggregations**
- Open "Weather Monthly Trends"
- Each panel should show 3 series (avg/max/min or similar)
- Data points should appear at midnight (local time)
- Hover over data points - tooltip should show correct date

**Troubleshooting**:
- **No dashboards**: Check `grafana/provisioning/dashboards/` directory exists
- **"No Data"**: InfluxDB datasource may not be configured
  - Go to **Connections** → **Data sources**
  - InfluxDB datasource should exist with green checkmark
- **Wrong timezone**: Check dashboard timezone setting (top right → timezone icon)

### Test Datasource Connection

1. Go to **Connections** → **Data sources**
2. Click **InfluxDB**
3. Scroll down, click **Save & Test**

**Expected**: Green message "datasource is working. X measurements found"

---

## Validation Checklist

Use this checklist to verify complete system functionality:

### Data Ingestion
- [ ] RTL_433 is decoding weather station signals
- [ ] MQTT broker is receiving messages on `rtl_433/#` topics
- [ ] Telegraf logs show successful writes to InfluxDB
- [ ] InfluxDB contains data in `weather_data` bucket

### Field Validation
- [ ] Raw fields are being stored (temperature_C, humidity, etc.)
- [ ] Derived fields are calculated (dew_point_C, feels_like_C, etc.)
- [ ] Daily rain resets at midnight (check `daily_rain_current`)
- [ ] Precipitation rate updates every 5 minutes

### Dashboard Verification
- [ ] Weather Station Dashboard shows real-time data
- [ ] All panels display without errors
- [ ] Derived field panels show correct calculations
- [ ] Monthly Trends dashboard shows daily aggregations
- [ ] Dates on monthly dashboard align correctly (not offset by 1 day)
- [ ] Dashboard auto-refresh works

### Timezone Correctness
- [ ] Timestamps in InfluxDB are in UTC
- [ ] Grafana displays times in local timezone
- [ ] Daily rain resets at correct local midnight
- [ ] Monthly aggregation timestamps show correct dates

### Performance
- [ ] Dashboard loads in < 5 seconds
- [ ] No error messages in any container logs
- [ ] CPU usage normal (< 50% idle state)
- [ ] Memory usage stable (no leaks)

---

## Common Issues and Solutions

### Issue: Dual ASK/FSK Values

**Symptom**: Grafana shows duplicate values for each metric with slight differences.

**Cause**: Weather station transmits twice (ASK and FSK modulation).

**Solution**: Normal behavior. Grafana queries use `drop()` to remove the `mod` tag, which causes values to be averaged or merged.

### Issue: Daily Rain Not Resetting

**Symptom**: `daily_rain_current` doesn't reset to 0 at midnight.

**Cause**: Timezone offset in Telegraf doesn't match local timezone.

**Solution**: Edit `telegraf/telegraf.conf` line 98:
```python
tz_offset = 3600  # Adjust based on your timezone
```

### Issue: Missing Data Gaps

**Symptom**: Gaps in dashboard graphs.

**Cause**: Temporary signal loss or sensor sleep mode.

**Solution**: Normal for battery-powered sensors. Gaps < 1 minute are expected.

### Issue: Stale Data

**Symptom**: Last update time is old (> 5 minutes).

**Cause**: RTL_433 not receiving signals or MQTT connection lost.

**Solution**:
1. Check RTL_433 logs
2. Verify antenna placement
3. Replace sensor batteries
4. Restart RTL_433: `docker compose restart rtl433`

---

## Performance Benchmarks

Expected system performance:

| Metric | Expected Value |
|--------|----------------|
| Data points/day | ~8,640 (with dual modulation) |
| InfluxDB disk usage | ~2-3 MB/day (compressed) |
| Dashboard load time | < 3 seconds |
| Query response time | < 500ms for 24h range |
| Memory usage (total) | < 1 GB |
| CPU usage (idle) | < 10% |

If your system significantly deviates from these benchmarks, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).
