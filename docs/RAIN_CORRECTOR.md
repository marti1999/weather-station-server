# Rain Corrector System

The Rain Corrector is an automated system that fixes daily rain tracking data when Telegraf container restarts cause gaps or resets in the `daily_rain_current` field.

## Overview

### Problem
When the Telegraf container restarts, the `daily_rain_current` field resets to 0 instead of maintaining the accumulated daily rainfall. This creates data gaps and inaccurate precipitation tracking.

### Solution
The Rain Corrector uses ground truth data from the `rain_mm` field (cumulative rainfall since sensor reset) to reconstruct accurate daily rainfall values when restarts are detected.

## How It Works

1. **Restart Detection**: Analyzes `daily_rain_current` data for sudden drops to 0 that indicate container restarts
2. **Ground Truth Calculation**: Uses `rain_mm` historical data as the definitive source for rainfall amounts
3. **Full Day Reconstruction**: When ANY restart is detected, reconstructs ALL data points for the entire day
4. **Precipitation Rate Calculation**: Recalculates precipitation rates based on corrected daily rain values

### Key Features
- **Complete Dataset Processing**: Processes all data points (1000+ per day) when reconstruction is needed
- **Ground Truth Accuracy**: Uses sensor's cumulative `rain_mm` data as the authoritative source
- **Automatic Operation**: Runs daily at 00:10 via cron job
- **Comprehensive Logging**: Detailed logs of all corrections and statistics

## Architecture

### Components
- **Docker Container**: `rain-corrector` service defined in `docker-compose.yml`
- **Python Script**: `/app/daily_rain_corrector.py` - Main correction logic
- **Cron Job**: Runs daily at 00:10 (10 minutes after midnight)
- **Log File**: `/var/log/rain_corrector.log` - Execution logs and results

### Data Fields Updated
- `daily_rain_current` - Overwritten with corrected daily rainfall values
- `precipitation_rate_mm_h` - Overwritten with corrected precipitation rates (mm/hour)

**Important**: The corrector overwrites existing field values to maintain dashboard compatibility. It does not create separate corrected fields.

## Monitoring and Maintenance

### Check Service Status
```bash
# Check if rain-corrector container is running
docker ps --filter "name=rain-corrector"

# Check service logs
docker logs rain-corrector

# Check execution logs
docker exec rain-corrector cat /var/log/rain_corrector.log

# Check recent log entries
docker exec rain-corrector tail -n 20 /var/log/rain_corrector.log
```

### View Cron Configuration
```bash
# Check cron job schedule
docker exec rain-corrector crontab -l

# Check cron service status
docker exec rain-corrector service cron status
```

### Monitor InfluxDB Data
```bash
# Check daily rain data for recent corrections
influx query 'from(bucket:"weather_data") 
  |> range(start: -1d) 
  |> filter(fn: (r) => r._field == "daily_rain_current")
  |> last()'

# Check precipitation rate data  
influx query 'from(bucket:"weather_data") 
  |> range(start: -1d) 
  |> filter(fn: (r) => r._field == "precipitation_rate_mm_h")
  |> last()'
```

## Testing and Validation

### Dry-Run Testing Script
A test script is available to analyze and validate corrections for any specific day:

```bash
# Test today's data (dry-run, no writes to InfluxDB)
python test_rain_corrector_today.py

# The script will:
# - Detect any restarts in the day's data
# - Show what corrections would be made
# - Display statistics and sample corrections
# - Validate against ground truth rain_mm data
```

### Test Script Output Example
```
🧪 TESTING: Analyzing today's rain data (2026-01-17)
✅ Found 1172 daily_rain_current points and 1173 rain_mm points

🚨 RESTART DETECTED at 10:56:28
🚨 RESTART DETECTED at 17:12:09
Found 2 restart(s)

✅ FULL DAY RECONSTRUCTION SUMMARY:
   Total data points processed: 1172
   Points needing correction: 356
   Correction rate: 30.4%
   Max corrected daily rain: 11.65mm
```

### Manual Execution
```bash
# Run the corrector manually (writes to InfluxDB)
docker exec rain-corrector python3 /app/daily_rain_corrector.py

# Run corrector for specific date (modify script as needed)
# Edit ANALYSIS_DATE in daily_rain_corrector.py
```

## Configuration

### Environment Variables
The rain-corrector service uses these environment variables (defined in `.env`):

- `INFLUXDB_URL=http://influxdb:8086`
- `INFLUXDB_TOKEN` - InfluxDB admin token
- `INFLUXDB_ORG` - InfluxDB organization name  
- `INFLUXDB_BUCKET` - InfluxDB bucket name (typically "weather_data")
- `TZ` - Timezone for proper time handling

### Cron Schedule
- **Default**: `10 0 * * *` (00:10 daily)
- **Why 10 minutes**: Allows time for the previous day's data to fully settle
- **Frequency**: Once per day is sufficient since it processes the entire previous day

### Service Dependencies
- **InfluxDB**: Must be running and accessible
- **Weather Data**: Requires both `daily_rain_current` and `rain_mm` fields

## Troubleshooting

### Common Issues

#### Container Not Starting
```bash
# Check container status
docker compose ps rain-corrector

# Check build logs
docker compose logs rain-corrector

# Rebuild if needed
docker compose build rain-corrector
docker compose up -d rain-corrector
```

#### Cron Job Not Running
```bash
# Check cron service inside container
docker exec rain-corrector service cron status

# Check cron logs
docker exec rain-corrector grep CRON /var/log/syslog

# Manually trigger cron
docker exec rain-corrector cron -f &
```

#### InfluxDB Connection Issues
```bash
# Test connection from container
docker exec rain-corrector python3 -c "
from influxdb_client import InfluxDBClient
client = InfluxDBClient(url='http://influxdb:8086', token='YOUR_TOKEN', org='YOUR_ORG')
print('✅ Connection successful' if client.ping() else '❌ Connection failed')
"
```

#### Missing Data Fields
```bash
# Check if rain_mm data exists
influx query 'from(bucket:"weather_data") 
  |> range(start: -1d) 
  |> filter(fn: (r) => r._field == "rain_mm")
  |> count()'

# Check if daily_rain_current exists  
influx query 'from(bucket:"weather_data") 
  |> range(start: -1d) 
  |> filter(fn: (r) => r._field == "daily_rain_current")
  |> count()'
```

### Log Analysis

#### Successful Execution Log
```
✅ Connected to InfluxDB successfully
📊 Analyzing rain data for 2026-01-17...
✅ Found 1172 daily_rain_current points and 1173 rain_mm points
🚨 Restart detected - reconstructing ALL daily rain values
✅ Overwrote 1172 daily_rain_current points
✅ Overwrote 234 precipitation_rate_mm_h points
📈 Correction Summary: 356 points corrected (30.4% of total)
```

#### No Corrections Needed Log
```
✅ Connected to InfluxDB successfully  
📊 Analyzing rain data for 2026-01-17...
✅ Found 1172 daily_rain_current points and 1173 rain_mm points
✅ No restarts detected - no corrections needed
```

#### Error Logs
Look for these error patterns:
- `❌ Failed to connect to InfluxDB` - Connection issues
- `❌ No rain_mm data found` - Missing ground truth data
- `❌ Failed to write data` - InfluxDB write permissions

## Performance

### Processing Capacity
- **Typical Day**: 1000-1500 data points processed in ~2-3 seconds
- **Heavy Rain Day**: Up to 5000+ points, processed in ~10-15 seconds  
- **Memory Usage**: ~50MB during processing
- **CPU Usage**: Minimal, brief spike during processing

### Data Volume
- **Storage Impact**: Adds ~2 additional fields per data point
- **Query Performance**: Negligible impact on InfluxDB queries
- **Retention**: Follows same retention policy as other weather data

## Integration with Grafana

### Dashboard Compatibility
The rain corrector overwrites the original `daily_rain_current` and `precipitation_rate_mm_h` fields, ensuring existing dashboards continue to work without any modifications.

### No Query Changes Needed
Since the corrector updates the existing fields in-place, all existing Grafana queries will automatically use the corrected data. No dashboard updates are required.

## Maintenance Schedule

### Daily (Automatic)
- ✅ Rain corrector runs at 00:10
- ✅ Processes previous day's data
- ✅ Logs results

### Weekly (Manual)
- Check execution logs: `docker exec rain-corrector tail -n 50 /var/log/rain_corrector.log`
- Verify service health: `docker ps --filter "name=rain-corrector"`

### Monthly (Manual)  
- Review correction frequency and patterns
- Check storage usage of corrected data
- Update retention policies if needed

### As Needed
- Run dry-run tests after system changes
- Manually execute corrector after known issues
- Review and update documentation

---

## Quick Reference

### Essential Commands
```bash
# Check rain corrector status
docker ps --filter "name=rain-corrector"

# View recent logs  
docker exec rain-corrector tail -20 /var/log/rain_corrector.log

# Run dry-run test for today
python test_rain_corrector_today.py

# Manual execution (writes to InfluxDB)
docker exec rain-corrector python3 /app/daily_rain_corrector.py

# Restart rain corrector service
docker compose restart rain-corrector
```

### Key Files
- **Main Script**: `scripts/daily_rain_corrector.py`
- **Test Script**: `test_rain_corrector_today.py`  
- **Docker Config**: `rain-corrector/Dockerfile`
- **Service Config**: `docker-compose.yml` (rain-corrector service)
- **Execution Logs**: `/var/log/rain_corrector.log` (inside container)