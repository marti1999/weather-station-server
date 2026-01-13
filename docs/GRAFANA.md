# Grafana Dashboards Guide

Comprehensive guide to the Grafana dashboards, visualizations, and customization options for the weather station.

## Table of Contents

- [Overview](#overview)
- [Dashboard Access](#dashboard-access)
- [Available Dashboards](#available-dashboards)
- [Dashboard Components](#dashboard-components)
- [Customization](#customization)
- [Troubleshooting](#troubleshooting)
- [Advanced Features](#advanced-features)

---

## Overview

The weather station uses Grafana for data visualization with three pre-configured dashboards:

1. **Weather Station Dashboard** - Real-time 24-hour view
2. **Weather Monthly Trends** - 30-day historical analysis
3. **(Future) Current Weather Conditions** - At-a-glance stat panels

All dashboards are **automatically provisioned** from JSON files and use the InfluxDB datasource configured via environment variables.

---

## Dashboard Access

### Initial Login

1. Open http://localhost:3000
2. Login credentials:
   - **Username**: `admin`
   - **Password**: Value of `GRAFANA_ADMIN_PASSWORD` from `.env`

**Security Note**: Change the default password immediately after first login.

### Navigation

- **Dashboards Icon** (left sidebar) → **Browse**
- Search for "Weather" to find all weather-related dashboards
- Click dashboard name to open

### Favorites

Star frequently used dashboards:
- Open dashboard
- Click ★ icon (top left near title)
- Access from **Dashboards** → **Starred**

---

## Available Dashboards

### 1. Weather Station Dashboard

**Purpose**: Real-time weather monitoring with 24-hour historical context.

**Default Settings**:
- Time Range: Last 24 hours
- Refresh: Every 30 seconds
- Timezone: Browser default

**Panels**:

| Panel | Fields Displayed | Description |
|-------|------------------|-------------|
| **Temperature** | temperature_C, dew_point_C, feels_like_C | Triple-line chart showing actual, dew point, and apparent temperature |
| **Humidity** | humidity | Relative humidity percentage |
| **Wind Speed** | wind_avg_km_h | Average wind speed with optional max gust |
| **Wind Direction** | wind_dir_deg | Compass direction as degrees |
| **Precipitation** | daily_rain_current (bars), precipitation_rate_mm_h (line) | Dual-axis: daily accumulation and current rate |
| **UV Index** | uvi | UV exposure index with color-coded thresholds |
| **Solar Radiation** | solar_radiation_w_m2 | Calculated solar irradiance |
| **Pressure** | pressure_hPa | Barometric pressure (if available) |

**Features**:
- **Hover Tooltips**: Displays exact values at cursor position
- **Legend**: Shows last value for each series
- **Zoom**: Click and drag to zoom into time range
- **Annotations**: Optional markers for events (rain start, etc.)

**Customization Options**:
- Change time range: Use time picker (top right)
- Adjust refresh rate: Click refresh dropdown next to time picker
- Hide panels: Click panel title → View → Toggle panel

**Screenshot Example**:
```
┌─────────────┬─────────────┬─────────────┬──────────────┐
│ Temperature │   Humidity  │ Wind Speed  │Wind Direction│
│   📈 Line   │   📈 Line   │  📈 Line    │   🧭 Gauge   │
├─────────────┴─────────────┴─────────────┴──────────────┤
│                   Precipitation                         │
│              📊 Bars + 📈 Line (dual axis)             │
├─────────────┬──────────────────────────────────────────┤
│  UV Index   │          Solar Radiation                 │
│  📈 Line    │              📈 Area                     │
└─────────────┴──────────────────────────────────────────┘
```

---

### 2. Weather Monthly Trends

**Purpose**: Long-term weather pattern analysis with daily aggregations.

**Default Settings**:
- Time Range: Last 30 days
- Refresh: Every 5 minutes
- Timezone: Europe/Madrid (explicit)

**Panels**:

#### Temperature Trends (Daily)
- **avg_temp** (red line): Mean temperature for each day
- **max_temp** (dark red line): Maximum temperature
- **min_temp** (light blue line): Minimum temperature

**Formula**:
```flux
aggregateWindow(every: 1d, fn: mean/max/min, createEmpty: false)
|> timeShift(duration: -1h)  # Align to local midnight
```

#### Humidity Trends (Daily)
- **avg_humidity** (blue line): Mean humidity
- **max_humidity** (dark blue line): Peak humidity
- **min_humidity** (light blue line): Lowest humidity

#### Wind Trends (Daily)
- **avg_wind** (green line): Mean wind speed
- **max_gust** (dark green line): Maximum gust recorded
- **min_wind** (light green line): Calm periods

#### Precipitation Analysis (Daily)
- **daily_rain_total** (blue bars): Total rainfall per day
- **max_rate** (red points): Peak rainfall intensity (mm/h)

**Timezone Alignment**:
The `timeShift(duration: -1h)` ensures data from Jan 12 00:00-23:59 appears on Jan 12, not Jan 13. This compensates for UTC aggregation boundaries.

**Interpretation Example**:
```
Temperature Trends Chart:
   ↑ °C
25 ├─────max_temp─────────────────
   │     /   \
20 ├────●─avg_temp─●──────────────
   │   /             \
15 ├──────────────────min_temp────
   └──────────────────────────────→
     Jan 10  Jan 11  Jan 12  Day
```

**Use Cases**:
- Identify temperature patterns (daily/weekly cycles)
- Track rainfall accumulation over month
- Spot anomalies (unusually hot/cold days)
- Plan outdoor activities based on historical trends

---

## Dashboard Components

### Panel Types

#### Time Series (Line/Area Charts)
- **Best For**: Continuous data (temperature, humidity, wind)
- **Features**: Zoom, pan, multiple Y-axes, legend with stats
- **Configuration**: Right-click panel → Edit

#### Bar Charts
- **Best For**: Discrete events (daily rain totals)
- **Features**: Stacked/grouped, color-coded
- **When Used**: Precipitation panel (daily accumulation)

#### Gauge/Stat Panels
- **Best For**: Latest value display (current conditions)
- **Features**: Thresholds, color coding, large numbers
- **When Used**: (Future) Current Conditions dashboard

#### Compass/Direction Widgets
- **Best For**: Wind direction
- **Features**: 360° visualization, cardinal directions
- **Configuration**: Requires wind_dir_deg field

### Query Structure

All dashboards use Flux query language:

```flux
from(bucket: "weather_data")
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "rtl433")
  |> filter(fn: (r) => r._field == "temperature_C")
  |> aggregateWindow(every: v.windowPeriod, fn: mean, createEmpty: false)
  |> drop(columns: ["_measurement", "model", "id", ...])
```

**Key Components**:
- `range()`: Uses dashboard time picker values
- `filter()`: Selects specific measurement and field
- `aggregateWindow()`: Downsamples data based on time range
- `drop()`: Removes unnecessary tag columns

### Color Schemes

**Temperature**:
- Blue: < 15°C (cold)
- Green: 15-25°C (comfortable)
- Yellow: 25-30°C (warm)
- Red: > 30°C (hot)

**UV Index**:
- Green: 0-2 (Low)
- Yellow: 3-5 (Moderate)
- Orange: 6-7 (High)
- Red: 8-10 (Very High)
- Purple: 11+ (Extreme)

**Precipitation Rate**:
- Green: 0 mm/h (no rain)
- Yellow: > 2 mm/h (light rain)
- Orange: > 10 mm/h (moderate rain)
- Red: > 25 mm/h (heavy rain)

---

## Customization

### Modify Existing Panels

1. **Edit Panel**:
   - Click panel title → Edit
   - Modify query, visualization, or display options
   - Click **Apply** to save

2. **Change Time Range**:
   - Panel → Edit → Query options → Time range override
   - Example: Show last 7 days instead of dashboard default

3. **Adjust Thresholds**:
   - Panel → Edit → Field → Thresholds
   - Add/remove color breakpoints
   - Set min/max values

4. **Hide Series**:
   - Click legend item to toggle visibility
   - Right-click → Hide series to persist

### Add New Panels

1. Click **Add** → **Visualization** (top right)
2. Select panel type (Time series, Gauge, etc.)
3. Configure query:
   ```flux
   from(bucket: "weather_data")
     |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
     |> filter(fn: (r) => r._field == "battery_status_pct")
     |> last()
   ```
4. Customize visualization
5. Click **Apply**

### Create Custom Dashboard

1. **Dashboards** → **New** → **New Dashboard**
2. Click **Add visualization**
3. Select **InfluxDB** datasource
4. Build query (see examples below)
5. Save dashboard: Click **Save** (disk icon)

**Example Queries**:

**Daily Min/Max Temperature**:
```flux
from(bucket: "weather_data")
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r._field == "temperature_C")
  |> aggregateWindow(every: 1d, fn: max, createEmpty: false)
  |> timeShift(duration: -1h)
```

**Wind Rose (directional distribution)**:
Requires custom visualization plugin or use external tool.

**Correlation (Temp vs Humidity)**:
```flux
temp = from(bucket: "weather_data")
  |> range(start: v.timeRangeStart)
  |> filter(fn: (r) => r._field == "temperature_C")

humidity = from(bucket: "weather_data")
  |> range(start: v.timeRangeStart)
  |> filter(fn: (r) => r._field == "humidity")

join(tables: {temp: temp, humidity: humidity}, on: ["_time"])
```

### Export/Import Dashboards

**Export**:
1. Dashboard → Settings (gear icon)
2. **JSON Model** tab
3. Copy JSON or click **Save to file**

**Import**:
1. **Dashboards** → **New** → **Import**
2. Paste JSON or upload file
3. Select datasource
4. Click **Import**

**Share Dashboards**:
- Dashboard → Share → Snapshot (creates public link)
- Dashboard → Share → Export (downloads JSON)

### Provisioning New Dashboards

To make dashboards persistent across container restarts:

1. Save dashboard JSON to `grafana/provisioning/dashboards/`
2. Edit JSON, set:
   ```json
   {
     "id": null,
     "uid": "unique-dashboard-id",
     "title": "My Custom Dashboard"
   }
   ```
3. Restart Grafana: `docker compose restart grafana`

Dashboard appears automatically on next startup.

---

## Troubleshooting

### Dashboard Not Loading

**Symptom**: Dashboard shows "Loading..." indefinitely.

**Solutions**:
1. Check datasource: **Connections** → **Data sources** → **InfluxDB** → **Save & Test**
2. Verify time range has data: Try "Last 24 hours"
3. Check browser console (F12) for errors
4. Clear browser cache: Ctrl+Shift+Delete

### "No Data" in Panels

**Symptom**: Panels show "No data" despite InfluxDB having data.

**Debug Steps**:
1. Click panel title → **Explore**
2. Run query manually
3. Check **Query Inspector** tab for errors

**Common Causes**:
- Wrong field name (check InfluxDB schema)
- Time range too narrow (no data in period)
- Timezone mismatch (data offset)
- Measurement name typo (`rtl433` vs `rtl_433`)

**Fix**: Edit panel → Query tab → Verify:
```flux
filter(fn: (r) => r._measurement == "rtl433")  # Correct
filter(fn: (r) => r._field == "temperature_C")  # Match InfluxDB field
```

### Duplicate Values (ASK/FSK)

**Symptom**: Each metric shows twice with "mod=ASK" and "mod=FSK" labels.

**Cause**: Weather station transmits with dual modulation.

**Solution**: Add to query:
```flux
|> group()
|> keep(columns: ["_time", "_value"])
```

This removes the `mod` tag causing duplication.

### Wrong Timezone Display

**Symptom**: Timestamps off by 1-2 hours.

**Solutions**:
1. **Dashboard Level**: Dashboard settings → Timezone → Select "Europe/Madrid"
2. **Browser Level**: Check OS/browser timezone settings
3. **Data Level**: Verify InfluxDB stores in UTC (this is correct)

**Note**: Monthly Trends dashboard has hardcoded timezone, Daily dashboard uses browser timezone.

### Slow Dashboard Performance

**Symptom**: Dashboard takes > 5 seconds to load or refresh.

**Optimizations**:

1. **Reduce Time Range**: Use "Last 6 hours" instead of "Last 30 days"

2. **Increase Aggregation Window**:
   ```flux
   |> aggregateWindow(every: 5m, fn: mean)  # Instead of 1m
   ```

3. **Limit Data Points**:
   ```flux
   |> limit(n: 1000)  # For testing
   ```

4. **Disable Auto-Refresh**: Set to "Off" when not actively viewing

5. **Optimize Query**: Remove unnecessary columns early:
   ```flux
   |> drop(columns: ["model", "id", ...])  # Early in query
   ```

### Panel Cut Off or Overlapping

**Symptom**: Panel display is cropped or panels overlap.

**Solutions**:
1. Dashboard → Settings → General → Auto-refresh → Disable
2. Resize panel: Click and drag panel corner
3. Adjust grid: Dashboard → Settings → General → Panel alignment
4. Reset layout: Click **Reset zoom** (lens icon, top right)

---

## Advanced Features

### Variables

Create dashboard variables for dynamic filtering:

1. Dashboard → Settings → Variables → Add variable
2. **Type**: Query
3. **Query**:
   ```flux
   import "influxdata/influxdb/schema"
   schema.tagValues(bucket: "weather_data", tag: "id")
   ```
4. Use in panels: `r.id == "$device_id"`

**Example Use Cases**:
- Switch between multiple weather stations
- Filter by time period (day/week/month)
- Toggle between raw and derived fields

### Annotations

Add event markers to dashboards:

1. Dashboard → Settings → Annotations → Add annotation
2. **Query**:
   ```flux
   from(bucket: "weather_data")
     |> range(start: v.timeRangeStart)
     |> filter(fn: (r) => r._field == "daily_rain_current" and r._value > 10)
   ```
3. Marks days with > 10mm rain

### Alerts

Set up threshold-based alerts:

1. Panel → Edit → Alert tab → Create alert
2. Configure conditions:
   - WHEN: `avg()` OF query(A, 5m, now)
   - IS ABOVE: 30 (°C)
3. Set notification channel (email, Slack, etc.)
4. Save

**Example Alerts**:
- Temperature exceeds 35°C (heat warning)
- Humidity < 20% (dry air alert)
- No data received in 10 minutes (sensor offline)
- Daily rain > 50mm (flooding risk)

### Dashboard Links

Connect related dashboards:

1. Dashboard → Settings → Links → Add link
2. **Type**: Dashboard
3. **Target**: Weather Monthly Trends
4. **Icon**: Dashboard
5. Save

Creates clickable link in dashboard header.

### Playlists

Auto-rotate through dashboards:

1. **Dashboards** → **Playlists** → **New playlist**
2. Add dashboards
3. Set interval (e.g., 30 seconds)
4. Click **Start playlist**

**Use Case**: Display on wall-mounted monitor cycling through views.

### Plugins

Install additional visualizations:

```bash
# Example: Wind rose plugin
docker exec grafana grafana-cli plugins install citilogics-geoloop-panel

# Restart Grafana
docker compose restart grafana
```

**Recommended Plugins**:
- **Worldmap Panel**: Geographic weather data
- **Plotly Panel**: Advanced scientific charts
- **Pie Chart**: Data distribution

### API Access

Programmatically interact with dashboards:

```bash
# Get dashboard JSON
curl -H "Authorization: Bearer <API_KEY>" \
  http://localhost:3000/api/dashboards/uid/weather-station-v2

# Create dashboard
curl -X POST -H "Authorization: Bearer <API_KEY>" \
  -H "Content-Type: application/json" \
  -d @dashboard.json \
  http://localhost:3000/api/dashboards/db
```

Generate API key: **Configuration** → **API Keys** → **Add API key**

---

## Best Practices

### Design Principles

1. **Consistency**: Use same color scheme across panels
2. **Clarity**: Label axes, add units, use descriptive titles
3. **Context**: Show historical trends, not just current values
4. **Performance**: Aggregate data for long time ranges
5. **Accessibility**: Use colorblind-safe palettes

### Naming Conventions

- **Dashboard Names**: Descriptive, prefixed (e.g., "Weather - Monthly Trends")
- **Panel Titles**: Short, clear (e.g., "Temperature (°C)" not "Temp")
- **Variables**: Lowercase with underscores (`device_id`, not `DeviceID`)

### Organization

- **Folders**: Group related dashboards (Weather, System Monitoring)
- **Tags**: Tag dashboards for easy searching (`weather`, `production`)
- **Favorites**: Star frequently used dashboards

### Version Control

Track dashboard changes:
1. Export dashboard JSON regularly
2. Commit to git (outside Docker volumes)
3. Document changes in commit messages
4. Use dashboard versioning: Settings → Versions

---

## Additional Resources

- **Grafana Documentation**: https://grafana.com/docs/grafana/latest/
- **Flux Query Language**: https://docs.influxdata.com/flux/
- **Panel Plugins**: https://grafana.com/grafana/plugins/
- **Community Dashboards**: https://grafana.com/grafana/dashboards/

### Sample Dashboards

Import community dashboards for inspiration:
- Search "weather station" on Grafana dashboard marketplace
- Filter by InfluxDB datasource
- Customize to match your sensor setup
