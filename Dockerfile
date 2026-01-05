FROM python:3.11-slim

WORKDIR /app

# Copy requirements first for better caching
COPY scripts/requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the bridge script
COPY scripts/mqtt_influxdb_bridge.py .

# Enable unbuffered output
ENV PYTHONUNBUFFERED=1

# Run the bridge
CMD ["python", "-u", "mqtt_influxdb_bridge.py"]
