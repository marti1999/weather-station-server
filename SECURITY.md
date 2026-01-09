# Security Best Practices

This document outlines security considerations for your weather station server.

## Environment Variables

All sensitive credentials are stored in the `.env` file, which is excluded from version control.

### Files Containing Credentials

**Tracked in Git (Safe - Uses Environment Variables):**
- `docker-compose.yml` - References `${VARIABLE_NAME}` placeholders
- `telegraf/telegraf.conf` - References `$VARIABLE_NAME` placeholders
- `.env.example` - Template with placeholder values only

**NOT Tracked in Git (Contains Real Credentials):**
- `.env` - **Never commit this file!**
- `.claude/` - May contain sensitive configuration

### Initial Setup

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

2. Generate secure passwords:
   ```bash
   # Using openssl
   openssl rand -base64 32

   # Using PowerShell
   -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 32 | ForEach-Object {[char]$_})
   ```

3. Edit `.env` and update:
   - `INFLUXDB_ADMIN_PASSWORD`
   - `INFLUXDB_ADMIN_TOKEN`

### Production Recommendations

1. **Change all default passwords** before exposing to network
2. **Use strong, random tokens** for InfluxDB authentication
3. **Enable MQTT authentication** by editing `mosquitto/config/mosquitto.conf`:
   ```
   allow_anonymous false
   password_file /mosquitto/config/passwd
   ```

4. **Use HTTPS/TLS** if exposing services to the internet
5. **Implement firewall rules** to restrict access to ports:
   - 1883 (MQTT)
   - 8086 (InfluxDB)

6. **Regular backups** of InfluxDB data:
   ```bash
   docker exec influxdb influx backup /var/lib/influxdb2/backup
   ```

## Network Security

### Current Configuration
- All services run on Docker bridge network
- Ports exposed to host: 1883 (MQTT), 8086 (InfluxDB), 9001 (MQTT WebSocket)
- Anonymous MQTT access allowed (no authentication required)

### Recommended for Production
- Enable MQTT authentication
- Use reverse proxy (nginx) with HTTPS
- Restrict access with firewall rules
- Consider VPN for remote access

## Data Privacy

- Weather data is stored locally in Docker volumes
- No external services are contacted
- Data retention is unlimited by default (configure in InfluxDB if needed)

## Updating Credentials

If you need to change credentials after initial setup:

1. Update `.env` file with new values
2. Restart services:
   ```bash
   docker-compose down
   docker-compose up -d
   ```

3. For InfluxDB, you may need to recreate the admin user via the web UI

## Git Security

The `.gitignore` file is configured to exclude:
- `.env` and all `.env.*` files
- `.claude/` directory
- Docker volumes and logs
- Temporary files

**Before committing, verify no secrets are exposed:**
```bash
git diff --cached
```
