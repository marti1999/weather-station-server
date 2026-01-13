# Data Fields Reference

This document describes all data fields in the weather station system, from raw sensor readings to derived calculations and dashboard aggregations.

## Table of Contents

- [Raw Sensor Fields](#raw-sensor-fields)
- [Derived Fields (Telegraf)](#derived-fields-telegraf)
- [Dashboard Aggregations](#dashboard-aggregations)
- [InfluxDB Storage](#influxdb-storage)

---

## Raw Sensor Fields

These fields are transmitted directly from the Vevor-7in1 weather station via RTL_433 and published to MQTT.

### Environmental Measurements

| Field | Data Type | Unit | Description | Typical Range |
|-------|-----------|------|-------------|---------------|
| `temperature_C` | float | °C | Ambient air temperature | -40 to 60°C |
| `humidity` | float | % | Relative humidity | 0-100% |
| `wind_avg_km_h` | float | km/h | Average wind speed over sampling period | 0-150 km/h |
| `wind_max_km_h` | float | km/h | Maximum wind gust speed | 0-200 km/h |
| `wind_dir_deg` | float | degrees | Wind direction (0° = North, 90° = East) | 0-359° |
| `rain_mm` | float | mm | Cumulative rainfall since sensor reset | 0-9999 mm |
| `light_lux` | float | lux | Ambient light intensity | 0-200,000 lux |
| `uvi` | float | index | UV Index (0-16 scale) | 0-16 |
| `pressure_hPa` | float | hPa | Barometric pressure (CSV imports only) | 950-1050 hPa |

### Device Metadata

| Field | Data Type | Description |
|-------|-----------|-------------|
| `battery_ok` | float | Battery status (1.0 = OK, 0.0 = Low) |
| `model` | tag (string) | Device model ("Vevor-7in1" or "CSV_Import") |
| `id` | tag (string) | Unique device ID (e.g., "3092" or "imported") |
| `channel` | tag (string) | RF channel (usually "0") |
| `mic` | tag (string) | Message integrity check ("CHECKSUM") |
| `mod` | tag (string) | Modulation type ("ASK", "FSK", or "CSV") |
| `time` | string | Timestamp from sensor (YYYY-MM-DD HH:MM:SS) |

**Note on Modulation**: The weather station transmits each reading twice using different modulation schemes (ASK and FSK). This creates duplicate entries with slightly different timestamps and potentially different values.

---

## Derived Fields (Telegraf)

These fields are calculated by the Telegraf Starlark processor before data is stored in InfluxDB. All formulas use the local timezone set in the `TZ` environment variable.

### Temperature-Related

#### `dew_point_C`
**Data Type**: float
**Unit**: °C
**Formula**: Magnus formula

```
γ = (17.625 × T) / (243.04 + T) + ln(RH/100)
Td = (243.04 × γ) / (17.625 - γ)
```

Where:
- T = temperature_C
- RH = humidity (%)
- Constants: b = 17.625, c = 243.04

**Purpose**: Indicates the temperature at which air becomes saturated and condensation forms. Critical for frost/fog prediction.

#### `feels_like_C`
**Data Type**: float
**Unit**: °C
**Formula**: Context-aware (selects appropriate formula based on conditions)

**Conditions**:
1. **Wind Chill** (when temp < 10°C AND wind > 4.8 km/h):
   ```
   WC = 13.12 + 0.6215×T - 11.37×V^0.16 + 0.3965×T×V^0.16
   ```
   Where: T = temperature_C, V = wind_avg_km_h

2. **Heat Index** (when temp > 27°C AND humidity > 40%):
   ```
   HI = c1 + c2×T + c3×RH + c4×T×RH + c5×T² + c6×RH² + c7×T²×RH + c8×T×RH² + c9×T²×RH²
   ```
   Rothfusz regression coefficients (adapted to Celsius)

3. **Otherwise**: Returns actual temperature_C

**Purpose**: Perceived temperature accounting for wind and humidity effects on human comfort.

### Precipitation-Related

#### `daily_rain_current`
**Data Type**: float
**Unit**: mm
**Calculation**: `rain_mm - daily_start_rain`
**Reset**: Midnight (local timezone)

**Purpose**: Accumulation for the current day. Resets to 0.0 at midnight.

**Edge Cases**:
- Sensor reset detection: If value becomes negative, resets to 0.0

#### `daily_rain_total`
**Data Type**: float
**Unit**: mm
**Calculation**: Previous complete day's rain total
**Update**: At midnight (local timezone)

**Purpose**: Historical daily rainfall (same value throughout the day). Used for long-term statistics and monthly aggregations.

**State Management**: Persists in Telegraf memory (lost on restart).

#### `precipitation_rate_mm_h`
**Data Type**: float
**Unit**: mm/h
**Calculation**: `(rain_change / time_elapsed) × 3600`
**Window**: 5 minutes (300 seconds)

**Purpose**: Current rainfall intensity. Useful for detecting heavy rain events.

**Update Frequency**: Every 5 minutes minimum.

### Solar-Related

#### `solar_radiation_w_m2`
**Data Type**: float
**Unit**: W/m²
**Formula**: `light_lux / 126.7`

**Purpose**: Approximates solar irradiance from lux measurement. Useful for solar panel estimation.

**Approximation Note**: Conversion factor assumes sunlight spectrum. Artificial light may give inaccurate results.

### Wind-Related

#### `wind_speed_beaufort`
**Data Type**: int
**Unit**: Beaufort scale (0-12)
**Calculation**: Lookup table from wind_avg_km_h

| Beaufort | km/h Range | Description |
|----------|------------|-------------|
| 0 | < 1.0 | Calm |
| 1 | 1.0 - 5.4 | Light air |
| 2 | 5.5 - 11.8 | Light breeze |
| 3 | 11.9 - 19.7 | Gentle breeze |
| 4 | 19.8 - 28.6 | Moderate breeze |
| 5 | 28.7 - 38.7 | Fresh breeze |
| 6 | 38.8 - 49.8 | Strong breeze |
| 7 | 49.9 - 61.7 | Near gale |
| 8 | 61.8 - 74.5 | Gale |
| 9 | 74.6 - 88.0 | Strong gale |
| 10 | 88.1 - 102.3 | Storm |
| 11 | 102.4 - 117.3 | Violent storm |
| 12 | ≥ 117.4 | Hurricane |

**Purpose**: Standardized wind speed classification for marine/land observations.

### UV-Related

#### `uv_risk_level`
**Data Type**: int
**Unit**: Risk category (0-4)
**Calculation**: Mapping from UVI

| Level | UVI Range | Category |
|-------|-----------|----------|
| 0 | 0-2.9 | Low |
| 1 | 3-5.9 | Moderate |
| 2 | 6-7.9 | High |
| 3 | 8-10.9 | Very High |
| 4 | ≥ 11 | Extreme |

**Purpose**: Simplified UV exposure risk for health warnings.

### Device-Related

#### `battery_status_pct`
**Data Type**: float
**Unit**: %
**Calculation**: `battery_ok × 100`

**Purpose**: Converts binary battery status to percentage (100% or 0%).

---

## Dashboard Aggregations

These are calculated on-the-fly by Grafana using Flux queries. They are NOT stored in InfluxDB.

### Daily Aggregations (Monthly Trends Dashboard)

All daily aggregations use `aggregateWindow(every: 1d)` with `timeShift(duration: -1h)` to align with local midnight.

#### Temperature Trends

| Aggregation | Function | Description |
|-------------|----------|-------------|
| `avg_temp` | `mean(temperature_C)` | Average temperature for the day |
| `max_temp` | `max(temperature_C)` | Maximum temperature for the day |
| `min_temp` | `min(temperature_C)` | Minimum temperature for the day |

**Query Example**:
```flux
from(bucket: "weather_data")
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "rtl433")
  |> filter(fn: (r) => r._field == "temperature_C")
  |> aggregateWindow(every: 1d, fn: mean, createEmpty: false)
  |> timeShift(duration: -1h)
```

**Timezone Handling**: The `timeShift(duration: -1h)` shifts aggregation timestamps to display correctly in Europe/Madrid timezone (UTC+1 winter, UTC+2 summer).

#### Humidity Trends

| Aggregation | Function | Description |
|-------------|----------|-------------|
| `avg_humidity` | `mean(humidity)` | Average humidity for the day |
| `max_humidity` | `max(humidity)` | Maximum humidity for the day |
| `min_humidity` | `min(humidity)` | Minimum humidity for the day |

#### Wind Trends

| Aggregation | Function | Field | Description |
|-------------|----------|-------|-------------|
| `avg_wind` | `mean()` | `wind_avg_km_h` | Average wind speed for the day |
| `max_gust` | `max()` | `wind_max_km_h` | Maximum gust speed for the day |
| `min_wind` | `min()` | `wind_avg_km_h` | Minimum wind speed for the day |

#### Precipitation Analysis

| Aggregation | Function | Field | Description |
|-------------|----------|-------|-------------|
| `daily_rain` | `last()` | `daily_rain_total` | Total rainfall for the day |
| `max_rate` | `max()` | `precipitation_rate_mm_h` | Peak rainfall rate for the day |

**Note**: Uses `last()` for daily_rain_total because this field already contains the daily total (updated at midnight).

### Real-Time Aggregations (Daily Dashboard)

The daily dashboard uses `aggregateWindow(every: v.windowPeriod)` where the period is determined by the time range:
- Last 6 hours: 1-minute windows
- Last 24 hours: 5-minute windows
- Last 7 days: 1-hour windows
- Last 30 days: 6-hour windows

**Functions Used**:
- `mean()` - For temperature, humidity, wind speed, solar radiation
- `last()` - For daily rain accumulation (preserves monotonic increase)
- `max()` - For wind gusts (captures peak values)

---

## InfluxDB Storage

### Measurement Structure

**Measurement Name**: `rtl433`

**Tags** (indexed for fast queries):
- `model` - Device model
- `id` - Device ID
- `channel` - RF channel
- `battery_ok` - Battery status
- `mic` - Message integrity
- `mod` - Modulation type (ASK/FSK)
- `topic` - MQTT topic
- `host` - Telegraf hostname

**Fields** (actual data values):
- All raw sensor fields (temperature_C, humidity, etc.)
- All derived fields (dew_point_C, feels_like_C, etc.)

**Timestamp**: UTC (automatically handled by InfluxDB)

### Storage Efficiency

**Data Rate**:
- Sensor transmission: Every 10-20 seconds
- With ASK+FSK: ~8,640 points/day (double due to dual modulation)
- With derived fields: ~17 fields × 8,640 = 146,880 values/day

**Compression**: InfluxDB compresses time-series data efficiently:
- Raw data: ~2-3 MB/day
- With 30-day retention: ~60-90 MB total

### Querying Examples

**Get latest temperature**:
```flux
from(bucket: "weather_data")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "rtl433" and r._field == "temperature_C")
  |> last()
```

**Get daily averages for a week**:
```flux
from(bucket: "weather_data")
  |> range(start: -7d)
  |> filter(fn: (r) => r._measurement == "rtl433" and r._field == "temperature_C")
  |> aggregateWindow(every: 1d, fn: mean)
```

**Compare raw vs derived fields**:
```flux
from(bucket: "weather_data")
  |> range(start: -24h)
  |> filter(fn: (r) => r._measurement == "rtl433")
  |> filter(fn: (r) => r._field == "temperature_C" or r._field == "feels_like_C" or r._field == "dew_point_C")
```

---

## Timezone Configuration

**Critical Setting**: The `TZ` environment variable in `.env` controls timezone handling across the entire stack.

### Where TZ is Used

1. **RTL_433 Container**: Formats timestamps in local time
2. **Telegraf Container**: Uses for `json_timezone` parsing
3. **Telegraf Starlark Processor**: Manual offset calculation for daily reset

### Important Limitation

The Telegraf Starlark processor has a **hardcoded timezone offset** (line 98 in `telegraf.conf`):

```python
tz_offset = 3600  # UTC+1 for Europe/Madrid winter
```

**Manual Adjustment Required**:
- **Europe/Madrid (winter)**: `tz_offset = 3600` (UTC+1)
- **Europe/Madrid (summer)**: `tz_offset = 7200` (UTC+2)
- **US Eastern (winter)**: `tz_offset = -18000` (UTC-5)
- **US Eastern (summer)**: `tz_offset = -14400` (UTC-4)

This offset is used for daily rain reset calculations. If not adjusted for DST, midnight detection will be off by 1 hour during summer months.

### Grafana Dashboard Timezone

- **Daily Dashboard**: Uses `"timezone": "browser"` (inherits from browser)
- **Monthly Trends**: Uses `"timezone": "Europe/Madrid"` (explicit setting)

All dashboard queries include `timeShift(duration: -1h)` to align aggregation boundaries with local midnight.

---

## Data Flow Summary

```
Weather Station (433MHz)
    ↓
RTL_433 (decodes signal)
    ↓
MQTT Broker (rtl_433/Vevor-7in1/3092)
    ↓
Telegraf (MQTT Consumer)
    ↓
Telegraf Starlark Processor
    ├── Raw Fields (pass-through)
    └── Derived Fields (calculated)
    ↓
InfluxDB (stores all fields with UTC timestamps)
    ↓
Grafana (queries with aggregations)
    ├── Real-time queries (variable window)
    └── Daily aggregations (1d window with timeShift)
```

**Key Points**:
- Raw fields stored as-is
- Derived fields calculated once before storage
- Dashboard aggregations computed on-the-fly
- All timestamps in UTC in database
- Timezone conversions handled at query time
