# PowerShell script to query weather data from InfluxDB
# Usage: .\query_weather.ps1 [-Limit 10] [-Field "temperature_C"]
# If no Field is specified, shows all fields for each record in SQL-style table format

param(
    [int]$Limit = 10,
    [string]$Field = $null
)

# Load environment variables from .env file
if (Test-Path ".env") {
    Get-Content ".env" | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+)=(.+)$') {
            $key = $matches[1].Trim()
            $value = $matches[2].Trim()
            [Environment]::SetEnvironmentVariable($key, $value, "Process")
        }
    }
}

# Get credentials from environment
$token = $env:INFLUXDB_ADMIN_TOKEN
$org = $env:INFLUXDB_ORG
$bucket = $env:INFLUXDB_BUCKET

if (-not $token -or -not $org -or -not $bucket) {
    Write-Host "Error: Missing environment variables. Make sure .env file exists with:" -ForegroundColor Red
    Write-Host "  INFLUXDB_ADMIN_TOKEN" -ForegroundColor Red
    Write-Host "  INFLUXDB_ORG" -ForegroundColor Red
    Write-Host "  INFLUXDB_BUCKET" -ForegroundColor Red
    exit 1
}

# Get current date for the query (use a wide range to account for timezone differences)
$today = Get-Date -Format "yyyy-MM-dd"
$yesterday = (Get-Date).AddDays(-1).ToString("yyyy-MM-dd")

# Build the Flux query to pivot data (convert from long to wide format)
if ($Field) {
    # Query specific field
    Write-Host "Querying weather data (field: $Field, limit: $Limit)..." -ForegroundColor Cyan
    $fluxQuery = "from(bucket:\`"$bucket\`") |> range(start: ${yesterday}T00:00:00Z, stop: ${today}T23:59:59Z) |> filter(fn: (r) => r._field == \`"$Field\`") |> sort(columns: [\`"_time\`"], desc: true) |> limit(n: $Limit)"
    $pivotData = $false
} else {
    # Query all fields and pivot to show as rows
    Write-Host "Querying latest weather data (all fields, limit: $Limit records)..." -ForegroundColor Cyan
    $fluxQuery = "from(bucket:\`"$bucket\`") |> range(start: ${yesterday}T00:00:00Z, stop: ${today}T23:59:59Z) |> pivot(rowKey:[\`"_time\`"], columnKey: [\`"_field\`"], valueColumn: \`"_value\`") |> sort(columns: [\`"_time\`"], desc: true) |> limit(n: $Limit)"
    $pivotData = $true
}

# Use curl.exe explicitly to avoid PowerShell's Invoke-WebRequest alias
$csvData = & curl.exe -s -X POST "http://localhost:8086/api/v2/query?org=$org" `
  -H "Authorization: Token $token" `
  -H "Content-Type: application/vnd.flux" `
  -H "Accept: application/csv" `
  -d $fluxQuery

if (-not $csvData) {
    Write-Host "Error: No data returned from InfluxDB" -ForegroundColor Red
    exit 1
}

# Parse CSV and display as table
$lines = $csvData -split "`n" | Where-Object { $_ -and $_.Trim() }
$dataStarted = $false
$headers = @()
$records = @()

foreach ($line in $lines) {
    # Skip InfluxDB metadata/annotation lines
    if ($line -match '^#') { continue }

    # First non-comment line is headers
    if (-not $dataStarted) {
        $headers = ($line -split ',').Trim()
        $dataStarted = $true
        continue
    }

    # Parse data rows - handle quoted CSV values
    $values = @()
    $currentValue = ""
    $inQuotes = $false

    for ($i = 0; $i -lt $line.Length; $i++) {
        $char = $line[$i]

        if ($char -eq '"') {
            $inQuotes = -not $inQuotes
        }
        elseif ($char -eq ',' -and -not $inQuotes) {
            $values += $currentValue.Trim('"')
            $currentValue = ""
        }
        else {
            $currentValue += $char
        }
    }
    # Add the last value
    $values += $currentValue.Trim('"')

    if ($values.Count -eq $headers.Count) {
        $record = New-Object PSObject
        for ($i = 0; $i -lt $headers.Count; $i++) {
            $headerName = $headers[$i]
            # Skip internal InfluxDB columns that start with underscore except _time, _value, _field
            if ($headerName -match '^_(start|stop|measurement)$') { continue }

            try {
                $record | Add-Member -MemberType NoteProperty -Name $headerName -Value $values[$i] -ErrorAction Stop
            }
            catch {
                # Skip if property already exists or has issues
                continue
            }
        }
        $records += $record
    }
}

if ($records.Count -eq 0) {
    Write-Host "No data found in the specified time range." -ForegroundColor Yellow
    exit 0
}

Write-Host ""
Write-Host "=" * 120
Write-Host ""

if ($pivotData) {
    # For pivoted data, select relevant columns in a logical order
    # First, check which properties exist
    $sampleRecord = $records[0]
    $availableProps = $sampleRecord.PSObject.Properties.Name

    # Build select object dynamically based on available properties
    $selectProps = @()

    # Define desired columns in order
    $columnMap = @(
        @{Name='Time'; Prop='_time'},
        @{Name='Temp_C'; Prop='temperature_C'},
        @{Name='Humid%'; Prop='humidity'},
        @{Name='WindAvg'; Prop='wind_avg_km_h'},
        @{Name='WindMax'; Prop='wind_max_km_h'},
        @{Name='WindDir'; Prop='wind_dir_deg'},
        @{Name='Rain_mm'; Prop='rain_mm'},
        @{Name='Light'; Prop='light_lux'},
        @{Name='UVI'; Prop='uvi'},
        @{Name='RSSI'; Prop='rssi'},
        @{Name='SNR'; Prop='snr'},
        @{Name='Noise'; Prop='noise'},
        @{Name='Freq1'; Prop='freq1'},
        @{Name='Freq2'; Prop='freq2'},
        @{Name='Batt'; Prop='battery_ok'},
        @{Name='Model'; Prop='model'},
        @{Name='ID'; Prop='id'},
        @{Name='Chan'; Prop='channel'},
        @{Name='MIC'; Prop='mic'},
        @{Name='Mod'; Prop='mod'}
    )

    foreach ($col in $columnMap) {
        if ($availableProps -contains $col.Prop) {
            $selectProps += @{N=$col.Name; E=[scriptblock]::Create("`$_.$($col.Prop)")}
        }
    }

    if ($selectProps.Count -gt 0) {
        $records | Select-Object -Property $selectProps | Format-Table -AutoSize
    } else {
        # Fallback: show all properties
        $records | Format-Table -AutoSize
    }
} else {
    # For single field queries, show standard output
    $records | Format-Table -AutoSize
}

Write-Host ""
Write-Host "Query complete! Showing $($records.Count) record(s)" -ForegroundColor Green
Write-Host ""
Write-Host "Usage examples:" -ForegroundColor Yellow
Write-Host "  .\query_weather.ps1                          # Show all fields (default)" -ForegroundColor Cyan
Write-Host "  .\query_weather.ps1 -Limit 20                # Show 20 latest records" -ForegroundColor Cyan
Write-Host "  .\query_weather.ps1 -Field 'temperature_C'   # Show only temperature" -ForegroundColor Cyan
Write-Host "  .\query_weather.ps1 -Field 'humidity' -Limit 5  # Show 5 humidity records" -ForegroundColor Cyan
Write-Host ""
