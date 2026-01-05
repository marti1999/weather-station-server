# Weather Station Server

A complete server-side solution for collecting weather station data via RTL_433, storing it in InfluxDB, and preparing for data visualization and home automation integration.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLIENT SIDE                              │
│  RTL_433 (Windows/Linux) receives 868.3MHz RF signals from       │
│  weather station and publishes to MQTT broker                    │
└─────────────────────────────────┬───────────────────────────────┘
                                  │ MQTT Protocol (TCP/1883)
                                  ▼
        ┌─────────────────────────────────────────────────────────┐
        │              DOCKER CONTAINERS (Server)                  │
        │                                                           │
        │  ┌──────────────┐      ┌──────────────┐                 │
        │  │  Mosquitto   │──────│   Bridge     │                 │
        │  │   (MQTT)     │      │(Python App)  │                 │
        │  └──────────────┘      └──────┬───────┘                 │
        │                               │                          │
        │  ┌──────────────────────────────────────────┐            │
        │  │                                          │            │
        │  ▼                                          │            │
        │  ┌──────────────┐      ┌──────────────┐    │            │
        │  │  InfluxDB    │◄─────│   Future:    │    │            │
        │  │(Time-Series) │      │  - Grafana   │    │            │
        │  └──────────────┘      │  - Home      │    │            │
        │                        │    Assistant │    │            │
        │                        └──────────────┘    │            │
        │                                          │            │
        │  (All containers on shared 'weather-network')           │
        └─────────────────────────────────────────────────────────┘
```

## Prerequisites

- **Docker Desktop** installed (for Windows/Mac) or **Docker + Docker Compose** (for Linux)
- **Python 3.11+** (only needed if running the bridge script locally without Docker)
- Weather station transmitting on 868.3 MHz RF frequency
- Network connectivity between client and server

## Quick Start

### 1. Clone/Download the Repository

```bash
cd weather-station-server-1
```

### 2. Start the Docker Services

```bash
docker-compose up -d
```

This command will:
- Pull the required Docker images (Mosquitto, InfluxDB, Python)
- Create a shared network for container communication
- Start all services in the background

Verify all containers are running:

```bash
docker-compose ps
```

### 3. Access the Services

- **MQTT Broker**: `localhost:1883` or `<server-ip>:1883`
- **MQTT WebSocket**: `localhost:9001` (for web-based clients)
- **InfluxDB API**: `http://localhost:8086/`
  - Note: InfluxDB 1.8 doesn't have a built-in web UI. Use the API directly or install Grafana for visualization.
  - Test the API: `http://localhost:8086/ping` (should return 204 No Content)
  - Query example: See [Querying InfluxDB](#querying-influxdb) section below

### 3.5 Configure Environment Variables (Optional)

The system uses default credentials for development. To customize them:

1. Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

2. Edit `.env` with your values:
```env
MQTT_HOST=mosquitto
MQTT_PORT=1883
INFLUXDB_DB=weather_data
INFLUXDB_USER=admin
INFLUXDB_PASSWORD=your_secure_password
```

3. Restart the services:
```bash
docker-compose up -d
```

**Important**: The `.env` file is ignored by git (see `.gitignore`). Never commit sensitive credentials.

### 4. Set Up Python Virtual Environment (Host Machine)

To run the query script on your host machine (to view stored weather data), you'll need Python with the required packages:

#### **Windows 11:**

```powershell
# Create virtual environment
python -m venv venv

# Activate it
.\venv\Scripts\Activate.ps1

# Install required packages
pip install -r scripts/requirements.txt
```

#### **Linux/Mac:**

```bash
# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate

# Install required packages
pip install -r scripts/requirements.txt
```

#### **Then use the query script:**

```powershell
# View all stored weather data in table format
python scripts/query_influxdb.py
```

The venv folder is ignored by git (see `.gitignore`), so it won't be committed to the repository.

### 5. Configure Client (RTL_433)

#### **Windows 11 - Option 1: Install Mosquitto Client Tools (Recommended)**

1. Download Mosquitto: https://mosquitto.org/download/
2. Install the Windows installer
3. Add to your PATH or use full path: `C:\Program Files\mosquitto\mosquitto_pub.exe`
4. Pipe RTL_433 JSON output to mosquitto_pub:

```cmd
rtl_433.exe -s 1000k -f 868.3M -R 263 -Y classic -M level -X "n=Vevor-YT60234,m=FSK_PCM,s=87,l=87,r=89088,match={96}0c14" -F json | mosquitto_pub -h <YOUR_SERVER_IP> -t rtl_433/devices/Vevor-7in1 -l
```

**Key Points:**
- `-F json` outputs JSON format (required)
- `| mosquitto_pub` pipes the output to MQTT broker
- `-h <YOUR_SERVER_IP>` is the server running Docker
- `-t rtl_433/devices/Vevor-7in1` is the topic name
- `-l` reads each line as a separate message

#### **Windows 11 - Option 2: Use Docker (No Installation)**

Pipe RTL_433 JSON directly through Docker's mosquitto container:

```cmd
rtl_433.exe -s 1000k -f 868.3M -R 263 -Y classic -M level -X "n=Vevor-YT60234,m=FSK_PCM,s=87,l=87,r=89088,match={96}0c14" -F json | docker run --rm -i --net host eclipse-mosquitto mosquitto_pub -h <YOUR_SERVER_IP> -t rtl_433/devices/Vevor-7in1 -l
```

#### **Linux Command:**

```bash
rtl_433 -s 1000k -f 868.3M -R 263 -Y classic -M level -X "n=Vevor-YT60234,m=FSK_PCM,s=87,l=87,r=89088,match={96}0c14" -F json | mosquitto_pub -h <YOUR_SERVER_IP> -t rtl_433/devices/Vevor-7in1 -l
```

Replace `<YOUR_SERVER_IP>` with your server's IP address or hostname.

#### **Testing - Real Vevor-7in1 Data**

Test with actual sensor data:

```powershell
docker exec weather-mosquitto mosquitto_pub -h localhost -t "rtl_433/devices/Vevor-7in1" -m '{"time" : "2026-01-05 18:44:20", "model" : "Vevor-7in1", "id" : 3092, "channel" : 0, "battery_ok" : 1, "temperature_C" : 4.3, "humidity" : 89, "wind_avg_km_h" : 0.0, "wind_max_km_h" : 2.5, "wind_dir_deg" : 90, "rain_mm" : 343.209, "uvi" : 0.0, "light_lux" : 0, "rssi" : -2.327, "snr" : 30.786, "noise" : -33.113}'
```

#### **View Data - Use Query Script**

```powershell
pip install tabulate influxdb
python scripts/query_influxdb.py
```

This displays all measurements in SQL-like table format. This is the EASIEST way to view your data.

#### **Alternative: Docker CLI**

```bash
docker exec weather-influxdb influx -database weather_data -execute 'SELECT * FROM "rtl_433_devices_Vevor-7in1"'

#### **Testing Without RTL_433**

You can test the system using Docker without RTL_433:

```powershell
# Windows PowerShell - simple test data
docker exec weather-mosquitto mosquitto_pub -h localhost -t "rtl_433/devices/TestSensor" -m '{"temperature": 23.1, "humidity": 42, "model": "TestSensor", "battery": "ok", "rssi": -85}'

# Or test with real Vevor-7in1 data
docker exec weather-mosquitto mosquitto_pub -h localhost -t "rtl_433/devices/Vevor-7in1" -m '{"time" : "2026-01-05 18:44:20", "model" : "Vevor-7in1", "id" : 3092, "channel" : 0, "battery_ok" : 1, "temperature_C" : 4.3, "humidity" : 89, "wind_avg_km_h" : 0.0, "wind_max_km_h" : 2.5, "wind_dir_deg" : 90, "rain_mm" : 343.209, "uvi" : 0.0, "light_lux" : 0, "rssi" : -2.327, "snr" : 30.786, "noise" : -33.113}'
```

The data will automatically flow to InfluxDB. Check the bridge logs:
```powershell
docker logs weather-mqtt-bridge
```

## Component Details

### Mosquitto (MQTT Broker)

**Purpose**: Acts as a message broker that receives data from RTL_433 clients and distributes it to subscribers.

**Key Features**:
- Lightweight publish-subscribe messaging
- Supports both standard MQTT (port 1883) and WebSocket (port 9001) protocols
- Persistent message storage (survives restarts)
- Perfect for IoT devices with limited resources

**Configuration File**: `config/mosquitto.conf`
- Anonymous connections allowed (change for production security)
- Persistence enabled at `/mosquitto/data/`
- Logging to both file and stdout

**Default Port**: 1883

### MQTT to InfluxDB Bridge

**Purpose**: Acts as a consumer that listens to MQTT messages and forwards them to InfluxDB with proper formatting.

**How It Works**:
1. Subscribes to `rtl_433/#` topic (receives all RTL_433 data)
2. Parses incoming JSON data from weather station
3. Converts MQTT data into InfluxDB Point format:
   - Numeric values become "fields" (the actual measurements)
   - String/categorical values become "tags" (metadata for querying)
4. Writes points to InfluxDB with timestamps

**Example Data Flow**:
```
MQTT Topic: rtl_433/devices/Vevor-YT60234
Message: {"temperature": 22.5, "humidity": 45, "model": "Vevor", "battery": "ok"}
        ↓
Converts to:
  Measurement: rtl_433_devices
  Fields: temperature=22.5, humidity=45
  Tags: model="Vevor", battery="ok"
  ↓
Stored in InfluxDB for querying and visualization
```

**Script Location**: `scripts/mqtt_influxdb_bridge.py`

### Detailed Data Flow Example

This section shows exactly what happens to your Vevor-7in1 weather station data as it flows through the system.

#### **Input Data - Real Vevor-7in1 Sensor Output**

Your Vevor-7in1 weather station transmits on 868.3 MHz RF. RTL_433 receives it with JSON output:

```json
{"time" : "2026-01-05 18:44:20", "model" : "Vevor-7in1", "id" : 3092, "channel" : 0, "battery_ok" : 1, "temperature_C" : 4.3, "humidity" : 89, "wind_avg_km_h" : 0.0, "wind_max_km_h" : 2.5, "wind_dir_deg" : 90, "rain_mm" : 343.209, "uvi" : 0.0, "light_lux" : 0, "mic" : "CHECKSUM", "mod" : "FSK", "freq1" : 868.402, "freq2" : 868.302, "rssi" : -2.327, "snr" : 30.786, "noise" : -33.113}
```

#### **Step 1: RTL_433 Client**

Location: Your client machine (Windows/Linux running RTL_433)

The command reads RF signals and outputs JSON:
```cmd
rtl_433.exe -s 1000k -f 868.3M -R 263 -Y classic -M level -X "n=Vevor-YT60234,..." -F json
```

Output piped to mosquitto_pub

#### **Step 2: MQTT Publish**

Location: Your client machine (piped to mosquitto_pub)

The JSON is published to the MQTT broker:
```
Topic: rtl_433/devices/Vevor-7in1
Payload: Real-time Vevor-7in1 sensor data in JSON format
```

#### **Step 3: Mosquitto Broker (Docker Container)**

Location: Server, inside `weather-mosquitto` container

- **Receives** the message on topic `rtl_433/devices/Vevor-7in1`
- **Stores** a copy for persistence (survives broker restart)
- **Broadcasts** to all subscribers (the Python Bridge)

#### **Step 4: Python Bridge Processing (Docker Container)**

Location: Server, inside `weather-mqtt-bridge` container

The bridge receives the Vevor-7in1 JSON and **intelligently separates it into FIELDS (measurements) and TAGS (metadata)**:

**Incoming JSON from Vevor-7in1:**
```json
{
  "time": "2026-01-05 18:44:20",
  "model": "Vevor-7in1",
  "id": 3092,
  "channel": 0,
  "battery_ok": 1,
  "temperature_C": 4.3,
  "humidity": 89,
  "wind_avg_km_h": 0.0,
  "wind_max_km_h": 2.5,
  "wind_dir_deg": 90,
  "rain_mm": 343.209,
  "uvi": 0.0,
  "light_lux": 0,
  "rssi": -2.327,
  "snr": 30.786,
  "noise": -33.113,
  "mic": "CHECKSUM",
  "mod": "FSK",
  "freq1": 868.402,
  "freq2": 868.302
}
```

**Smart Processing Logic:**

The bridge knows which fields are **measurements (FIELDS)** and which are **metadata (TAGS)**:

**FIELDS** (Numeric measurements to graph):
- `temperature_C` → 4.3
- `humidity` → 89
- `wind_avg_km_h` → 0.0
- `wind_max_km_h` → 2.5
- `wind_dir_deg` → 90
- `rain_mm` → 343.209
- `uvi` → 0.0
- `light_lux` → 0
- `rssi` → -2.327
- `snr` → 30.786
- `noise` → -33.113
- `battery_ok` → 1

**TAGS** (Metadata for filtering/grouping):
- `model` → "Vevor-7in1"
- `id` → "3092"
- `channel` → "0"
- `mic` → "CHECKSUM"
- `mod` → "FSK"
- `freq1` → "868.402"
- `freq2` → "868.302"

**Measurement Name:** `rtl_433_devices_Vevor-7in1` (derived from MQTT topic)

#### **Step 5: InfluxDB Storage (Docker Container)**

Location: Server, inside `weather-influxdb` container

**InfluxDB Point Created:**

```
Measurement: rtl_433_devices_Vevor-7in1
Tags: {model: "Vevor-7in1", id: "3092", channel: "0", mic: "CHECKSUM", mod: "FSK"}
Fields: {temperature_C: 4.3, humidity: 89, wind_max_km_h: 2.5, rain_mm: 343.209, uvi: 0.0, light_lux: 0, ...}
Timestamp: 2026-01-05T18:44:20Z
```

#### **Viewing the Data**

The EASIEST way to see your data:

```powershell
python scripts/query_influxdb.py
```

This displays all measurements in SQL-like table format, showing temperature, humidity, wind speed, rainfall, UV index, light, signal strength, and more.

**Alternative Methods:**

**Via Docker CLI:**
```powershell
docker exec weather-influxdb influx -database weather_data -execute 'SELECT * FROM "rtl_433_devices_Vevor-7in1" LIMIT 10'
```

**Via HTTP API (PowerShell):**
```powershell
Invoke-WebRequest -Uri "http://localhost:8086/query?db=weather_data&q=SELECT * FROM `"rtl_433_devices_Vevor-7in1`""
```

#### **Query Results Example**

After running the query, you'll see output like:

```
Name: rtl_433_devices_Vevor-7in1

Time                    Temperature  Humidity  Wind Max  Rain MM  UV Index  Light Lux  RSSI   Channel  Model
──────────────────────  ──────────────  ────────  ────────  ────────  ─────────  ──────────  ──────  ────────  ──────────
2026-01-05T18:44:20Z    4.3            89        2.5       343.209  0.0       0          -2.33  0        Vevor-7in1
```

The data is now ready for:
- **Grafana Dashboards**: Real-time visualization
- **Home Assistant Integration**: Automation rules
- **Analysis**: Historical trends, averages, alerts

## Docker Volumes and Data Persistence

Your setup uses three Docker volumes to store persistent data. This is important to understand:

### What are Docker Volumes?

Docker volumes are managed storage locations that persist data even when containers stop. They're **NOT** regular folders you can see in File Explorer.

**Location on Windows:**
```
C:\ProgramData\Docker\volumes\weather-station-server-1_*\
```

You can list them with:
```powershell
docker volume ls
```

And inspect them with:
```powershell
docker volume inspect weather-station-server-1_influxdb_data
```

### The Three Volumes in Your Setup

| Volume | Purpose | Content |
|--------|---------|---------|
| `mosquitto_data` | MQTT Persistence | Stored messages (if broker crashes/restarts) |
| `mosquitto_logs` | MQTT Logs | Broker activity logs for debugging |
| `influxdb_data` | Database Storage | **All your weather measurements** |

### Data Persistence Scenarios

| Scenario | Command | Data Safe? | Notes |
|----------|---------|-----------|-------|
| Stop containers | `docker compose stop` | ✅ YES | Containers pause, volumes remain intact |
| Restart containers | `docker compose start` | ✅ YES | Same data loads automatically |
| Rebuild containers | `docker compose up -d` | ✅ YES | Old containers removed, but volumes persist |
| Remove containers | `docker compose down` | ✅ YES | Containers deleted, volumes remain |
| Delete volumes | `docker compose down -v` | ❌ **DATA LOST** | Volumes deleted permanently - **CAUTION** |

### Important Operations

**Backup your data (InfluxDB):**
```powershell
# Export database as SQL
docker exec weather-influxdb influx -database weather_data -execute 'SELECT * INTO OUTFILE "/tmp/backup.txt" FROM /./'
docker cp weather-influxdb:/tmp/backup.txt ./weather_data_backup.txt
```

**Verify data is safe during restart:**
```powershell
# Stop all containers
docker compose stop

# Check volume still exists
docker volume ls | findstr weather-station

# Restart
docker compose start

# Data is still there!
docker exec weather-influxdb influx -database weather_data -execute 'SHOW MEASUREMENTS'
```

**⚠️ WARNING - Don't do this unless you want to delete all data:**
```powershell
# This deletes all volumes and data!
docker compose down -v
```

## Configuration

### Environment Variables

Edit `docker-compose.yml` to change default settings:

```yaml
INFLUXDB_ADMIN_PASSWORD: "adminpassword"  # Change this!
MQTT_TOPIC: "rtl_433/#"                   # Adjust if using different topic names
INFLUXDB_TOKEN: "weather-token-default"   # Generate secure token
```

### Adding More Weather Stations

1. **RTL_433 Configuration**: Adjust the `-X` parameter for each station:
   ```bash
   rtl_433 -s 1000k -f 868.3M -R 263 -Y classic -M level \
     -X "n=Station1,m=FSK_PCM,s=87,l=87,r=89088,match={96}0c14" \
     -X "n=Station2,m=FSK_PCM,s=87,l=87,r=89088,match={96}0c15"
   ```

2. **MQTT Topic**: Publish each station to its own topic:
   ```bash
   rtl_433... | mosquitto_pub -h <SERVER_IP> -t rtl_433/devices/Station1 -l
   ```

3. The bridge will automatically handle multiple topics.

## Monitoring & Debugging

### View Container Logs

```bash
# All containers
docker-compose logs

# Specific container
docker-compose logs mosquitto          # MQTT broker logs
docker-compose logs influxdb           # InfluxDB logs
docker logs weather-mqtt-bridge        # Bridge logs
```

### MQTT Testing

Check if data is being received:

**Using Docker (no installation needed):**
```powershell
# Subscribe to all MQTT topics
docker exec weather-mosquitto mosquitto_sub -h localhost -t "rtl_433/#"
```

**Using Mosquitto client (if installed):**
```bash
mosquitto_sub -h localhost -t "rtl_433/#"
```

### Querying InfluxDB

**Using Query Script (RECOMMENDED - Easiest Method):**

```powershell
# From your host machine (with venv activated)
python scripts/query_influxdb.py
```

This shows all data in SQL-like table format.

**Using HTTP API (Windows PowerShell):**

```powershell
# Check InfluxDB is running
Invoke-WebRequest -Uri "http://localhost:8086/ping" -Method Head -UseBasicParsing

# List all measurements
Invoke-WebRequest -Uri 'http://localhost:8086/query?db=weather_data&q=SHOW MEASUREMENTS' -UseBasicParsing | Select-Object -ExpandProperty Content

# Query recent Vevor-7in1 data
$query = 'SELECT * FROM "rtl_433_devices_Vevor-7in1" LIMIT 5'
$encoded = [System.Web.HttpUtility]::UrlEncode($query)
$response = Invoke-WebRequest -Uri "http://localhost:8086/query?db=weather_data&q=$encoded" -UseBasicParsing
$response.Content | ConvertFrom-Json | ConvertTo-Json -Depth 10
```

**Using Docker CLI:**

```powershell
# Get last 5 measurements (note: measurement names with dashes MUST be quoted)
docker exec weather-influxdb influx -database weather_data -execute 'SELECT * FROM "rtl_433_devices_Vevor-7in1" LIMIT 5'

# Calculate average temperature from last hour
docker exec weather-influxdb influx -database weather_data -execute 'SELECT MEAN(temperature_C) FROM "rtl_433_devices_Vevor-7in1" WHERE time > now() - 1h'

# List all fields in a measurement
docker exec weather-influxdb influx -database weather_data -execute 'SHOW FIELD KEYS FROM "rtl_433_devices_Vevor-7in1"'

# List all tags in a measurement
docker exec weather-influxdb influx -database weather_data -execute 'SHOW TAG KEYS FROM "rtl_433_devices_Vevor-7in1"'
```

**Example Output:**

```
name: rtl_433_devices_Vevor-7in1
time                battery_ok channel humidity id   light_lux model      noise   rain_mm rssi   snr    temperature_C
----                ---------- ------- -------- --   --------- ------     -----   ------- ----   ---    ------------- 
1767638660000000000 1          0       89       3092 0         Vevor-7in1 -33.113 343.209 -2.327 30.786 4.3
```

**Important Note about Docker CLI Queries:**
- Measurement names containing dashes (like `rtl_433_devices_Vevor-7in1`) **MUST** be quoted with double quotes
- Without quotes, InfluxDB will try to parse the dash as a minus operator
- Always use: `'SELECT * FROM "rtl_433_devices_Vevor-7in1"'` not `'SELECT * FROM rtl_433_devices_Vevor-7in1'`

## Security Considerations

⚠️ **Current Setup for Development Only**

For production deployment:

1. **MQTT Authentication**:
   - Enable username/password in `mosquitto.conf`
   - Use TLS/SSL encryption (mosquitto.conf: `listener 8883 tls`)

2. **InfluxDB**:
   - Change default admin password
   - Create service accounts with specific permissions
   - Enable TLS/SSL

3. **Network**:
   - Don't expose ports directly to the internet
   - Use VPN or private network
   - Implement firewall rules

4. **Example Mosquitto Config for Auth**:
   ```
   listener 1883
   password_file /mosquitto/config/passwd
   require_certificate false
   ```

## Future Enhancements

This setup is designed to easily add:

### Grafana (Data Visualization)
```yaml
grafana:
  image: grafana/grafana:latest
  ports:
    - "3000:3000"
  depends_on:
    - influxdb
  networks:
    - weather-network
```

### Home Assistant (Home Automation)
```yaml
home-assistant:
  image: homeassistant/home-assistant:latest
  volumes:
    - ./config/home-assistant:/config
  ports:
    - "8123:8123"
  networks:
    - weather-network
```

Both will be able to connect to the shared `weather-network` and access MQTT/InfluxDB.

## Troubleshooting

### Containers won't start
```bash
# Check logs
docker-compose logs

# Rebuild images
docker-compose build --no-cache

# Reset (WARNING: deletes data)
docker-compose down -v
docker-compose up -d
```

### No data appearing in InfluxDB
1. Check MQTT data is arriving: `mosquitto_sub -h localhost -t "rtl_433/#"`
2. Check bridge logs: `docker logs weather-mqtt-bridge`
3. Verify InfluxDB token is correct in `docker-compose.yml`

### MQTT Connection Refused
1. Check if Mosquitto is running: `docker-compose ps`
2. Test connection: `mosquitto_pub -h localhost -t test -m "hello"`
3. Check firewall rules (port 1883)

### High CPU/Memory Usage
- InfluxDB: Large number of unique tags can cause issues
- Monitor with: `docker stats`

## Performance Tips

1. **Reduce MQTT Message Frequency**: Adjust RTL_433 transmit interval
2. **Enable InfluxDB Retention Policies**: Delete old data automatically
3. **Use Tags Wisely**: Keep number of unique tag combinations low
4. **Batch Writes**: The bridge batches multiple readings together

## Additional Resources

- [Mosquitto Documentation](https://mosquitto.org/documentation/)
- [InfluxDB Documentation](https://docs.influxdata.com/influxdb/latest/)
- [RTL_433 Project](https://github.com/merbanan/rtl_433)
- [MQTT Specification](https://mqtt.org/)

## Quick Troubleshooting

### System Not Working?

**1. Check if Docker is running:**
```powershell
docker ps
```

If you get "cannot connect to Docker daemon", start Docker Desktop.

**2. Containers not running?**
```powershell
docker compose up -d
```

**3. No data appearing in InfluxDB?**

Check if MQTT is receiving data:
```powershell
docker exec weather-mosquitto mosquitto_sub -h localhost -t "rtl_433/#" -C 1
```

If you see messages, check the bridge logs:
```powershell
docker logs weather-mqtt-bridge
```

**4. InfluxDB says 404 Error?**

InfluxDB 1.8 doesn't have a web UI. Use the API or install Grafana:
```powershell
# Test API
Invoke-WebRequest http://localhost:8086/ping

# Query data via CLI
docker exec weather-influxdb influx -database weather_data -execute 'SHOW MEASUREMENTS'
```

**5. Can't find docker compose files?**

They're stored in Docker volumes, not as regular folders:
```powershell
docker volume ls
docker volume inspect weather-station-server-1_influxdb_data
```

**6. Lost data / need to reset?**

⚠️ **WARNING**: This deletes all data!
```powershell
docker compose down -v
docker compose up -d
```

### Common Questions

**Q: How do I stop the system without losing data?**
```powershell
docker compose stop  # Pauses containers, keeps data
docker compose start # Resumes with all data intact
```

**Q: How do I see logs?**
```powershell
docker compose logs -f           # All containers
docker logs -f weather-mqtt-bridge    # Just the bridge
docker logs -f weather-influxdb       # Just InfluxDB
```

**Q: How do I add more weather stations?**

Just publish to different MQTT topics:
```powershell
# Station 1
mosquitto_pub -h localhost -t "rtl_433/devices/Station1" -m '{"temperature": 20, "humidity": 45}'

# Station 2  
mosquitto_pub -h localhost -t "rtl_433/devices/Station2" -m '{"temperature": 22, "humidity": 48}'
```

Each creates a separate measurement in InfluxDB automatically.

## License

This project is provided as-is for personal use.

---

**Last Updated**: January 5, 2026
**Status**: ✅ Tested and Working - All 3 containers running, data flowing correctly to InfluxDB