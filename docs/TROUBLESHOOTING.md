# Troubleshooting Guide

Common issues and their solutions for the weather station server.

## Table of Contents

- [Container Issues](#container-issues)
- [MQTT Issues](#mqtt-issues)
- [InfluxDB Issues](#influxdb-issues)
- [Telegraf Issues](#telegraf-issues)
- [Grafana Issues](#grafana-issues)
- [RTL_433 Issues](#rtl_433-issues)
- [Timezone Issues](#timezone-issues)
- [Performance Issues](#performance-issues)

---

## Container Issues

### Services Won't Start

**Symptom**: `docker compose up -d` fails or containers exit immediately.

**Diagnosis**:
```bash
docker compose ps  # Check status
docker compose logs <service-name>  # Check specific service logs
```

**Common Causes**:

1. **Port Already in Use**
   ```bash
   # Check what's using ports 1883, 8086, 3000
   netstat -ano | findstr ":1883"  # Windows
   lsof -i :1883  # Linux/Mac
   ```
   **Solution**: Stop conflicting service or change port in `docker-compose.yml`

2. **Permission Denied** (Linux)
   **Solution**: Run with sudo or add user to docker group:
   ```bash
   sudo usermod -aG docker $USER
   newgrp docker
   ```

3. **Invalid Environment Variables**
   ```bash
   docker compose config  # Validate docker-compose.yml
   ```
   **Solution**: Check `.env` file exists and has valid values

4. **Insufficient Resources**
   **Solution**: Increase Docker Desktop memory/CPU limits in settings

### Container Keeps Restarting

**Symptom**: Container shows `Restarting` status.

**Diagnosis**:
```bash
docker logs <container-name> --tail 100
```

**Solutions**:
- **InfluxDB**: Wait 30-60 seconds for initialization on first run
- **Telegraf**: Check token in `.env` matches InfluxDB token
- **RTL_433**: Verify USB device passthrough is correct

---

## MQTT Issues

### Messages Not Reaching Docker Container (Windows)

**Symptom**: `mosquitto_pub -h 127.0.0.1` connects but messages don't appear in `docker logs mqtt-broker`.

**Cause**: Another Mosquitto broker running on host intercepts connections.

**Diagnosis**:
```powershell
netstat -ano | findstr ":1883"
tasklist | findstr mosquitto
```

**Solution**: Stop host Mosquitto service:
```powershell
net stop mosquitto
sc config mosquitto start= disabled
```

**Verification**:
```bash
mosquitto_pub -h 127.0.0.1 -p 1883 -t "test/topic" -m "test"
docker logs mqtt-broker --tail 10
```

### RTL_433 Can't Connect to MQTT

**Symptom**: RTL_433 shows "Connection refused" or times out.

**Diagnosis**:
```bash
# Test MQTT broker is reachable
telnet <SERVER_IP> 1883  # Should connect
nc -zv <SERVER_IP> 1883  # Alternative test
```

**Solutions**:

1. **Wrong IP Address**
   - Use `localhost` or `127.0.0.1` if RTL_433 on same machine
   - Use server's LAN IP (e.g., `192.168.1.100`) if RTL_433 on different machine
   - Find IP: `ipconfig` (Windows) or `hostname -I` (Linux)

2. **Firewall Blocking Port 1883**
   ```powershell
   # Windows: Allow inbound connections
   New-NetFirewallRule -DisplayName "MQTT" -Direction Inbound -Protocol TCP -LocalPort 1883 -Action Allow
   ```
   ```bash
   # Linux
   sudo ufw allow 1883/tcp
   ```

3. **Docker Network Mode**
   - If using `network_mode: host`, connect to `localhost:1883`
   - If using bridge mode (default), connect to host IP on port 1883

### MQTT Authentication Failures

**Symptom**: "Connection refused" or "Not authorized" when connecting.

**Diagnosis**: Check Mosquitto config:
```bash
docker exec -it mqtt-broker cat /mosquitto/config/mosquitto.conf
```

**Solutions**:

1. **Anonymous Access Disabled**
   Edit `mosquitto/config/mosquitto.conf`:
   ```
   allow_anonymous true
   ```
   Restart: `docker compose restart mosquitto`

2. **Password File Missing**
   ```bash
   # Create password file
   docker exec -it mqtt-broker mosquitto_passwd -c /mosquitto/config/passwd <username>
   ```

   Update `mosquitto.conf`:
   ```
   password_file /mosquitto/config/passwd
   ```

---

## InfluxDB Issues

### No Data in InfluxDB

**Symptom**: Data Explorer shows empty results.

**Diagnosis Steps**:

1. **Check Telegraf is writing**:
   ```bash
   docker compose logs telegraf | grep "Wrote batch"
   ```
   Should show regular writes every 10-20 seconds.

2. **Verify bucket exists**:
   ```bash
   docker exec influxdb influx bucket list --org weather
   ```

3. **Query directly**:
   ```bash
   docker exec influxdb influx query \
     'from(bucket:"weather_data") |> range(start: -1h) |> limit(n: 10)' \
     --org weather --raw
   ```

**Solutions**:

1. **Wrong Bucket/Organization**
   - Check `.env` values match Telegraf config
   - Verify `INFLUXDB_ORG` and `INFLUXDB_BUCKET` are consistent

2. **Invalid Token**
   - Regenerate token in InfluxDB UI: **Data** → **API Tokens**
   - Update `INFLUXDB_ADMIN_TOKEN` in `.env`
   - Restart Telegraf: `docker compose restart telegraf`

3. **Topic Mismatch**
   - Check RTL_433 publishes to: `rtl_433/Vevor-7in1/3092`
   - Check Telegraf subscribes to: `rtl_433/Vevor-7in1/+`
   - Verify with: `docker exec -it mqtt-broker mosquitto_sub -t "rtl_433/#" -v`

### "Unauthorized" Error

**Symptom**: InfluxDB returns 401 Unauthorized.

**Cause**: Invalid or expired token.

**Solution**:
1. Login to InfluxDB UI (http://localhost:8086)
2. Go to **Data** → **API Tokens**
3. Copy the admin token
4. Update `.env`:
   ```
   INFLUXDB_ADMIN_TOKEN=<new-token>
   ```
5. Restart services:
   ```bash
   docker compose restart telegraf grafana
   ```

### Database Fills Up Disk

**Symptom**: Disk space running low.

**Diagnosis**:
```bash
docker exec influxdb du -sh /var/lib/influxdb2
```

**Solutions**:

1. **Set Retention Policy**
   ```bash
   # Keep only 30 days of data
   docker exec influxdb influx bucket update \
     --name weather_data \
     --retention 720h \
     --org weather
   ```

2. **Delete Old Data**
   ```bash
   # Delete data older than 90 days
   docker exec influxdb influx delete \
     --bucket weather_data \
     --start 1970-01-01T00:00:00Z \
     --stop $(date -d '90 days ago' -Iseconds) \
     --org weather
   ```

3. **Reduce Sampling Rate**
   - Increase RTL_433 transmission interval (if supported)
   - Use Telegraf aggregation before storage
   - Downsample old data with InfluxDB tasks

---

## Telegraf Issues

### Telegraf Not Writing to InfluxDB

**Symptom**: Telegraf logs show MQTT messages but no writes to InfluxDB.

**Diagnosis**:
```bash
docker compose logs telegraf | grep -A 5 -B 5 "error"
```

**Common Errors**:

1. **"connection refused"**
   - InfluxDB not ready yet (wait 30 seconds after startup)
   - Wrong URL in `telegraf.conf`: Should be `http://influxdb:8086` (not localhost)

2. **"unauthorized"**
   - Check `INFLUXDB_ADMIN_TOKEN` in `.env`
   - Verify token in InfluxDB UI matches

3. **"bucket not found"**
   - Create bucket in InfluxDB UI or via CLI
   - Ensure bucket name matches `telegraf.conf`

### Starlark Processor Errors

**Symptom**: Derived fields not appearing in InfluxDB.

**Diagnosis**:
```bash
docker compose logs telegraf | grep -i starlark
```

**Common Issues**:

1. **Syntax Error**
   ```
   Error in Starlark script: syntax error at line XX
   ```
   **Solution**: Fix Python-like syntax in `telegraf.conf` Starlark section

2. **Type Error**
   ```
   TypeError: unsupported operand type
   ```
   **Solution**: Check field types (use `.get()` with defaults)

3. **Division by Zero**
   ```
   Error: division by zero
   ```
   **Solution**: Add checks before division:
   ```python
   if time_diff_s > 0:
       rate = value / time_diff_s
   ```

### High Memory Usage

**Symptom**: Telegraf container uses excessive RAM (> 500MB).

**Diagnosis**:
```bash
docker stats telegraf
```

**Solutions**:

1. **Reduce Buffer Size**
   Edit `telegraf.conf`:
   ```toml
   [agent]
     metric_buffer_limit = 1000  # Reduce from 10000
   ```

2. **Disable Debug Mode**
   ```toml
   [agent]
     debug = false
   ```

3. **Clear State** (if Starlark state grows too large)
   ```bash
   docker compose restart telegraf
   ```
   Note: This resets daily rain state.

---

## Grafana Issues

### Dashboards Not Appearing

**Symptom**: No dashboards in Grafana sidebar.

**Diagnosis**:
```bash
# Check provisioning directory
ls -la grafana/provisioning/dashboards/

# Check Grafana logs
docker compose logs grafana | grep -i dashboard
```

**Solutions**:

1. **Provisioning Not Mounted**
   - Verify `docker-compose.yml` has volume mount:
     ```yaml
     volumes:
       - ./grafana/provisioning:/etc/grafana/provisioning
     ```
   - Restart: `docker compose restart grafana`

2. **Invalid JSON**
   - Validate dashboard files:
     ```bash
     cat grafana/provisioning/dashboards/weather-dashboard.json | jq .
     ```
   - Fix JSON syntax errors

3. **Permissions Issue** (Linux)
   ```bash
   sudo chown -R 472:472 grafana/
   ```

### "No Data" in Panels

**Symptom**: Dashboard panels show "No Data" or empty graphs.

**Diagnosis**:

1. **Check Datasource**
   - Go to **Connections** → **Data sources** → **InfluxDB**
   - Click **Save & Test**
   - Should show green "datasource is working"

2. **Check Query**
   - Edit panel → Query tab
   - Click **Query Inspector** → **Refresh**
   - Review error messages

**Solutions**:

1. **Datasource Not Configured**
   - Check `grafana/provisioning/datasources/influxdb.yaml` exists
   - Verify `INFLUXDB_ADMIN_TOKEN` environment variable is set

2. **Wrong Time Range**
   - Try absolute time range: Last 24 hours
   - Data might be sparse for longer ranges

3. **Field Name Typo**
   - Verify field names match InfluxDB:
     ```bash
     docker exec influxdb influx query \
       'import "influxdata/influxdb/schema"
        schema.fieldKeys(bucket: "weather_data")' \
       --org weather --raw
     ```

### Panels Show Duplicate Values

**Symptom**: Each metric shows twice with ASK/FSK labels.

**Cause**: Weather station transmits with dual modulation.

**Solution**: Add to query:
```flux
|> group()
|> keep(columns: ["_time", "_value"])
```

This strips the `mod` tag causing duplication.

### Wrong Timezone Display

**Symptom**: Timestamps are off by several hours.

**Solutions**:

1. **Dashboard Timezone**
   - Click timezone icon (top right)
   - Select "Europe/Madrid" or your local timezone

2. **Browser Timezone**
   - Check browser timezone matches your location
   - Dashboard with `"timezone": "browser"` uses browser setting

3. **Grafana Server Timezone**
   - Add to `docker-compose.yml` under grafana service:
     ```yaml
     environment:
       - TZ=${TZ}
     ```

---

## RTL_433 Issues

### No Signal Received

**Symptom**: RTL_433 logs show no decoded messages.

**Diagnosis**:
```bash
docker compose logs rtl433 --tail 100
```

**Solutions**:

1. **Wrong Frequency**
   - EU weather stations: 868.3 MHz
   - US weather stations: 433.92 MHz
   - Check your model's specifications

2. **Weak Signal**
   - Move RTL-SDR closer to weather station
   - Use external antenna
   - Check weather station batteries

3. **USB Device Not Found**
   ```bash
   # Check USB devices
   lsusb | grep Realtek  # Linux
   ```
   **Solution**: Fix device path in `docker-compose.yml`

4. **Driver Issue**
   - Install RTL-SDR drivers: https://www.rtl-sdr.com/rtl-sdr-quick-start-guide/
   - On Windows: Use Zadig to install WinUSB driver

### CRC Errors

**Symptom**: Logs show frequent checksum errors.

**Diagnosis**:
```
CRC error: calculated XXXX, expected YYYY
```

**Solutions**:
- **Occasional errors**: Normal due to interference
- **Constant errors**:
  - Increase sample rate: `-s 2048k`
  - Adjust frequency: Try ±100kHz from nominal
  - Check antenna connection

### Wrong Device Decoded

**Symptom**: RTL_433 decodes neighbor's weather station.

**Solution**: Filter by device ID in Telegraf:
```toml
[[inputs.mqtt_consumer]]
  topics = ["rtl_433/Vevor-7in1/3092"]  # Your device ID only
```

---

## Timezone Issues

### Daily Rain Doesn't Reset at Midnight

**Symptom**: `daily_rain_current` resets at wrong time or not at all.

**Cause**: Timezone offset in Telegraf Starlark doesn't match local timezone.

**Diagnosis**: Check current timezone offset calculation:
```bash
docker compose logs telegraf | grep "daily_rain"
```

**Solution**: Edit `telegraf/telegraf.conf` line 98:

```python
# For Europe/Madrid (winter UTC+1)
tz_offset = 3600

# For Europe/Madrid (summer UTC+2)
tz_offset = 7200

# For US Eastern (winter UTC-5)
tz_offset = -18000

# For US Eastern (summer UTC-4)
tz_offset = -14400
```

Restart Telegraf:
```bash
docker compose restart telegraf
```

### Monthly Dashboard Dates Off by One Day

**Symptom**: Data from Jan 12 appears on Jan 13.

**Cause**: Aggregation window not aligned with local timezone.

**Solution**: Already fixed with `timeShift(duration: -1h)` in dashboard queries. If still occurring:
1. Verify dashboard timezone is set to "Europe/Madrid"
2. Check all queries include timeShift
3. Confirm timezone matches `.env` TZ setting

### Timestamps in Wrong Timezone

**Symptom**: InfluxDB shows times in UTC instead of local time.

**This is CORRECT**: InfluxDB always stores in UTC.

**Display in Local Time**:
- Grafana: Handles conversion automatically based on dashboard/browser timezone
- CLI queries: Use `--timezone` flag:
  ```bash
  influx query 'from(bucket:"weather_data") |> range(start: -1h)' --timezone Europe/Madrid
  ```

---

## Performance Issues

### Slow Dashboard Loading

**Symptom**: Dashboards take > 5 seconds to load.

**Diagnosis**:
```bash
# Check query performance in Grafana
# Panel menu → Inspect → Stats
```

**Solutions**:

1. **Reduce Time Range**
   - Use relative ranges (Last 24h) instead of absolute
   - Avoid querying > 30 days without aggregation

2. **Optimize Queries**
   - Use `aggregateWindow()` for long ranges
   - Add `limit(n: 1000)` for testing
   - Use `drop()` to remove unused columns early

3. **InfluxDB Performance**
   ```bash
   # Check InfluxDB resource usage
   docker stats influxdb
   ```
   - Increase memory limit in Docker Desktop if needed
   - Consider downsampling old data

### High CPU Usage

**Symptom**: Continuous high CPU usage (> 50%) when idle.

**Diagnosis**:
```bash
docker stats
```

**Solutions**:

1. **Telegraf Debug Mode**
   - Disable debug in `telegraf.conf`:
     ```toml
     debug = false
     ```

2. **Grafana Auto-Refresh**
   - Increase refresh interval from 30s to 1m
   - Disable auto-refresh when not viewing dashboard

3. **Too Many Data Points**
   - Check data point count:
     ```bash
     docker exec influxdb influx query \
       'from(bucket:"weather_data") |> range(start: -24h) |> count()' \
       --org weather --raw
     ```
   - Should be < 10,000/day
   - If higher: Check for duplicate sensors or excessive polling

### Container Out of Memory

**Symptom**: Container killed with OOMKilled status.

**Diagnosis**:
```bash
docker inspect <container-name> | grep -i oom
```

**Solutions**:

1. **Increase Docker Memory**
   - Docker Desktop → Settings → Resources
   - Allocate at least 4GB RAM

2. **Set Memory Limits**
   Add to `docker-compose.yml`:
   ```yaml
   services:
     influxdb:
       mem_limit: 1g
       memswap_limit: 1g
   ```

3. **Clear Old Data** (see InfluxDB section above)

---

## Getting Help

If your issue isn't covered here:

1. **Check Logs**: `docker compose logs <service-name>`
2. **Enable Debug**: Set `debug = true` in relevant config
3. **Search Issues**: Check GitHub issues for rtl_433, Telegraf, InfluxDB, Grafana
4. **Community Forums**:
   - InfluxDB: https://community.influxdata.com/
   - Grafana: https://community.grafana.com/
   - RTL-SDR: https://www.rtl-sdr.com/forum/

When asking for help, include:
- Docker Compose version: `docker compose version`
- Container logs: `docker compose logs`
- Configuration files (redact passwords/tokens)
- Operating system and version
