# Security Guide

Security best practices and recommendations for the weather station server.

## Table of Contents

- [Security Overview](#security-overview)
- [Default Security Posture](#default-security-posture)
- [Production Hardening](#production-hardening)
- [Network Security](#network-security)
- [Cloudflare Tunnel (Recommended for Public Access)](#cloudflare-tunnel-recommended-for-public-access)
- [Credential Management](#credential-management)
- [Container Security](#container-security)
- [Monitoring & Auditing](#monitoring--auditing)
- [Backup & Recovery](#backup--recovery)

---

## Security Overview

This weather station server is designed for **home/local network use**. The default configuration prioritizes ease of setup over security.

**Threat Model**:
- **In Scope**: Unauthorized access from local network, credential exposure
- **Out of Scope**: Advanced persistent threats, nation-state actors, DDoS attacks

**Key Principle**: Defense in depth - multiple layers of security.

---

## Default Security Posture

### Current State (Out of the Box)

| Component | Security Level | Notes |
|-----------|----------------|-------|
| **MQTT Broker** | ⚠️ Open | Anonymous connections allowed, no encryption |
| **InfluxDB** | 🔒 Protected | Token-based auth, default admin password |
| **Grafana** | 🔒 Protected | Password-protected, default admin password |
| **Docker Network** | 🔒 Isolated | Services communicate via internal network |
| **Ports Exposed** | ⚠️ Multiple | 1883, 8086, 3000 exposed to LAN |

### Critical Actions Required

**Before exposing to public internet:**
1. ✅ Change all default passwords
2. ✅ Enable MQTT authentication
3. ✅ Enable TLS/SSL on all services
4. ✅ Use reverse proxy (nginx/Traefik)
5. ✅ Implement firewall rules
6. ✅ Regular security updates

---

## Production Hardening

### Step 1: Change Default Credentials

**CRITICAL**: Default passwords are publicly known. Change immediately.

#### Generate Secure Passwords

```bash
# Linux/Mac/Git Bash
openssl rand -base64 32

# Windows PowerShell
-join ((48..57) + (65..90) + (97..122) | Get-Random -Count 32 | ForEach-Object {[char]$_})
```

#### Update `.env` File

```bash
# InfluxDB
INFLUXDB_ADMIN_PASSWORD=<generated-password>
INFLUXDB_ADMIN_TOKEN=<generated-token>

# Grafana
GRAFANA_ADMIN_PASSWORD=<generated-password>
```

**Important**: After changing, update tokens in:
- `telegraf/telegraf.conf` (INFLUXDB_ADMIN_TOKEN)
- Grafana datasource configuration (regenerated automatically from `.env`)

#### Restart Services

```bash
docker compose down
docker compose up -d
```

### Step 2: Enable MQTT Authentication

#### Create Password File

```bash
# Create password for MQTT user
docker exec -it mqtt-broker mosquitto_passwd -c /mosquitto/config/passwd weather_user
```

Enter password when prompted (use secure password).

#### Update Mosquitto Configuration

Edit `mosquitto/config/mosquitto.conf`:

```conf
# Disable anonymous access
allow_anonymous false

# Enable password authentication
password_file /mosquitto/config/passwd

# Optional: Restrict topic access
acl_file /mosquitto/config/acl.conf
```

#### Create ACL File (Optional)

Create `mosquitto/config/acl.conf`:

```conf
# Allow weather_user to publish to rtl_433 topics
user weather_user
topic write rtl_433/#

# Allow telegraf_user to subscribe
user telegraf_user
topic read rtl_433/#
```

#### Update RTL_433 Command

Add authentication:

```bash
-F "mqtt://weather_user:password@192.168.1.100:1883,retain=0,events=rtl_433[/model][/id]"
```

#### Update Telegraf Config

Edit `telegraf/telegraf.conf`:

```toml
[[inputs.mqtt_consumer]]
  servers = ["tcp://mosquitto:1883"]
  username = "telegraf_user"
  password = "secure-password"  # Or use environment variable
  topics = ["rtl_433/Vevor-7in1/+"]
```

#### Restart MQTT Broker

```bash
docker compose restart mosquitto
```

### Step 3: Enable TLS/SSL

#### Generate Self-Signed Certificates (for testing)

```bash
# Create certificates directory
mkdir -p mosquitto/certs

# Generate CA certificate
openssl req -new -x509 -days 365 -extensions v3_ca \
  -keyout mosquitto/certs/ca.key \
  -out mosquitto/certs/ca.crt \
  -subj "/CN=Weather Station CA"

# Generate server certificate
openssl genrsa -out mosquitto/certs/server.key 2048
openssl req -new -key mosquitto/certs/server.key \
  -out mosquitto/certs/server.csr \
  -subj "/CN=mqtt.local"

# Sign server certificate
openssl x509 -req -in mosquitto/certs/server.csr \
  -CA mosquitto/certs/ca.crt \
  -CAkey mosquitto/certs/ca.key \
  -CAcreateserial \
  -out mosquitto/certs/server.crt \
  -days 365
```

#### Update Mosquitto Configuration

Edit `mosquitto/config/mosquitto.conf`:

```conf
# TLS listener on port 8883
listener 8883
protocol mqtt
cafile /mosquitto/certs/ca.crt
certfile /mosquitto/certs/server.crt
keyfile /mosquitto/certs/server.key
require_certificate false
```

#### Update Docker Compose

Add port 8883 to `docker-compose.yml`:

```yaml
mosquitto:
  ports:
    - "1883:1883"  # Keep for local development
    - "8883:8883"  # TLS port
  volumes:
    - ./mosquitto/certs:/mosquitto/certs
```

#### Use TLS in Clients

```bash
# RTL_433 with TLS
-F "mqtts://weather_user:password@192.168.1.100:8883,retain=0,events=rtl_433[/model][/id],cacert=/path/to/ca.crt"

# Telegraf with TLS
[[inputs.mqtt_consumer]]
  servers = ["ssl://mosquitto:8883"]
  tls_ca = "/mosquitto/certs/ca.crt"
```

**Production Note**: Use certificates from Let's Encrypt or your organization's CA, not self-signed.

### Step 4: Implement Reverse Proxy

For public access, use a reverse proxy (nginx or Traefik) with HTTPS.

#### Example nginx Configuration

```nginx
server {
    listen 443 ssl http2;
    server_name weather.example.com;

    ssl_certificate /etc/letsencrypt/live/weather.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/weather.example.com/privkey.pem;

    # Grafana
    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # InfluxDB (if needed externally)
    location /influxdb/ {
        proxy_pass http://localhost:8086/;
        allow 192.168.1.0/24;  # Restrict to local network
        deny all;
    }
}
```

---

## Network Security

### Firewall Rules

#### Linux (ufw)

```bash
# Allow only from local network
sudo ufw allow from 192.168.1.0/24 to any port 1883 comment 'MQTT'
sudo ufw allow from 192.168.1.0/24 to any port 8086 comment 'InfluxDB'
sudo ufw allow from 192.168.1.0/24 to any port 3000 comment 'Grafana'

# Block from WAN
sudo ufw deny 1883
sudo ufw deny 8086
sudo ufw deny 3000
```

#### Windows Firewall

```powershell
# Allow inbound only from local network
New-NetFirewallRule -DisplayName "MQTT Local" `
  -Direction Inbound -Protocol TCP -LocalPort 1883 `
  -RemoteAddress 192.168.1.0/24 -Action Allow

# Block from public networks
New-NetFirewallRule -DisplayName "MQTT Block Public" `
  -Direction Inbound -Protocol TCP -LocalPort 1883 `
  -RemoteAddress 0.0.0.0/0 -Action Block -Priority 2
```

### Docker Network Isolation

#### Create Isolated Network

```yaml
# docker-compose.yml
networks:
  weather-internal:
    driver: bridge
    internal: true  # No external access
  weather-external:
    driver: bridge

services:
  mosquitto:
    networks:
      - weather-internal
      - weather-external  # MQTT needs external for RTL_433

  influxdb:
    networks:
      - weather-internal  # Internal only

  telegraf:
    networks:
      - weather-internal

  grafana:
    networks:
      - weather-internal
      - weather-external  # Grafana needs external for browser access
```

### Port Binding Restrictions

Bind services only to localhost if not needed externally:

```yaml
services:
  influxdb:
    ports:
      - "127.0.0.1:8086:8086"  # Only accessible from host

  grafana:
    ports:
      - "127.0.0.1:3000:3000"
```

Then access via SSH tunnel or reverse proxy.

---

## Cloudflare Tunnel (Recommended for Public Access)

Cloudflare Tunnel is the **recommended method** for exposing Grafana to the internet. It's more secure than traditional port forwarding or reverse proxies.

### Why Cloudflare Tunnel?

| Feature | Traditional Port Forward | Reverse Proxy | Cloudflare Tunnel |
|---------|-------------------------|---------------|-------------------|
| Exposes home IP | ✅ Yes | ✅ Yes | ❌ No |
| Requires open ports | ✅ Yes | ✅ Yes | ❌ No |
| DDoS protection | ❌ No | ❌ No | ✅ Yes |
| Free SSL certificates | ❌ No | ⚠️ Manual setup | ✅ Automatic |
| Connection direction | Inbound | Inbound | Outbound only |

### How It Works

```
Internet → Cloudflare Edge → Encrypted Tunnel → Your Server (outbound connection)
```

The tunnel runs as a Docker container that maintains an **outbound** connection to Cloudflare. No inbound ports need to be opened on your router.

### Setup Steps

1. **Create Cloudflare account**: https://dash.cloudflare.com
2. **Add your domain** to Cloudflare (update nameservers at registrar)
3. **Create tunnel** in [Zero Trust Dashboard](https://one.dash.cloudflare.com/):
   - **Networks** → **Tunnels** → **Create a tunnel**
   - Choose **Cloudflared** connector
   - Copy the tunnel token
4. **Configure public hostname**:
   - Subdomain: `grafana`
   - Domain: `yourdomain.com`
   - Type: `HTTP`
   - URL: `grafana:3000`
5. **Update `.env`**:
   ```bash
   CLOUDFLARE_TUNNEL_TOKEN=eyJ...your-token...
   GRAFANA_ROOT_URL=https://grafana.yourdomain.com
   ```
6. **Deploy**: `docker compose up -d`

### Grafana Security Settings

When exposed via tunnel, Grafana is hardened with these settings in `docker-compose.yml`:

```yaml
environment:
  # Prevent unauthorized account creation
  - GF_USERS_ALLOW_SIGN_UP=false
  - GF_USERS_ALLOW_ORG_CREATE=false
  # Cookie security (HTTPS)
  - GF_SECURITY_COOKIE_SECURE=true
  - GF_SECURITY_COOKIE_SAMESITE=strict
  - GF_SECURITY_DISABLE_GRAVATAR=true
  # Anonymous read-only access (optional)
  - GF_AUTH_ANONYMOUS_ENABLED=true
  - GF_AUTH_ANONYMOUS_ORG_ROLE=Viewer
```

**To require login for all users**: Set `GF_AUTH_ANONYMOUS_ENABLED=false`

### Additional Protection: Cloudflare Access

For sensitive dashboards, add Cloudflare Access (Zero Trust) authentication:

1. Go to **Access** → **Applications** → **Add an application**
2. Select **Self-hosted**
3. Set application domain: `grafana.yourdomain.com`
4. Configure identity providers (Email OTP, Google, GitHub, etc.)
5. Create allow policies for specific users/emails

This adds authentication **before** traffic reaches Grafana.

### Tunnel Monitoring

```bash
# Check tunnel status
docker logs cloudflare-tunnel

# Verify connection in Cloudflare dashboard
# Zero Trust → Networks → Tunnels → Your tunnel → Status should be "Healthy"
```

---

## Credential Management

### Environment Variable Best Practices

1. **Never Commit `.env`**: Already in `.gitignore`, keep it there
2. **Use Strong Passwords**: Minimum 16 characters, random
3. **Rotate Regularly**: Change passwords every 90 days
4. **Separate Accounts**: Don't reuse passwords across services

### Secrets Management (Advanced)

For production, use Docker Secrets:

```yaml
# docker-compose.yml
version: '3.8'

secrets:
  influxdb_token:
    file: ./secrets/influxdb_token.txt
  grafana_password:
    file: ./secrets/grafana_password.txt

services:
  influxdb:
    secrets:
      - influxdb_token
    environment:
      - INFLUXDB_ADMIN_TOKEN_FILE=/run/secrets/influxdb_token
```

Store secrets outside repository:

```bash
mkdir -p secrets
echo "your-secure-token" > secrets/influxdb_token.txt
chmod 600 secrets/*
```

### API Token Scoping (InfluxDB)

Create limited-scope tokens instead of using admin token:

1. Login to InfluxDB UI
2. Go to **Data** → **API Tokens**
3. Click **Generate API Token** → **Custom API Token**
4. Grant only required permissions:
   - Telegraf: Write access to `weather_data` bucket
   - Grafana: Read access to `weather_data` bucket

Update services to use scoped tokens.

---

## Container Security

### Run Containers as Non-Root

```yaml
services:
  influxdb:
    user: "1000:1000"  # Your user UID:GID
```

**Note**: Some images require root. Check documentation.

### Limit Container Resources

Prevent DoS via resource exhaustion:

```yaml
services:
  influxdb:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 1G
        reservations:
          memory: 512M
```

### Keep Images Updated

```bash
# Pull latest images
docker compose pull

# Rebuild and restart
docker compose up -d --force-recreate
```

Subscribe to security mailing lists:
- InfluxDB: https://www.influxdata.com/blog/category/security/
- Grafana: https://grafana.com/security/
- Mosquitto: https://mosquitto.org/blog/

### Image Scanning

```bash
# Scan for vulnerabilities
docker scan eclipse-mosquitto:latest
docker scan influxdb:2.7
docker scan grafana/grafana:latest
```

### Read-Only Filesystems

```yaml
services:
  telegraf:
    read_only: true
    tmpfs:
      - /tmp
```

**Note**: May break some functionality. Test thoroughly.

---

## Monitoring & Auditing

### Enable Audit Logging

#### InfluxDB Audit Log

Edit InfluxDB config or set environment variable:

```yaml
influxdb:
  environment:
    - INFLUXDB_HTTP_LOG_ENABLED=true
```

#### Mosquitto Connection Log

Edit `mosquitto/config/mosquitto.conf`:

```conf
log_dest file /mosquitto/log/mosquitto.log
log_type all
connection_messages true
```

#### Monitor Failed Login Attempts

```bash
# Check Grafana logs for failed logins
docker compose logs grafana | grep -i "failed login"

# Check InfluxDB logs for unauthorized access
docker compose logs influxdb | grep -i "unauthorized"
```

### Set Up Alerts

Use Grafana alerting for security events:
- No data received in 5 minutes (potential DoS or service down)
- Unexpected data volume spike (potential unauthorized access)
- Battery low (physical security - sensor tampering)

### Log Retention

```yaml
services:
  mosquitto:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

---

## Backup & Recovery

### What to Back Up

1. **InfluxDB Data**: Time-series database
2. **Grafana Config**: Dashboards and datasources
3. **Configuration Files**: `telegraf.conf`, `mosquitto.conf`
4. **Environment Variables**: `.env` file (encrypted)

### Backup InfluxDB

```bash
# Backup to local directory
docker exec influxdb influx backup /var/lib/influxdb2/backup \
  --bucket weather_data \
  --org weather

# Copy from container
docker cp influxdb:/var/lib/influxdb2/backup ./backups/influxdb-$(date +%Y%m%d)
```

### Automated Backup Script

```bash
#!/bin/bash
# backup.sh
BACKUP_DIR="./backups/$(date +%Y%m%d)"
mkdir -p "$BACKUP_DIR"

# Backup InfluxDB
docker exec influxdb influx backup /var/lib/influxdb2/backup
docker cp influxdb:/var/lib/influxdb2/backup "$BACKUP_DIR/influxdb"

# Backup Grafana
docker exec grafana cp -r /var/lib/grafana/grafana.db /var/lib/grafana/grafana.db.backup
docker cp grafana:/var/lib/grafana/grafana.db.backup "$BACKUP_DIR/grafana.db"

# Backup configs
cp -r telegraf/ "$BACKUP_DIR/"
cp -r mosquitto/config/ "$BACKUP_DIR/"
cp .env "$BACKUP_DIR/env.txt"

# Encrypt backup
tar czf "$BACKUP_DIR.tar.gz" "$BACKUP_DIR"
gpg --symmetric --cipher-algo AES256 "$BACKUP_DIR.tar.gz"
rm -rf "$BACKUP_DIR" "$BACKUP_DIR.tar.gz"

echo "Backup complete: $BACKUP_DIR.tar.gz.gpg"
```

### Restore from Backup

```bash
# Decrypt
gpg --decrypt backups/20260113.tar.gz.gpg > backup.tar.gz
tar xzf backup.tar.gz

# Restore InfluxDB
docker cp backup/influxdb influxdb:/var/lib/influxdb2/restore
docker exec influxdb influx restore /var/lib/influxdb2/restore

# Restore Grafana
docker cp backup/grafana.db grafana:/var/lib/grafana/grafana.db
docker compose restart grafana
```

### Off-Site Backups

For critical data, store backups off-site:
- Cloud storage (encrypted)
- NAS on different network
- External hard drive

```bash
# Example: rsync to NAS
rsync -avz --delete backups/ user@nas:/weather-backups/
```

---

## Security Checklist

### Initial Setup
- [ ] Changed all default passwords in `.env`
- [ ] Generated strong InfluxDB admin token
- [ ] Configured `.gitignore` to exclude `.env`
- [ ] Reviewed exposed ports in `docker-compose.yml`

### Production Deployment
- [ ] Enabled MQTT authentication
- [ ] Enabled TLS/SSL on MQTT (port 8883)
- [ ] Configured firewall rules (allow only local network)
- [ ] Set up Cloudflare Tunnel for external Grafana access (recommended)
- [ ] Configured Grafana security settings (disable sign-up, secure cookies)
- [ ] Created limited-scope API tokens for InfluxDB
- [ ] Implemented Docker network isolation
- [ ] Configured resource limits on containers

### Ongoing Maintenance
- [ ] Regular security updates (monthly)
- [ ] Password rotation (quarterly)
- [ ] Backup verification (weekly)
- [ ] Log review (weekly)
- [ ] Vulnerability scanning (monthly)

---

## Incident Response

### If Credentials Compromised

1. **Immediately**:
   - Change all passwords in `.env`
   - Regenerate InfluxDB tokens
   - Restart all services

2. **Investigate**:
   - Review logs for unauthorized access
   - Check InfluxDB for unusual queries
   - Verify Grafana user accounts

3. **Prevent Recurrence**:
   - Enable 2FA if available (Grafana Enterprise)
   - Implement IP allowlisting
   - Strengthen access controls

### If Unauthorized Access Detected

1. **Isolate**:
   ```bash
   docker compose down
   ```

2. **Preserve Evidence**:
   ```bash
   docker compose logs > incident-$(date +%Y%m%d-%H%M%S).log
   ```

3. **Analyze**:
   - Review logs for entry point
   - Check for data exfiltration
   - Identify compromised accounts

4. **Remediate**:
   - Patch vulnerabilities
   - Restore from clean backup if needed
   - Harden security posture

---

## Additional Resources

- **Docker Security**: https://docs.docker.com/engine/security/
- **OWASP Top 10**: https://owasp.org/www-project-top-ten/
- **InfluxDB Security**: https://docs.influxdata.com/influxdb/v2/admin/security/
- **Grafana Security**: https://grafana.com/docs/grafana/latest/setup-grafana/configure-security/
- **Mosquitto Security**: https://mosquitto.org/documentation/authentication-methods/
- **Cloudflare Tunnel**: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/
- **Cloudflare Access**: https://developers.cloudflare.com/cloudflare-one/policies/access/
