# Weather Station Server - MQTT + InfluxDB

A Docker-based server setup to receive weather station data from RTL_433, store it in InfluxDB via MQTT, with the ability to add Grafana and Home Assistant later.

## Architecture Overview

```
RTL_433 (Client) --> MQTT Broker (Mosquitto) --> Telegraf --> InfluxDB
                                                                  |
                                                           (Future: Grafana)
                                                           (Future: Home Assistant)
```

### What Each Component Does

1. **RTL_433 (Client Side)**: Receives radio signals from your weather station and publishes JSON data to MQTT
2. **Mosquitto**: MQTT broker that receives and distributes messages
3. **Telegraf**: Subscribes to MQTT topics and writes data to InfluxDB
4. **InfluxDB**: Time-series database that stores all weather measurements

## Prerequisites

### Server Side
- Docker Desktop installed (Windows 11 or Linux)
- Docker Compose installed (included with Docker Desktop)

### Client Side (Where RTL_433 runs)
- RTL_433 installed
- Network access to the server's IP address

## Quick Start

### 1. Configure Environment Variables

**IMPORTANT: First time setup**

Copy the example environment file and update with your own secure credentials:

```bash
cp .env.example .env
```

Then edit `.env` and change the default passwords and tokens:

```bash
# Generate a secure password
openssl rand -base64 32

# Or on Windows PowerShell
-join ((48..57) + (65..90) + (97..122) | Get-Random -Count 32 | ForEach-Object {[char]$_})
```

Update these values in `.env`:
- `INFLUXDB_ADMIN_PASSWORD` - Change from default
- `INFLUXDB_ADMIN_TOKEN` - Use a secure random string

**Security Note**: The `.env` file contains sensitive credentials and is excluded from git via `.gitignore`.

### 2. Start the Server Stack

Navigate to the project directory and start all services:

```bash
cd C:\Users\mcaix\Documents\weather_station_server_claude
docker-compose up -d
```

This will start:
- Mosquitto MQTT broker on port 1883
- InfluxDB on port 8086
- Telegraf (runs in background, no exposed ports)

### 2. Verify Services Are Running

```bash
docker-compose ps
```

All services should show status "Up".

### 3. Access InfluxDB Web UI

Open your browser and go to: http://localhost:8086

Login credentials:
- Username: `admin`
- Password: `adminpassword123`
- Organization: `weather`
- Bucket: `weather_data`

## Running RTL_433 Client and Publishing to MQTT

RTL_433 has **built-in MQTT support**, so you don't need pipes or mosquitto_pub!

### On Windows (Client Machine)

Replace `<SERVER_IP>` with your server's IP address (use `127.0.0.1` or `localhost` if running on the same machine):

```bash
rtl_433 -s 1000k -f 868.3M -R 263 -Y classic -M level \
  -X "n=Vevor-YT60234,m=FSK_PCM,s=87,l=87,r=89088,match={96}0c14" \
  -F "mqtt://<SERVER_IP>:1883,retain=0,events=rtl_433[/model][/id]"
```

**Example for localhost:**
```bash
rtl_433 -s 1000k -f 868.3M -R 263 -Y classic -M level \
  -X "n=Vevor-YT60234,m=FSK_PCM,s=87,l=87,r=89088,match={96}0c14" \
  -F "mqtt://127.0.0.1:1883,retain=0,events=rtl_433[/model][/id]"
```

### On Linux (Client Machine)

```bash
rtl_433 -s 1000k -f 868.3M -R 263 -Y classic -M level \
  -X "n=Vevor-YT60234,m=FSK_PCM,s=87,l=87,r=89088,match={96}0c14" \
  -F "mqtt://<SERVER_IP>:1883,retain=0,events=rtl_433[/model][/id]"
```

### MQTT Output Format Explanation

The `-F` flag configures RTL_433 to publish to MQTT:
- `mqtt://<SERVER_IP>:1883` - MQTT broker address and port
- `retain=0` - Don't retain messages (only send live data)
- `events=rtl_433[/model][/id]` - Dynamic topic structure where:
  - `[/model]` is replaced with the device model name (e.g., `/Vevor-7in1`)
  - `[/id]` is replaced with the device ID (e.g., `/3092`)
  - **Example topic**: `rtl_433/Vevor-7in1/3092` for a Vevor-7in1 sensor with ID 3092

**Note**: The square brackets `[]` are placeholders that rtl_433 replaces at runtime. Do NOT remove them from the command.

### Alternative: Simple Topic Structure

If you prefer a simpler single-topic structure, use:

```bash
-F "mqtt://<SERVER_IP>:1883,retain=0,events=rtl_433/events"
```

This publishes all data to a single topic: `rtl_433/events`

## Testing the Data Flow

### 1. Monitor MQTT Messages

Install an MQTT client to view messages:

```bash
# Using mosquitto_sub (if installed)
mosquitto_sub -h localhost -t "rtl_433/#" -v

# Or use Docker
docker exec -it mqtt-broker mosquitto_sub -t "rtl_433/#" -v
```

You should see JSON messages from your weather station.

### 2. Check InfluxDB Data

1. Go to http://localhost:8086
2. Click "Data Explorer" (icon on the left sidebar)
3. Select bucket: `weather_data`
4. You should see measurements from your weather station

### 3. Check Telegraf Logs

```bash
docker-compose logs -f telegraf
```

You should see messages being processed.

## Configuration Details

### Credentials Management

**All sensitive credentials are stored in `.env` file** (not tracked in git).

**InfluxDB:**
- URL: http://localhost:8086
- Username: Set in `INFLUXDB_ADMIN_USERNAME` (default: `admin`)
- Password: Set in `INFLUXDB_ADMIN_PASSWORD` (**change this!**)
- Organization: Set in `INFLUXDB_ORG` (default: `weather`)
- Bucket: Set in `INFLUXDB_BUCKET` (default: `weather_data`)
- Token: Set in `INFLUXDB_ADMIN_TOKEN` (**change this!**)

**MQTT:**
- URL: mqtt://localhost:1883
- No authentication (anonymous allowed)
- To add authentication, edit `mosquitto/config/mosquitto.conf`

**IMPORTANT**:
- Never commit `.env` file to git (already in `.gitignore`)
- Change default passwords before production use
- Use `.env.example` as a template for new installations

### Modifying Configurations

#### Change MQTT Topics

Edit [telegraf/telegraf.conf](telegraf/telegraf.conf) and modify the `topics` array:

```toml
topics = [
  "rtl_433/+/events",
  "rtl_433/#"
]
```

#### Change InfluxDB Credentials

1. Edit [docker-compose.yml](docker-compose.yml) and modify the environment variables
2. Update the token in [telegraf/telegraf.conf](telegraf/telegraf.conf)

#### Enable MQTT Authentication

Edit [mosquitto/config/mosquitto.conf](mosquitto/config/mosquitto.conf) and change:

```
allow_anonymous false
password_file /mosquitto/config/passwd
```

Then create a password file:

```bash
docker exec -it mqtt-broker mosquitto_passwd -c /mosquitto/config/passwd <username>
```

## Managing the Stack

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f mosquitto
docker-compose logs -f influxdb
docker-compose logs -f telegraf
```

### Stop Services

```bash
docker-compose stop
```

### Restart Services

```bash
docker-compose restart
```

### Stop and Remove Everything

```bash
docker-compose down
```

### Stop and Remove Including Data

```bash
docker-compose down -v
```

## Adding Grafana (Future)

To add Grafana for visualization:

1. Edit [docker-compose.yml](docker-compose.yml)
2. Uncomment the `grafana` service section
3. Uncomment `grafana-data` in the volumes section
4. Run: `docker-compose up -d`
5. Access Grafana at http://localhost:3000 (default login: admin/admin)

## Adding Home Assistant (Future)

To add Home Assistant:

1. Edit [docker-compose.yml](docker-compose.yml)
2. Uncomment the `homeassistant` service section
3. Uncomment `homeassistant-config` in the volumes section
4. Run: `docker-compose up -d`
5. Access Home Assistant at http://localhost:8123

**Note**: Home Assistant uses `network_mode: host` which works differently on Windows vs Linux. On Windows, you may need to change this to bridge mode and adjust port mappings.

## Troubleshooting

### Messages Not Reaching Docker Container (Windows)

**Problem**: `mosquitto_pub -h 127.0.0.1 -p 1883` connects successfully but messages don't appear in the Docker container logs.

**Cause**: Another Mosquitto broker is running on the host machine (Windows service) and intercepting connections to `127.0.0.1:1883`.

**Solution**: Stop the host Mosquitto service before using the Docker container:

```powershell
# Check if Mosquitto is running on the host
netstat -ano | findstr ":1883"

# If you see multiple PIDs, check for mosquitto.exe
tasklist | findstr mosquitto

# Stop the Windows service
net stop mosquitto

# Or disable it permanently
sc config mosquitto start= disabled
```

**Verification**: After stopping the host service, test again:

```bash
# Publish a test message
mosquitto_pub -h 127.0.0.1 -p 1883 -t "rtl_433/test/events" -m "test message"

# Check Docker container logs (should show the message)
docker logs mqtt-broker --tail 20
```

### RTL_433 Can't Connect to MQTT

- Verify server IP address is correct
- Check firewall allows port 1883
- Test with: `telnet <SERVER_IP> 1883`
- Ensure no other MQTT broker is running on the same port (see above)

### No Data in InfluxDB

1. Check MQTT broker is receiving data:
   ```bash
   docker exec -it mqtt-broker mosquitto_sub -t "rtl_433/#" -v
   ```

2. Check Telegraf logs:
   ```bash
   docker-compose logs telegraf
   ```

3. Verify topic names match in RTL_433 output and Telegraf config

4. Query InfluxDB directly from command line:

   **Using the helper script (Windows PowerShell - Recommended):**
   ```powershell
   # Query latest temperature data
   .\query_weather.ps1 -Limit 10 -Field "temperature_C"

   # Query humidity data
   .\query_weather.ps1 -Limit 20 -Field "humidity"

   # Available fields: temperature_C, humidity, wind_avg_km_h, wind_dir_deg,
   #                   rain_mm, light_lux, uvi, battery_ok
   ```

   **Using curl directly (Windows PowerShell):**
   ```powershell
   # Note: Use curl.exe to avoid PowerShell alias issues
   # Replace YYYY-MM-DD with actual dates
   curl.exe -s -X POST "http://localhost:8086/api/v2/query?org=weather" `
     -H "Authorization: Token my-super-secret-auth-token" `
     -H "Content-Type: application/vnd.flux" `
     -H "Accept: application/csv" `
     -d "from(bucket:\`"weather_data\`") |> range(start: 2026-01-09T00:00:00Z, stop: 2026-01-09T23:59:59Z) |> filter(fn: (r) => r._field == \`"temperature_C\`") |> limit(n: 10)"
   ```

   **Using bash/Git Bash (Linux or Windows with Git Bash):**
   ```bash
   # Query with absolute timestamps (recommended)
   docker exec influxdb influx query 'from(bucket:"weather_data") |> range(start: 2026-01-09T00:00:00Z, stop: 2026-01-10T00:00:00Z) |> limit(n: 10)' --org weather --token my-super-secret-auth-token
   ```

5. Check all measurements in InfluxDB:
   ```bash
   # List all measurements
   docker exec influxdb influx query 'import "influxdata/influxdb/schema" schema.measurements(bucket:"weather_data")' --org weather --token my-super-secret-auth-token

   # Count total records
   docker exec influxdb influx query 'from(bucket:"weather_data") |> range(start: -24h) |> count()' --org weather --token my-super-secret-auth-token
   ```

### Services Won't Start

- Check Docker is running
- Verify ports 1883, 8086 are not in use by other applications
- Check logs: `docker-compose logs`

## Project Structure

```
weather_station_server_claude/
├── docker-compose.yml           # Main Docker Compose configuration
├── mosquitto/
│   └── config/
│       └── mosquitto.conf       # MQTT broker configuration
├── telegraf/
│   └── telegraf.conf           # Telegraf configuration (MQTT → InfluxDB)
├── .gitignore
└── README.md                    # This file
```

## Network Ports

- **1883**: MQTT (Mosquitto)
- **9001**: MQTT WebSockets (Mosquitto)
- **8086**: InfluxDB Web UI and API
- **3000**: Grafana (when enabled)
- **8123**: Home Assistant (when enabled)

## Data Persistence

Data is persisted in Docker volumes:
- `influxdb-data`: All time-series data
- `influxdb-config`: InfluxDB configuration
- `mosquitto/data`: MQTT persistence
- `mosquitto/log`: MQTT logs

These volumes survive container restarts but will be deleted with `docker-compose down -v`.

## Cross-Platform Notes

This setup works on both Windows and Linux with Docker. The only difference:

- **Windows**: Use `./rtl_433.exe` and Windows paths
- **Linux**: Use `rtl_433` and Unix paths

The Docker containers run identically on both platforms.

## License

This project configuration is provided as-is for personal use.
