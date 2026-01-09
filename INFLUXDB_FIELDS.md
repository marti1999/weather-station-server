# InfluxDB Field Mapping for RTL_433 Data

This document shows how JSON fields from rtl_433 are stored in InfluxDB.

## JSON Input Example
```json
{
  "time": "2026-01-09 21:19:03",
  "model": "Vevor-7in1",
  "id": 3092,
  "channel": 0,
  "battery_ok": 1,
  "temperature_C": 7.500,
  "humidity": 64,
  "wind_avg_km_h": 0.600,
  "wind_max_km_h": 1.333,
  "wind_dir_deg": 260,
  "rain_mm": 343.209,
  "uvi": 0.000,
  "light_lux": 0,
  "mic": "CHECKSUM",
  "mod": "FSK",
  "freq1": 868.407,
  "freq2": 868.301,
  "rssi": -5.198,
  "snr": 22.967,
  "noise": -28.165
}
```

## InfluxDB Storage Classification

### 1. Timestamp (Used for `_time`)
- `time` - Parsed as timestamp (format: "2006-01-02 15:04:05")

### 2. Measurement Name
- **Fixed value**: `rtl433` (set by `name_override` in telegraf.conf)

### 3. Tags (Indexed, used for filtering/grouping)
Configured via `tag_keys` in telegraf.conf:
- `model` - Device model (e.g., "Vevor-7in1")
- `id` - Device ID (e.g., 3092)
- `channel` - RF channel (e.g., 0)
- `battery_ok` - Battery status (e.g., 1)
- `mic` - Message integrity check (e.g., "CHECKSUM")
- `mod` - Modulation type (e.g., "FSK")

Additional tags added by Telegraf:
- `host` - Container hostname
- `topic` - MQTT topic (e.g., "rtl_433/Vevor-7in1/3092")

### 4. Fields (Numeric values stored)
All numeric fields are stored as measurements:
- `temperature_C` - Temperature in Celsius
- `humidity` - Relative humidity percentage
- `wind_avg_km_h` - Average wind speed
- `wind_max_km_h` - Maximum wind gust
- `wind_dir_deg` - Wind direction in degrees
- `rain_mm` - Cumulative rainfall
- `uvi` - UV index
- `light_lux` - Light level in lux
- `freq1` - First frequency
- `freq2` - Second frequency
- `rssi` - Received signal strength indicator
- `snr` - Signal-to-noise ratio
- `noise` - Noise level

### 5. NOT Sent to InfluxDB
✅ **All fields are now being sent!** (Updated configuration)

Previously missing:
- ~~`mod`~~ - Now stored as a **tag** (as of latest configuration)

## Summary Statistics

| Category | Count | Fields |
|----------|-------|--------|
| **Timestamp** | 1 | `time` |
| **Measurement** | 1 | Fixed: `rtl433` |
| **Tags** | 8 | `model`, `id`, `channel`, `battery_ok`, `mic`, `mod`, `host`, `topic` |
| **Fields** | 13 | `temperature_C`, `humidity`, `wind_avg_km_h`, `wind_max_km_h`, `wind_dir_deg`, `rain_mm`, `uvi`, `light_lux`, `freq1`, `freq2`, `rssi`, `snr`, `noise` |
| **Not Sent** | 0 | None - all fields captured! |

## InfluxDB Line Protocol Example (Updated)
```
rtl433,battery_ok=1,channel=0,host=0b3ea07ee0d9,id=3092,mic=CHECKSUM,mod=FSK,model=Vevor-7in1,topic=rtl_433/Vevor-7in1/3092 wind_dir_deg=243,freq2=868.28045,light_lux=0,temperature_C=7.3,uvi=0,rain_mm=343.20898,freq1=868.38682,wind_avg_km_h=0,rssi=-3.82294,noise=-27.0927,humidity=65,snr=23.26976,wind_max_km_h=0 1767993863000000000
```

Format breakdown:
- **Measurement**: `rtl433`
- **Tags**: `battery_ok=1,channel=0,host=0b3ea07ee0d9,id=3092,mic=CHECKSUM,mod=FSK,model=Vevor-7in1,topic=rtl_433/Vevor-7in1/3092`
- **Fields**: `wind_dir_deg=243,freq2=868.28045,light_lux=0,temperature_C=7.3,...`
- **Timestamp**: `1767993863000000000` (nanoseconds)

## Configuration Applied

The `mod` field is now configured in `telegraf/telegraf.conf`:

```toml
## Extract tags from these JSON fields
tag_keys = ["model", "id", "channel", "battery_ok", "mic", "mod"]

## String fields (non-numeric)
json_string_fields = ["model", "mic", "mod", "subtype", "raw_msg"]
```

✅ **All 20 JSON fields from rtl_433 are now stored in InfluxDB!**
