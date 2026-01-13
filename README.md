# Weather Station Server - MQTT + InfluxDB

A Docker-based server setup to receive weather station data from RTL_433, store it in InfluxDB via MQTT, and visualize with Grafana dashboards.

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Running RTL_433](#running-rtl_433)
- [Configuration Details](#configuration-details)
- [Managing the Stack](#managing-the-stack)
- [Documentation](#documentation)
  - [Data Fields Reference](docs/FIELDS.md) - Raw sensor fields, derived calculations, and dashboard aggregations
  - [Testing Guide](docs/TESTING.md) - Verification procedures and data flow testing
  - [Troubleshooting Guide](docs/TROUBLESHOOTING.md) - Common issues and solutions
  - [Security Guide](docs/SECURITY.md) - Production hardening and best practices
  - [Grafana Dashboards](docs/GRAFANA.md) - Dashboard guides and customization
- [Project Structure](#project-structure)
- [Network Ports](#network-ports)
- [Data Persistence](#data-persistence)

## Architecture Overview

```
RTL_433 (Docker) --> MQTT Broker (Mosquitto) --> Telegraf --> InfluxDB --> Grafana
```

### What Each Component Does

1. **RTL_433**: Dockerized RTL-SDR receiver that decodes 433/868MHz radio signals from weather stations and publishes JSON data to MQTT
2. **Mosquitto**: MQTT broker that receives and distributes messages
3. **Telegraf**: Subscribes to MQTT topics and writes data to InfluxDB
4. **InfluxDB**: Time-series database that stores all weather measurements
5. **Grafana**: Data visualization and dashboarding platform

## Prerequisites

- Docker Desktop installed (Windows 11 or Linux)
- Docker Compose installed (included with Docker Desktop)
- RTL-SDR USB dongle
- RTL-SDR drivers installed (follow the [RTL-SDR Quick Start Guide](https://www.rtl-sdr.com/rtl-sdr-quick-start-guide/))

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
- `GRAFANA_ADMIN_PASSWORD` - Change from default
- `TZ` - Set your timezone (e.g., `Europe/Madrid`, `America/New_York`, `Asia/Tokyo`)

**Timezone Configuration**:
The `TZ` environment variable is **critical** for correct timestamp handling and daily rain reset timing:
- Sets timezone for RTL_433 timestamp formatting
- Used by Telegraf for parsing JSON timestamps
- Controls when daily rain counters reset (midnight in your local timezone)

Use standard IANA timezone format (e.g., `Europe/Madrid`, `America/New_York`, `Asia/Tokyo`).

**Important Limitation**: The Telegraf Starlark processor has a hardcoded timezone offset (currently set to UTC+1 for Europe/Madrid winter). When DST changes occur, you must manually update the `tz_offset` variable in [telegraf/telegraf.conf](telegraf/telegraf.conf) line 98. See [FIELDS.md](docs/FIELDS.md#timezone-configuration) for detailed instructions.

**Security Note**: The `.env` file contains sensitive credentials and is excluded from git via `.gitignore`.

### 2. Start the Server Stack

Navigate to the project directory and start all services:

```bash
docker compose up -d
```

This will start:
- RTL_433 receiver (connects to your RTL-SDR USB device)
- Mosquitto MQTT broker on port 1883
- InfluxDB on port 8086
- Telegraf (runs in background, no exposed ports)
- Grafana dashboard on port 3000

### 3. Verify Services Are Running

```bash
docker compose ps
```

All services should show status "Up".

### 4. Access InfluxDB Web UI

Open your browser and go to: http://localhost:8086

Login credentials:
- Username: `admin`
- Password: Value of `INFLUXDB_ADMIN_PASSWORD` from `.env`
- Organization: `weather`
- Bucket: `weather_data`

## Running RTL_433

RTL_433 has **built-in MQTT support** to publish decoded sensor data directly to your MQTT broker. You have three deployment options depending on your setup.

### Prerequisites for All Options

**RTL-SDR drivers must be installed** wherever the RTL-SDR dongle is physically connected. Follow the [RTL-SDR Quick Start Guide](https://www.rtl-sdr.com/rtl-sdr-quick-start-guide/) for your platform.

### Deployment Options

Choose one of the following options based on where your RTL-SDR dongle is located:

#### Option 1: Inside Docker Container (Recommended if RTL-SDR is on the same machine as Docker)

The Docker Compose stack includes an rtl_433 container. This is the easiest option if your RTL-SDR dongle is physically connected to the machine running Docker.

**Setup:**

1. **USB Device Access**: By default, all USB devices are accessible to the rtl_433 container via `privileged: true` in [docker compose.yml](docker compose.yml). This works on most systems without additional configuration.

   **Optional - Restrict to specific USB device**: If you want to expose only one USB device instead of all:
   - **Linux**: Run `lsusb` to find bus and device numbers (e.g., Bus 001 Device 007 → `/dev/bus/usb/001/007`)
   - Update [docker compose.yml](docker compose.yml):
     ```yaml
     rtl433:
       # Comment out or remove the privileged line
       # privileged: true
       devices:
         - "/dev/bus/usb/001/007:/dev/bus/usb/001/007"  # Your specific device
     ```

2. **Update the device filter** in [docker compose.yml](docker compose.yml) under the rtl_433 `command` section:

   The critical parameter is the `-X` flag with the `match={96}0c14` filter:
   ```yaml
   command: >
     -X "n=Vevor-YT60234,m=FSK_PCM,s=87,l=87,r=89088,match={96}0c14"
   ```

   **Important**: The `match={96}0c14` ensures only messages from your specific weather station (device ID `0c14`) are decoded. This prevents interference from neighbor's devices on the same frequency. Update `0c14` to match your station's ID (visible in raw RTL_433 output).

3. Start the stack: `docker compose up -d`

**Advantages**: No manual rtl_433 commands needed, automatic restart, integrated with Docker stack

#### Option 2: On the Same Machine as Docker (Outside Container)

Run rtl_433 directly on the host machine where Docker is running.

**Setup:**

1. **Disable the rtl_433 container** in [docker compose.yml](docker compose.yml) by commenting it out or removing the service definition.

2. **Run rtl_433 manually** with the device filter:

   ```bash
   rtl_433 -s 1000k -f 868.3M -R 263 -Y classic -M level \
     -X "n=Vevor-YT60234,m=FSK_PCM,s=87,l=87,r=89088,match={96}0c14" \
     -F "mqtt://localhost:1883,retain=0,events=rtl_433[/model][/id]"
   ```

   **Important**: The `match={96}0c14` filter ensures only your weather station (device ID `0c14`) is decoded, preventing interference from neighbor's devices. Update `0c14` to your station's ID.

**MQTT Broker Address**: Use `localhost` or `127.0.0.1` since the MQTT broker is running on the same machine.

**Advantages**: Simpler troubleshooting, no USB passthrough needed, easier to see rtl_433 output directly

#### Option 3: On a Different Machine (Client Machine)

Run rtl_433 on a separate machine (e.g., a Raspberry Pi near your antenna) and send data over the network to your Docker server.

**Setup:**

1. **Disable the rtl_433 container** in [docker compose.yml](docker compose.yml) on the Docker server by commenting it out or removing the service definition.

2. **Run rtl_433 on the remote machine** with the device filter:

   ```bash
   rtl_433 -s 1000k -f 868.3M -R 263 -Y classic -M level \
     -X "n=Vevor-YT60234,m=FSK_PCM,s=87,l=87,r=89088,match={96}0c14" \
     -F "mqtt://192.168.0.50:1883,retain=0,events=rtl_433[/model][/id]"
   ```

   **Important**: The `match={96}0c14` filter ensures only your weather station (device ID `0c14`) is decoded, preventing interference from neighbor's devices. Update `0c14` to your station's ID.

**MQTT Broker Address**: Use the IP address of the machine running Docker (e.g., `192.168.0.50`). Find it with:
- **Linux**: `ip addr` or `hostname -I`
- **Windows**: `ipconfig` (look for IPv4 Address)

**Advantages**: RTL-SDR can be located near your antenna for better reception, separates processing load

### Command Parameters Explained

```bash
rtl_433 -s 1000k -f 868.3M -R 263 -Y classic -M level \
  -X "n=Vevor-YT60234,m=FSK_PCM,s=87,l=87,r=89088,match={96}0c14" \
  -F "mqtt://192.168.0.50:1883,retain=0,events=rtl_433[/model][/id]"
```

**Radio Parameters:**
- `-s 1000k` - Sample rate (1000 kHz)
- `-f 868.3M` - Frequency (868.3 MHz for EU; use 433.92M for US)
- `-R 263` - Protocol 263 (Vevor 7-in-1 weather station)
- `-Y classic` - Output format style
- `-M level` - Message level filtering
- `-X "..."` - Custom decoder for specific device model

**MQTT Parameters (`-F` flag):**
- `mqtt://192.168.0.50:1883` - MQTT broker address and port
  - Use `localhost` or `127.0.0.1` if running on the same machine as Docker
  - Use the server's IP address (e.g., `192.168.0.50`) if running on a different machine
- `retain=0` - Don't retain messages (only send live data)
- `events=rtl_433[/model][/id]` - Dynamic topic structure
  - `[/model]` is replaced with device model (e.g., `Vevor-7in1`)
  - `[/id]` is replaced with device ID (e.g., `3092`)
  - **Example topic**: `rtl_433/Vevor-7in1/3092`
  - **Note**: Square brackets `[]` are placeholders - do NOT remove them

**Alternative Topic Structure**: For a simpler single-topic approach, use:
```bash
-F "mqtt://192.168.0.50:1883,retain=0,events=rtl_433/events"
```

## Testing and Verification

After starting the stack, verify that data is flowing correctly through all components. See the [Testing Guide](docs/TESTING.md) for detailed verification procedures including:

- Monitoring MQTT messages
- Checking InfluxDB data storage
- Validating Telegraf processing
- Verifying Grafana dashboards
- Performance benchmarks

Quick verification:
```bash
# Monitor MQTT messages
docker exec -it mqtt-broker mosquitto_sub -t "rtl_433/#" -v

# Check Telegraf logs
docker compose logs -f telegraf
```

Then access InfluxDB at http://localhost:8086 and Grafana at http://localhost:3000 to verify data.

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

1. Edit `.env` file and modify `INFLUXDB_ADMIN_PASSWORD` and `INFLUXDB_ADMIN_TOKEN`
2. Restart services: `docker compose restart`

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

See the [Security Guide](docs/SECURITY.md) for comprehensive hardening steps.

### Data Fields

The system processes weather station data through multiple stages:

1. **Raw Sensor Fields**: Direct measurements from the weather station (temperature, humidity, wind, rain, UV, light)
2. **Derived Fields**: Calculated by Telegraf Starlark processor before storage:
   - Dew point (Magnus formula)
   - Feels-like temperature (wind chill or heat index)
   - Daily rain tracking (current day accumulation and previous day total)
   - Precipitation rate (5-minute rolling window)
   - Solar radiation (converted from lux)
   - Beaufort wind scale, UV risk level, battery percentage
3. **Dashboard Aggregations**: Calculated on-the-fly in Grafana (daily avg/max/min for monthly trends)

All derived fields are stored in InfluxDB for historical querying and consistency across dashboards.

See the [Data Fields Reference](docs/FIELDS.md) for complete formulas, calculations, and field descriptions.

## Managing the Stack

### View Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f mosquitto
docker compose logs -f influxdb
docker compose logs -f telegraf
```

### Stop Services

```bash
docker compose stop
```

### Restart Services

```bash
docker compose restart
```

### Stop and Remove Everything

```bash
docker compose down
```

### Stop and Remove Including Data

```bash
docker compose down -v
```

## Grafana Dashboards

Grafana is included in the stack and provides two pre-configured dashboards for weather data visualization:

1. **Weather Station Dashboard** - Real-time 24-hour view with all sensors
2. **Weather Monthly Trends** - 30-day historical analysis with daily aggregations

### Access Grafana

Open http://localhost:3000

Login credentials:
- Username: `admin`
- Password: Value of `GRAFANA_ADMIN_PASSWORD` from `.env`

**Important**: Change the default password after first login.

### Available Panels

The dashboards display:
- **Temperature**: Actual, dew point, and feels-like temperature
- **Humidity**: Relative humidity percentage
- **Wind**: Speed, direction, and gusts
- **Precipitation**: Daily accumulation and current rate
- **UV Index**: With color-coded risk levels
- **Solar Radiation**: Calculated from light sensor
- **Pressure**: Barometric pressure (if available)

All dashboards are automatically provisioned from JSON files in `grafana/provisioning/dashboards/` and use the InfluxDB datasource configured via environment variables.

See the [Grafana Dashboards Guide](docs/GRAFANA.md) for detailed information on:
- Dashboard features and customization
- Panel configurations and queries
- Creating custom dashboards
- Troubleshooting visualization issues
- Advanced features (alerts, annotations, variables)

## Adding Home Assistant (Future)

To add Home Assistant:

1. Edit [docker compose.yml](docker compose.yml)
2. Uncomment the `homeassistant` service section
3. Uncomment `homeassistant-config` in the volumes section
4. Run: `docker compose up -d`
5. Access Home Assistant at http://localhost:8123

**Note**: Home Assistant uses `network_mode: host` which works differently on Windows vs Linux. On Windows, you may need to change this to bridge mode and adjust port mappings.

## Troubleshooting

If you encounter issues, see the [Troubleshooting Guide](docs/TROUBLESHOOTING.md) for comprehensive solutions organized by component:

- **Container Issues**: Services won't start, port conflicts, resource limits
- **MQTT Issues**: Messages not reaching broker, connection failures
- **InfluxDB Issues**: No data storage, query errors, retention policies
- **Telegraf Issues**: Processing errors, MQTT subscription problems
- **Grafana Issues**: Dashboard not loading, "No Data" errors, duplicate values
- **RTL_433 Issues**: Device detection, signal quality, decoding errors
- **Timezone Issues**: Daily rain reset timing, timestamp display
- **Performance Issues**: Slow queries, high memory usage

Quick checks:
```bash
# Check all services are running
docker compose ps

# View logs for errors
docker compose logs -f

# Test MQTT connection
docker exec -it mqtt-broker mosquitto_sub -t "rtl_433/#" -v

# Query InfluxDB for recent data
docker exec influxdb influx query 'from(bucket:"weather_data") |> range(start: -1h) |> limit(n: 5)' --org weather --token $INFLUXDB_ADMIN_TOKEN
```

## Project Structure

```
weather-station-server/
├── docker compose.yml           # Main Docker Compose configuration
├── .env                         # Environment variables (credentials, timezone)
├── .env.example                 # Template for environment configuration
├── mosquitto/
│   └── config/
│       └── mosquitto.conf       # MQTT broker configuration
├── telegraf/
│   └── telegraf.conf            # Telegraf configuration with Starlark processor
├── grafana/
│   └── provisioning/
│       ├── dashboards/
│       │   ├── weather-dashboard.json           # Daily historic dashboard
│       │   └── weather-monthly-trends.json      # Monthly aggregations
│       └── datasources/
│           └── influxdb.yml     # InfluxDB datasource configuration
├── docs/
│   ├── FIELDS.md                # Data fields reference (raw, derived, aggregated)
│   ├── TESTING.md               # Testing and verification procedures
│   ├── TROUBLESHOOTING.md       # Common issues and solutions
│   ├── SECURITY.md              # Security hardening guide
│   └── GRAFANA.md               # Dashboard guides and customization
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

These volumes survive container restarts but will be deleted with `docker compose down -v`.

## Documentation

This project includes comprehensive documentation in the [docs/](docs/) folder:

- **[FIELDS.md](docs/FIELDS.md)** - Complete data fields reference covering raw sensor readings, derived calculations (formulas included), and dashboard aggregations
- **[TESTING.md](docs/TESTING.md)** - Step-by-step testing procedures to verify data flow through all components
- **[TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)** - Common issues organized by component with specific solutions and diagnosis commands
- **[SECURITY.md](docs/SECURITY.md)** - Production hardening guide including MQTT authentication, TLS/SSL, firewall rules, and backup procedures
- **[GRAFANA.md](docs/GRAFANA.md)** - Detailed dashboard guides, panel configurations, query examples, customization instructions, and advanced features

## Cross-Platform Support

This setup works on both Windows and Linux with Docker. All services run identically in containers regardless of host OS. The only platform-specific considerations are USB device paths for RTL-SDR (documented in the RTL_433 section above).

## License

This project configuration is provided as-is for personal use.
