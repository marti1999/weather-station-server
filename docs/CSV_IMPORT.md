# CSV Import Guide

Comprehensive guide for importing historical weather data from CSV files into InfluxDB.

## Table of Contents

- [Overview](#overview)
- [CSV Format Requirements](#csv-format-requirements)
- [Field Mapping](#field-mapping)
- [Installation](#installation)
- [Usage](#usage)
- [Outlier Detection and Correction](#outlier-detection-and-correction)
- [Data Transformations](#data-transformations)
- [Derived Field Calculations](#derived-field-calculations)
- [Verification](#verification)
- [Troubleshooting](#troubleshooting)

---

## Overview

The CSV import script (`import_csv.py`) allows you to bulk-load historical weather data into InfluxDB. It handles:

- **Timezone conversion** from Madrid (Europe/Madrid) to UTC
- **Compass direction conversion** from abbreviations (N, SSE, etc.) to degrees (0-359)
- **Derived field calculation** matching live sensor formulas
- **Duplicate detection** to prevent overwriting existing data (with optional overwrite mode)
- **Outlier detection and correction** using adaptive statistical methods
- **Batch processing** for efficient imports (1000 points per batch)
- **Data tagging** for filtering (CSV imports tagged as `model=CSV_Import`)

**Use Cases:**
- Import data from weather station logger exports
- Backfill historical data from other sources
- Migrate data from different weather station platforms

### Obtaining CSV Data

**Weather Underground Stations**: If you have a Weather Underground personal weather station (PWS), you can export your historical data using [the-weather-scraper](https://github.com/Karlheinzniebuhr/the-weather-scraper) tool.

This tool exports Weather Underground data in the exact CSV format required by the import script, making it seamless to import years of historical weather data.

**Other Data Sources**: The import script accepts any CSV file matching the required format (see [CSV Format Requirements](#csv-format-requirements) below).

---

## CSV Format Requirements

### Supported Formats

The script supports both US/International and European CSV formats:

**US/International Format** (comma delimiter, dot decimal):
```csv
Date,Time,Temperature_C,Dew_Point_C,Humidity_%,Wind,Speed_kmh,Gust_kmh,Pressure_hPa,Precip_Rate_mm,Precip_Accum_mm,UV,Solar_w/m2
2025/07/09,07:44 PM,25.17,18.28,66.0,SSE,0.64,9.49,1017.27,0.0,4.32,0.0,64.5
```

**European Format** (semicolon delimiter, comma decimal):
```csv
Date;Time;Temperature_C;Dew_Point_C;Humidity_%;Wind;Speed_kmh;Gust_kmh;Pressure_hPa;Precip_Rate_mm;Precip_Accum_mm;UV;Solar_w/m2
2025/07/09;07:44 PM;25,17;18,28;66,0;SSE;0,64;9,49;1017,27;0,0;4,32;0,0;64,5
```

### Required Columns

| Column Name | Description | Example Values |
|-------------|-------------|----------------|
| `Date` | Date in YYYY/MM/DD format | `2025/07/09` |
| `Time` | 12-hour time with AM/PM | `07:44 PM` |
| `Temperature_C` | Temperature in Celsius | `25.17` |
| `Dew_Point_C` | Dew point in Celsius | `18.28` |
| `Humidity_%` | Relative humidity percentage | `66.0` |
| `Wind` | Compass direction (N, NE, E, SSE, etc.) | `SSE` |
| `Speed_kmh` | Average wind speed in km/h | `0.64` |
| `Gust_kmh` | Wind gust speed in km/h | `9.49` |
| `Pressure_hPa` | Barometric pressure in hPa | `1017.27` |
| `Precip_Rate_mm` | Precipitation rate in mm/h | `0.0` |
| `Precip_Accum_mm` | Daily precipitation accumulation in mm | `4.32` |
| `UV` | UV index | `0.0` |
| `Solar_w/m2` | Solar radiation in W/m² | `64.5` |

**Important Notes:**
- Header row is required
- Date/Time columns must match the format shown above
- Wind direction must use compass abbreviations (see [Compass Conversion](#compass-direction-conversion))
- Decimal separator can be comma or dot (auto-detected)
- Missing values should be represented as `0` or `0.0`

---

## Field Mapping

### Direct Mappings (No Transformation)

| CSV Column | InfluxDB Field | Data Type | Transformation |
|------------|---------------|-----------|----------------|
| `Temperature_C` | `temperature_C` | float | Decimal parsing |
| `Dew_Point_C` | `dew_point_C` | float | Decimal parsing |
| `Humidity_%` | `humidity` | float | Decimal parsing |
| `Speed_kmh` | `wind_avg_km_h` | float | Decimal parsing |
| `Gust_kmh` | `wind_max_km_h` | float | Decimal parsing |
| `Precip_Rate_mm` | `precipitation_rate_mm_h` | float | Decimal parsing |
| `Precip_Accum_mm` | `daily_rain_current` | float | Decimal parsing |
| `UV` | `uvi` | float | Decimal parsing |
| `Solar_w/m2` | `solar_radiation_w_m2` | float | Decimal parsing |
| `Pressure_hPa` | `pressure_hPa` | float | Decimal parsing |

### Transformed Fields

| CSV Column(s) | InfluxDB Field | Data Type | Transformation |
|--------------|---------------|-----------|----------------|
| `Date` + `Time` | `_time` | timestamp | Parse + Madrid→UTC conversion |
| `Wind` | `wind_dir_deg` | float | Compass → Degrees |
| `Precip_Accum_mm` | `rain_mm` | float | Copy of daily accumulation |

### Calculated Fields

| InfluxDB Field | Data Type | Calculation Source |
|---------------|-----------|-------------------|
| `feels_like_C` | float | Wind chill or heat index formula |
| `wind_speed_beaufort` | int | Beaufort scale mapping |
| `uv_risk_level` | int | UV index categories |
| `light_lux` | float | `solar_radiation_w_m2 × 126.7` |
| `battery_ok` | float | Set to `1.0` (CSV has no battery data) |
| `battery_status_pct` | float | Set to `100.0` (CSV has no battery data) |
| `daily_rain_total` | float | Set to `0.0` (requires historical state) |

### Tags for CSV Imports

All imported data points are tagged to distinguish them from live sensor data:

```python
tags = {
    'model': 'CSV_Import',
    'id': 'imported',
    'channel': '0',
    'battery_ok': '1',
    'mic': 'CHECKSUM',
    'mod': 'CSV',
    'topic': 'import/csv',
    'host': 'import-script'
}
```

**Filtering in Grafana:**
```flux
# Show only CSV imports
|> filter(fn: (r) => r.model == "CSV_Import")

# Show only live sensor data
|> filter(fn: (r) => r.model != "CSV_Import")

# Show both (remove model filter entirely)
|> filter(fn: (r) => r._measurement == "rtl433")
```

---

## Installation

### Prerequisites

- Python 3.7 or higher
- Access to InfluxDB instance
- `.env` file with InfluxDB credentials

### Install Python Dependencies

```bash
cd /path/to/weather-station-server

# Install required libraries
pip3 install -r requirements.txt
```

This installs:
- `influxdb-client>=1.36.0` - InfluxDB Python client
- `pytz>=2023.3` - Timezone conversion
- `python-dotenv>=1.0.0` - Environment variable loading

### Verify Configuration

Ensure your `.env` file contains:

```bash
INFLUXDB_ADMIN_TOKEN=your-token-here
INFLUXDB_ORG=weather
INFLUXDB_BUCKET=weather_data
TZ=Europe/Madrid
```

Check configuration:
```bash
cat .env | grep -E 'INFLUXDB_ADMIN_TOKEN|INFLUXDB_ORG|INFLUXDB_BUCKET|TZ'
```

---

## Usage

### Basic Usage

```bash
# Dry run (test without writing to database)
python3 import_csv.py your_data.csv --dry-run

# Actual import
python3 import_csv.py your_data.csv

# Import with overwrite (replace existing data points)
python3 import_csv.py your_data.csv --overwrite

# Show detailed outlier corrections
python3 import_csv.py your_data.csv --show-outlier-fixes

# Combine options
python3 import_csv.py your_data.csv --dry-run --show-outlier-fixes
```

### Command Line Options

| Option | Description |
|--------|-------------|
| `--dry-run` | Preview import without writing to database |
| `--overwrite` | Overwrite existing data points instead of skipping them |
| `--show-outlier-fixes` | Display detailed information about each outlier correction |

### Dry Run Mode

**Purpose:** Validate CSV format and preview data before import

```bash
python3 import_csv.py import.csv --dry-run
```

**Output:**
```
Starting CSV import from: import.csv
Dry run mode: True
Timezone: Europe/Madrid
InfluxDB: http://localhost:8086
Organization: weather
Bucket: weather_data
------------------------------------------------------------
Parsed 45537 rows from CSV
Date range: 2025-07-09 17:44:00+00:00 to 2026-01-10 22:54:00+00:00
------------------------------------------------------------
Checking for existing data in InfluxDB...
Found 0 existing timestamps in range
Skipping 0 existing data points
Importing 45537 new data points
------------------------------------------------------------
DRY RUN - No data will be written

Sample of first data point to be imported:
  Timestamp: 2025-07-09 17:44:00+00:00
  Tags: {'model': 'CSV_Import', 'id': 'imported', ...}
  Fields (19):
    battery_ok: 1.0
    battery_status_pct: 100.0
    daily_rain_current: 4.32
    daily_rain_total: 0.0
    dew_point_C: 18.28
    feels_like_C: 25.17
    humidity: 66.0
    light_lux: 8172.15
    precipitation_rate_mm_h: 0.0
    pressure_hPa: 1017.27
    rain_mm: 4.32
    solar_radiation_w_m2: 64.5
    temperature_C: 25.17
    uv_risk_level: 0
    uvi: 0.0
    wind_avg_km_h: 0.64
    wind_dir_deg: 157.5
    wind_max_km_h: 9.49
    wind_speed_beaufort: 0
```

**What to Check:**
- ✅ All rows parsed successfully (no ERROR messages)
- ✅ Date range matches your CSV data
- ✅ Sample fields show correct values
- ✅ Timestamp converted to UTC correctly
- ✅ Compass direction converted (e.g., SSE → 157.5°)

### Actual Import

```bash
python3 import_csv.py import.csv
```

**Output:**
```
Starting CSV import from: import.csv
Dry run mode: False
Timezone: Europe/Madrid
InfluxDB: http://localhost:8086
Organization: weather
Bucket: weather_data
------------------------------------------------------------
Parsed 45537 rows from CSV
Date range: 2025-07-09 17:44:00+00:00 to 2026-01-10 22:54:00+00:00
------------------------------------------------------------
Checking for existing data in InfluxDB...
Found 0 existing timestamps in range
Skipping 0 existing data points
Importing 45537 new data points
------------------------------------------------------------
Progress: 45537/45537 data points written
Import complete: 45537 data points written
```

**Import Speed:** Approximately 1000-2000 points per second
- 10,000 rows ≈ 5-10 seconds
- 50,000 rows ≈ 30-60 seconds
- 100,000 rows ≈ 1-2 minutes

### Re-running Import (Duplicate Detection)

If you run the import again with the same CSV file:

```bash
python3 import_csv.py import.csv
```

**Output:**
```
...
Found 45537 existing timestamps in range
Skipping 45537 existing data points
Importing 0 new data points
------------------------------------------------------------
Import complete: 0 data points written
```

**Behavior:** Existing timestamps are detected and skipped automatically. Only new data points are imported.

### Overwrite Mode

Use `--overwrite` to replace existing data points:

```bash
python3 import_csv.py import.csv --overwrite
```

**Output:**
```
...
Overwrite mode: will replace existing data points
Importing 45537 data points
------------------------------------------------------------
Progress: 45537/45537 data points written
Import complete: 45537 data points written
```

**Use Cases:**
- Re-importing corrected CSV data after fixing errors
- Updating historical data with better quality values
- Replacing data after adjusting outlier detection parameters

---

## Outlier Detection and Correction

The import script implements sophisticated outlier detection algorithms to identify and correct sensor anomalies in historical weather data. These corrections are applied automatically during import, ensuring data quality without manual intervention.

### Overview

Weather sensors can produce erroneous readings due to interference, hardware glitches, or transmission errors. The script detects two primary types of outliers:

1. **Wind Gust Anomalies** — Sudden unrealistic spikes in wind gust measurements
2. **Precipitation Accumulation Anomalies** — Erroneous jumps in cumulative rainfall data

### 1. Wind Gust Outlier Detection

Wind gust outliers are detected using a dual-criteria approach combining absolute thresholds with adaptive neighbor-based spike detection.

#### 1.1 Absolute Threshold Detection

A wind gust reading $g_i$ is flagged as an outlier if it exceeds the maximum physically plausible threshold:

$$
g_i > G_{max} \land (\bar{w}_i < 1 \lor g_i > 10 \cdot \bar{w}_i)
$$

Where:
- $g_i$ = Wind gust at time $t_i$ (km/h)
- $\bar{w}_i$ = Average wind speed at time $t_i$ (km/h)
- $G_{max} = 80$ km/h (configurable threshold)

This condition triggers when gusts exceed 80 km/h while the average wind speed is either very low (< 1 km/h) or the gust is more than 10× the average wind — a physically implausible scenario indicating sensor error.

#### 1.2 Adaptive Spike Detection

For gusts below the absolute threshold, the script employs a neighborhood-based spike detection algorithm. Given a sequence of gust measurements, we search for "calm" reference values before and after the suspected outlier:

$$
\mathcal{C}_{prev} = \{g_j : j < i \land g_j < \theta_{calm}\}
$$

$$
\mathcal{C}_{next} = \{g_k : k > i \land g_k < \theta_{calm}\}
$$

Where $\theta_{calm} = 10$ km/h defines the calm wind threshold.

The algorithm selects the nearest calm value from each set:

$$
c_{prev} = \max\{g_j \in \mathcal{C}_{prev} : j = \max\{k : k < i \land g_k < \theta_{calm}\}\}
$$

$$
c_{next} = \min\{g_k \in \mathcal{C}_{next} : k = \min\{j : j > i \land g_j < \theta_{calm}\}\}
$$

A spike is detected when:

$$
g_i > 15 \land \bar{c} < 5 \land g_i > 5 \cdot \bar{c}
$$

Where the calm reference average is:

$$
\bar{c} = \frac{c_{prev} + c_{next}}{2}
$$

#### 1.3 Correction Method

When an outlier is detected, the corrected value $\hat{g}_i$ is computed as the mean of the previous $n$ valid calm readings:

$$
\hat{g}_i = \frac{1}{|\mathcal{V}|} \sum_{g_j \in \mathcal{V}} g_j
$$

Where $\mathcal{V}$ contains up to $n=5$ previously corrected calm values ($g_j < \theta_{calm}$), ensuring that consecutive outliers don't propagate errors through the correction chain.

**Example:**

| Time | Original Gust | Corrected Gust | Status |
|------|--------------|----------------|--------|
| 09:44 PM | 2.09 | 2.09 | Valid |
| 09:49 PM | 27.19 | 2.09 | Outlier → Corrected |
| 09:54 PM | 20.92 | 2.09 | Outlier → Corrected |
| 09:59 PM | 0.00 | 0.00 | Valid |

### 2. Precipitation Accumulation Outlier Detection

Precipitation accumulation outliers require special handling because the data is cumulative — each reading represents total rainfall since midnight. A sensor error creates a permanent offset in all subsequent readings if not corrected.

#### 2.1 Trend-Aware Spike Detection

The algorithm maintains two parallel accumulation series:

- $A^{(o)}_i$ — Original sensor accumulation values
- $A^{(c)}_i$ — Corrected accumulation values

The inter-reading delta is computed from original values:

$$
\Delta_i = A^{(o)}_i - A^{(o)}_{i-1}
$$

The maximum allowable delta is scaled by the time interval:

$$
\Delta_{max}(\tau) = \Delta_{threshold} \cdot \frac{\tau}{5}
$$

Where:
- $\tau$ = Time elapsed since previous reading (minutes)
- $\Delta_{threshold} = 5$ mm (maximum expected rainfall in 5 minutes)

#### 2.2 Adaptive Threshold with Historical Context

To avoid false positives during legitimate heavy rainfall, the algorithm maintains a sliding window of recent rainfall deltas:

$$
\mathcal{R} = \{\Delta_j : j \in [i-N, i-1] \land \Delta_j > 0\}
$$

Where $N = 5$ (trend window size).

A reading is classified as an outlier only if it satisfies both conditions:

$$
\text{is\_outlier} = \begin{cases}
\text{true} & \text{if } \Delta_i > \Delta_{max}(\tau) \land \Delta_i > \mu_{\mathcal{R}} \cdot \lambda \\
\text{false} & \text{otherwise}
\end{cases}
$$

Where:
- $\mu_{\mathcal{R}} = \frac{1}{|\mathcal{R}|} \sum_{\Delta_j \in \mathcal{R}} \Delta_j$ (mean of recent positive deltas)
- $\lambda = 6$ (spike multiplier threshold)

This allows gradual rainfall intensification (e.g., 1mm → 2mm → 3mm → 5mm) while catching sudden unrealistic spikes (e.g., 0mm → 52mm).

#### 2.3 Correction Method

When an accumulation outlier is detected, the erroneous delta is zeroed:

$$
A^{(c)}_i = A^{(c)}_{i-1} + 0 = A^{(c)}_{i-1}
$$

The precipitation rate is recalculated from the corrected accumulation:

$$
R_i = \frac{A^{(c)}_i - A^{(c)}_{i-1}}{\tau / 60} = 0 \text{ mm/h}
$$

For non-outlier readings, the original delta is preserved:

$$
A^{(c)}_i = A^{(c)}_{i-1} + \Delta_i
$$

#### 2.4 Handling Consecutive Outliers

When the algorithm detects an outlier, the erroneous delta is **not** added to the recent history $\mathcal{R}$:

$$
\mathcal{R}_{i+1} = \begin{cases}
\mathcal{R}_i & \text{if is\_outlier} \\
\mathcal{R}_i \cup \{\Delta_i\} & \text{otherwise}
\end{cases}
$$

This prevents a chain reaction where one outlier corrupts the trend baseline, allowing subsequent outliers to slip through undetected.

**Example:**

| Time | Original Accum | Delta | Corrected Accum | Status |
|------|---------------|-------|-----------------|--------|
| 12:14 AM | 5.0 | 1.0 | 5.0 | Valid |
| 12:19 AM | 57.4 | 52.4 | 5.0 | Outlier → Zeroed |
| 12:24 AM | 110.2 | 52.8 | 5.0 | Outlier → Zeroed |
| 12:29 AM | 57.4 | 0.0 | 5.0 | Valid (flat reading) |

### 3. Viewing Outlier Corrections

Use the `--show-outlier-fixes` flag to display detailed correction information:

```bash
python3 import_csv.py your_data.csv --show-outlier-fixes --dry-run
```

**Sample Output:**
```
============================================================
DETAILED OUTLIER FIXES:
============================================================

--- Wind Gust Outliers (23) ---
  Row   1847 | 2025/08/15 09:49 PM | Gust:  27.19 ->   2.09 km/h (avg wind: 1.13 km/h)
  Row   1848 | 2025/08/15 09:54 PM | Gust:  20.92 ->   2.09 km/h (avg wind: 0.32 km/h)
  Row  35563 | 2025/12/06 12:19 AM | Gust: 129.49 ->   3.22 km/h (avg wind: 0.00 km/h)

--- Precipitation Accumulation Outliers (4) ---
  Row 35563 | 2025/12/06 12:19 AM | Accum:  57.40 ->   5.00 mm (delta: 52.40 -> 0.00 mm)
  Row 35564 | 2025/12/06 12:24 AM | Accum: 110.20 ->   5.00 mm (delta: 52.80 -> 0.00 mm)

--- Precipitation Rate Corrections (4) ---
  Row 35563 | 2025/12/06 12:19 AM | Rate: 629.08 ->   0.00 mm/h
  Row 35564 | 2025/12/06 12:24 AM | Rate: 633.89 ->   0.00 mm/h
============================================================
```

### 4. Algorithm Constants

| Constant | Value | Description |
|----------|-------|-------------|
| `MAX_WIND_GUST_KMH` | 80.0 | Absolute maximum plausible wind gust |
| `CALM_THRESHOLD` | 10.0 | Wind gust threshold for "calm" classification |
| `NUM_PREV_VALUES` | 5 | Number of previous values for correction averaging |
| `MAX_PRECIP_DELTA_MM` | 5.0 | Maximum expected precipitation in 5 minutes |
| `MAX_PRECIP_RATE_MMH` | 60.0 | Maximum plausible precipitation rate |
| `TREND_WINDOW` | 5 | Number of recent deltas for trend calculation |
| `SPIKE_MULTIPLIER` | 6.0 | Threshold multiplier for spike detection |

---

## Data Transformations

### Timestamp Conversion

**Input:** `Date,Time` columns in Madrid timezone (Europe/Madrid)

**Example:**
- CSV: `2025/07/09,07:44 PM`
- Madrid timezone: `2025-07-09 19:44:00 Europe/Madrid`
- UTC (stored): `2025-07-09 17:44:00 UTC` (CEST is UTC+2)

**Python Implementation:**
```python
from datetime import datetime
import pytz

MADRID_TZ = pytz.timezone('Europe/Madrid')
UTC_TZ = pytz.UTC

def parse_timestamp(date_str: str, time_str: str) -> int:
    datetime_str = f"{date_str} {time_str}"
    dt_naive = datetime.strptime(datetime_str, "%Y/%m/%d %I:%M %p")
    dt_madrid = MADRID_TZ.localize(dt_naive)
    dt_utc = dt_madrid.astimezone(UTC_TZ)
    return int(dt_utc.timestamp() * 1_000_000_000)
```

**DST Handling:** pytz automatically handles Daylight Saving Time transitions. No manual adjustment needed.

### Compass Direction Conversion

**Input:** Cardinal and intercardinal compass directions

**Mapping Table:**

| Compass | Degrees | Compass | Degrees | Compass | Degrees | Compass | Degrees |
|---------|---------|---------|---------|---------|---------|---------|---------|
| N / NORTH | 0 | NNE | 22.5 | NE / NORTHEAST | 45 | ENE | 67.5 |
| E / EAST | 90 | ESE | 112.5 | SE / SOUTHEAST | 135 | SSE | 157.5 |
| S / SOUTH | 180 | SSW | 202.5 | SW / SOUTHWEST | 225 | WSW | 247.5 |
| W / WEST | 270 | WNW | 292.5 | NW / NORTHWEST | 315 | NNW | 337.5 |

**Supported Formats:**
- Abbreviations: `N`, `NE`, `E`, `SE`, `S`, `SW`, `W`, `NW`
- Intercardinals: `NNE`, `ENE`, `ESE`, `SSE`, `SSW`, `WSW`, `WNW`, `NNW`
- Full words: `NORTH`, `NORTHEAST`, `EAST`, `SOUTHEAST`, `SOUTH`, `SOUTHWEST`, `WEST`, `NORTHWEST`
- Case-insensitive: `north`, `North`, `NORTH` all work

**Default:** Unknown or empty values default to `0.0` (North)

### Decimal Separator Auto-Detection

**Purpose:** Handle both European (comma) and US/International (dot) decimal formats

**Examples:**
- European: `25,17` → `25.17`
- US/International: `25.17` → `25.17`

**Python Implementation:**
```python
def parse_decimal(value: str) -> float:
    if ',' in value and '.' not in value:
        return float(value.replace(',', '.'))  # European format
    else:
        return float(value)  # US/International format
```

---

## Derived Field Calculations

All derived fields match the formulas used by Telegraf for live sensor data (see [telegraf/telegraf.conf](../telegraf/telegraf.conf) lines 107-281).

### 1. Feels-Like Temperature (`feels_like_C`)

**Logic:**
1. If `temperature < 10°C` AND `wind_avg_km_h > 4.8`: Calculate wind chill
2. Else if `temperature > 27°C` AND `humidity > 40%`: Calculate heat index
3. Else: `feels_like = temperature`

**Wind Chill Formula** (Environment Canada):
```python
def calculate_wind_chill(temp_c: float, wind_kmh: float) -> float:
    if temp_c < 10 and wind_kmh > 4.8:
        wc = (13.12 + 0.6215 * temp_c - 11.37 * (wind_kmh ** 0.16) +
              0.3965 * temp_c * (wind_kmh ** 0.16))
        return round(wc, 2)
    return temp_c
```

**Heat Index Formula** (Rothfusz regression, Celsius adaptation):
```python
def calculate_heat_index(temp_c: float, humidity: float) -> float:
    if temp_c > 27 and humidity > 40:
        c1, c2, c3 = -8.78469475556, 1.61139411, 2.33854883889
        c4, c5, c6 = -0.14611605, -0.012308094, -0.0164248277778
        c7, c8, c9 = 0.002211732, 0.00072546, -0.000003582

        T = temp_c
        RH = humidity

        hi = (c1 + c2*T + c3*RH + c4*T*RH + c5*T*T + c6*RH*RH +
              c7*T*T*RH + c8*T*RH*RH + c9*T*T*RH*RH)
        return round(hi, 2)
    return temp_c
```

**Example:**
- Temperature: 32°C, Humidity: 70%, Wind: 5 km/h
- Result: Heat index = ~38°C (feels hotter due to humidity)

### 2. Wind Speed Beaufort Scale (`wind_speed_beaufort`)

**Purpose:** Classify wind speed into standardized Beaufort scale (0-12)

**Mapping:**

| Beaufort | Wind Speed (km/h) | Description |
|----------|-------------------|-------------|
| 0 | < 1 | Calm |
| 1 | 1-4 | Light air |
| 2 | 5-10 | Light breeze |
| 3 | 11-18 | Gentle breeze |
| 4 | 19-27 | Moderate breeze |
| 5 | 28-37 | Fresh breeze |
| 6 | 38-48 | Strong breeze |
| 7 | 49-60 | High wind |
| 8 | 61-73 | Gale |
| 9 | 74-87 | Strong gale |
| 10 | 88-101 | Storm |
| 11 | 102-116 | Violent storm |
| 12 | ≥ 117 | Hurricane force |

**Data Type:** Integer (0-12)

### 3. UV Risk Level (`uv_risk_level`)

**Purpose:** Categorize UV index into risk levels

**Mapping:**

| Risk Level | UV Index Range | Category | Color |
|------------|----------------|----------|-------|
| 0 | 0-2.9 | Low | Green |
| 1 | 3-5.9 | Moderate | Yellow |
| 2 | 6-7.9 | High | Orange |
| 3 | 8-10.9 | Very High | Red |
| 4 | ≥ 11 | Extreme | Purple |

**Data Type:** Integer (0-4)

### 4. Light Lux (`light_lux`)

**Purpose:** Convert solar radiation to illuminance

**Formula:**
```python
light_lux = solar_radiation_w_m2 × 126.7
```

**Reverse of Telegraf conversion:**
```flux
# Telegraf: telegraf.conf line 224
solar_radiation = light_lux / 126.7

# Import script (reverse):
light_lux = solar_radiation × 126.7
```

**Example:**
- CSV Solar: 64.5 W/m²
- Calculated Lux: 8,172 lux

### 5. Battery Fields (`battery_ok`, `battery_status_pct`)

**Purpose:** Maintain schema consistency (CSV has no battery data)

**Values:**
- `battery_ok`: `1.0` (always "OK")
- `battery_status_pct`: `100.0` (always full)

**Note:** These fields are required by the InfluxDB schema but not meaningful for CSV imports.

### 6. Daily Rain Total (`daily_rain_total`)

**Purpose:** Track cumulative rain since sensor startup

**CSV Import Limitation:** Cannot calculate without previous day's state

**Value:** `0.0` for all CSV imports

**Note:** For daily aggregation in dashboards, use `daily_rain_current` with `max()` function instead (see [GRAFANA.md](GRAFANA.md) Monthly Trends dashboard).

---

## Verification

### 1. Verify Import in InfluxDB UI

1. Open http://localhost:8086
2. Navigate to **Data Explorer**
3. Run this query:

```flux
from(bucket: "weather_data")
  |> range(start: 2025-07-09T00:00:00Z, stop: 2025-07-10T00:00:00Z)
  |> filter(fn: (r) => r._measurement == "rtl433")
  |> filter(fn: (r) => r.model == "CSV_Import")
  |> limit(n: 10)
```

4. **Expected Result:** Should see 10 data points with `model=CSV_Import` tag

### 2. Verify All Fields Present

```flux
from(bucket: "weather_data")
  |> range(start: 2025-07-09T00:00:00Z, stop: 2025-07-10T00:00:00Z)
  |> filter(fn: (r) => r._measurement == "rtl433" and r.model == "CSV_Import")
  |> filter(fn: (r) =>
      r._field == "temperature_C" or
      r._field == "feels_like_C" or
      r._field == "pressure_hPa" or
      r._field == "solar_radiation_w_m2" or
      r._field == "wind_dir_deg" or
      r._field == "daily_rain_current"
  )
  |> limit(n: 20)
```

**Expected:** 19 fields per timestamp (see [Field Mapping](#field-mapping))

### 3. Verify Compass Conversion

**CSV Row:**
```csv
2025/07/09,07:44 PM,25.17,18.28,66.0,SSE,0.64,9.49,1017.27,0.0,4.32,0.0,64.5
```

**Query:**
```flux
from(bucket: "weather_data")
  |> range(start: 2025-07-09T17:44:00Z, stop: 2025-07-09T17:45:00Z)
  |> filter(fn: (r) => r._measurement == "rtl433" and r.model == "CSV_Import")
  |> filter(fn: (r) => r._field == "wind_dir_deg")
```

**Expected Result:** `wind_dir_deg = 157.5` (SSE = 157.5°)

### 4. Verify Timestamp Conversion

**CSV Time:** `2025/07/09,07:44 PM` (Madrid timezone)

**Expected UTC:**
- Summer (CEST = UTC+2): `2025-07-09 17:44:00 UTC`
- Winter (CET = UTC+1): Would be `18:44 UTC`

**Query:**
```flux
from(bucket: "weather_data")
  |> range(start: 2025-07-09T17:44:00Z, stop: 2025-07-09T17:45:00Z)
  |> filter(fn: (r) => r._measurement == "rtl433" and r.model == "CSV_Import")
  |> filter(fn: (r) => r._field == "temperature_C")
```

**Expected:** Data point at `17:44:00 UTC` with `temperature_C = 25.17`

### 5. Verify Derived Field Calculations

**Check feels_like calculation:**

```flux
from(bucket: "weather_data")
  |> range(start: 2025-07-09T00:00:00Z, stop: 2025-07-10T00:00:00Z)
  |> filter(fn: (r) => r._measurement == "rtl433" and r.model == "CSV_Import")
  |> filter(fn: (r) => r._field == "temperature_C" or r._field == "feels_like_C" or r._field == "humidity" or r._field == "wind_avg_km_h")
  |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> limit(n: 5)
```

**Expected:** When temp > 27°C and humidity > 40%, `feels_like_C` should be higher than `temperature_C` (heat index)

### 6. Verify Grafana Dashboards

1. Open http://localhost:3000
2. Navigate to **Weather Station Dashboard**
3. Set time range to cover imported date range (e.g., July 9-10, 2025)
4. **Expected:** All panels show data:
   - Temperature chart shows values
   - Wind direction shows correct compass points
   - Daily rain shows accumulation
   - UV index displays correctly

5. Navigate to **Weather Monthly Trends**
6. Set time range to July 2025
7. **Expected:** Daily aggregations show:
   - Daily rain bars (e.g., July 9: 4.32mm, July 12: 11.94mm)
   - Temperature min/max/avg lines
   - Wind trends

---

## Troubleshooting

### Error: "INFLUXDB_ADMIN_TOKEN not set"

**Cause:** Missing or invalid `.env` file

**Solution:**
```bash
# Check if .env file exists
ls -la .env

# Check if token is set
cat .env | grep INFLUXDB_ADMIN_TOKEN

# If missing, copy from .env.example or set manually
echo "INFLUXDB_ADMIN_TOKEN=your-token-here" >> .env
```

### Error: "Module 'influxdb_client' not found"

**Cause:** Python dependencies not installed

**Solution:**
```bash
pip3 install -r requirements.txt
```

### Error: "Connection refused to InfluxDB"

**Cause:** InfluxDB container not running or wrong URL

**Solution:**
```bash
# Check if InfluxDB is running
docker compose ps influxdb

# If not running, start it
docker compose up -d influxdb

# Test connection
curl http://localhost:8086/health
```

**Expected Response:**
```json
{"status": "pass"}
```

### Error: "Parsing CSV row failed"

**Example:**
```
ERROR parsing row 2: 'Date'
Row data: {'Date,Time,Temperature_C,...': '2025/07/09,07:44 PM,...'}
```

**Cause:** CSV delimiter mismatch or malformed header

**Solutions:**

1. **Check CSV delimiter:**
   - US format uses comma: `Date,Time,Temperature_C`
   - European format uses semicolon: `Date;Time;Temperature_C`
   - Script auto-detects, but header must match

2. **Verify header row:**
   ```bash
   head -n 1 your_file.csv
   ```

   Should be:
   ```
   Date,Time,Temperature_C,Dew_Point_C,Humidity_%,Wind,Speed_kmh,Gust_kmh,Pressure_hPa,Precip_Rate_mm,Precip_Accum_mm,UV,Solar_w/m2
   ```

3. **Check for extra spaces or quotes:**
   - Remove: `" Date "` → `Date`
   - Fix: `Date ,Time` → `Date,Time`

### Error: "field type conflict"

**Example:**
```
influxdb_client.rest.ApiException: (422)
field type conflict: input field "wind_dir_deg" on measurement "rtl433" is type integer, already exists as type float
```

**Cause:** InfluxDB field already exists with different data type

**Solutions:**

1. **Check existing field types in InfluxDB:**
   ```flux
   import "influxdata/influxdb/schema"

   schema.fieldKeys(bucket: "weather_data", predicate: (r) => r._measurement == "rtl433")
   ```

2. **For wind_dir_deg:** Must be float (script uses `float`)
3. **For uv_risk_level:** Must be int (script uses `int`)
4. **For wind_speed_beaufort:** Must be int (script uses `int`)

**If mismatch persists:** Contact administrator to check InfluxDB schema or clear test data

### Error: "Invalid compass direction"

**Example:**
```
WARNING: Unknown compass direction 'WNE' at row 1234, defaulting to 0°
```

**Cause:** CSV contains non-standard wind direction

**Solution:**

1. **Valid directions:**
   - 16-point compass: N, NNE, NE, ENE, E, ESE, SE, SSE, S, SSW, SW, WSW, W, WNW, NW, NNW
   - Full words: NORTH, NORTHEAST, EAST, SOUTHEAST, SOUTH, SOUTHWEST, WEST, NORTHWEST

2. **Fix CSV data:**
   - Replace invalid values with nearest valid direction
   - Or manually set to `0` (will default to North)

### Imported Data Not Showing in Grafana

**Symptoms:**
- Import succeeded but Grafana panels show "No data"
- Time range covers imported dates

**Solutions:**

1. **Check Grafana time range:**
   - Ensure time range covers imported dates
   - Example: If imported July 2025, set range to July 1-31, 2025

2. **Check panel filters:**
   - Some panels may filter by `model` tag
   - Remove or modify filter to include CSV imports:
   ```flux
   # Include all data (remove model filter)
   |> filter(fn: (r) => r._measurement == "rtl433")

   # Or explicitly include CSV imports
   |> filter(fn: (r) => r._measurement == "rtl433" and (r.model == "CSV_Import" or r.model != "CSV_Import"))
   ```

3. **Check field names:**
   - Verify panel queries use correct field names
   - Example: `daily_rain_current` (not `daily_rain_total` for CSV imports)

4. **Refresh Grafana:**
   - Click refresh button (top right)
   - Or set auto-refresh interval

### Timestamps Off by Hours

**Symptoms:**
- Data appears at wrong time in Grafana
- Example: 7:44 PM shows as 5:44 PM

**Cause:** Timezone mismatch between CSV, script, and Grafana

**Solutions:**

1. **Verify CSV timezone:**
   - Script assumes `TZ=Europe/Madrid` from `.env`
   - If CSV uses different timezone, update `.env`:
   ```bash
   TZ=Your/Timezone
   ```

2. **Check Grafana timezone:**
   - Dashboard Settings → Time options → Timezone
   - Should be "Browser time" or "Europe/Madrid"

3. **Verify InfluxDB stores UTC:**
   ```bash
   docker exec influxdb influx query \
     'from(bucket:"weather_data")
      |> range(start: 2025-07-09T17:44:00Z, stop: 2025-07-09T17:45:00Z)
      |> filter(fn: (r) => r._measurement == "rtl433")
      |> limit(n: 1)' \
     --org weather --token $INFLUXDB_ADMIN_TOKEN
   ```

   Timestamp should be in UTC (17:44 UTC for 19:44 CEST Madrid time)

### Daily Rain Shows Zero in Dashboard

**Symptoms:**
- CSV had rain data (e.g., `Precip_Accum_mm = 4.32`)
- Dashboard shows 0mm for that day

**Cause:** Dashboard query uses wrong field or aggregation

**Solution:**

1. **Check dashboard query** (should use `daily_rain_current` with `max`):
   ```flux
   from(bucket: "weather_data")
     |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
     |> filter(fn: (r) => r._measurement == "rtl433")
     |> filter(fn: (r) => r._field == "daily_rain_current")  # NOT daily_rain_total
     |> aggregateWindow(every: 1d, fn: max, createEmpty: false)  # NOT fn: last
     |> timeShift(duration: -1h)
   ```

2. **If using `daily_rain_total`:** Change to `daily_rain_current` (CSV imports set total to 0)

3. **If using `fn: last`:** Change to `fn: max` (gets daily maximum accumulation)

4. **Restart Grafana** if dashboard changes don't apply:
   ```bash
   docker compose restart grafana
   ```

### Slow Import Performance

**Symptoms:**
- Import takes > 5 minutes for 50k rows
- Progress bar moves slowly

**Solutions:**

1. **Increase batch size** (edit `import_csv.py` line ~280):
   ```python
   batch_size = 5000  # Instead of 1000
   ```

2. **Disable duplicate checking** (if certain no overlaps):
   - Comment out lines ~250-260 in `import_csv.py`
   - **Warning:** This will overwrite existing data

3. **Import during low-load periods:**
   - Stop live data collection temporarily
   - Or run import at night when Grafana usage is low

4. **Check InfluxDB resources:**
   ```bash
   docker stats influxdb
   ```

   If CPU/memory at 100%, increase Docker resources

### Duplicate Data After Re-import

**Symptoms:**
- Ran import twice
- Now see duplicate data points in Grafana

**Cause:** Duplicate detection failed or was disabled

**Solution:**

1. **Verify duplicate detection ran:**
   ```
   Checking for existing data in InfluxDB...
   Found 45537 existing timestamps in range
   Skipping 45537 existing data points
   ```

2. **If duplicates exist, delete CSV imports:**
   ```flux
   // WARNING: This deletes ALL CSV imports
   // Run in InfluxDB Data Explorer

   from(bucket: "weather_data")
     |> range(start: 2025-07-01T00:00:00Z, stop: 2026-02-01T00:00:00Z)
     |> filter(fn: (r) => r._measurement == "rtl433" and r.model == "CSV_Import")
     |> delete()
   ```

3. **Re-run import with duplicate detection enabled**

---

## Advanced Usage

### Importing Multiple CSV Files

```bash
# Import files sequentially
for file in *.csv; do
  echo "Importing $file..."
  python3 import_csv.py "$file"
done
```

### Custom Time Range

Edit `import_csv.py` to filter by date:

```python
# Add after line ~220 (in parse_csv_row)
min_date = datetime(2025, 7, 1, tzinfo=UTC_TZ)
max_date = datetime(2025, 8, 1, tzinfo=UTC_TZ)

if not (min_date <= dt_utc <= max_date):
    return None  # Skip this row
```

### Export InfluxDB Data to CSV

```bash
# Export data to CSV format
docker exec influxdb influx query \
  'from(bucket:"weather_data")
   |> range(start: 2025-07-01T00:00:00Z, stop: 2025-08-01T00:00:00Z)
   |> filter(fn: (r) => r._measurement == "rtl433")
   |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")' \
  --org weather --token $INFLUXDB_ADMIN_TOKEN --raw > export.csv
```

---

## Summary

The CSV import script provides a robust way to import historical weather data into your InfluxDB instance. Key features:

✅ **Automatic timezone conversion** (Madrid → UTC with DST handling)
✅ **Compass direction conversion** (16-point compass + full words → degrees)
✅ **Derived field calculation** (feels-like, Beaufort, UV risk, lux)
✅ **Outlier detection & correction** (wind gust spikes, precipitation anomalies)
✅ **Duplicate detection** (skip existing timestamps, optional overwrite)
✅ **Batch processing** (efficient 1000-point batches)
✅ **Data tagging** (`model=CSV_Import` for filtering)
✅ **Dry-run mode** (test before import)
✅ **Format flexibility** (US and European CSV formats)

For additional help, see:
- [FIELDS.md](FIELDS.md) - Complete field reference with data types
- [GRAFANA.md](GRAFANA.md) - Dashboard setup and customization
- [README.md](../README.md#importing-historical-data-from-csv) - Quick start guide
