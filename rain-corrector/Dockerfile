FROM python:3.11-slim

# Install required packages
RUN pip install influxdb-client

# Copy the script
COPY scripts/daily_rain_corrector.py /app/daily_rain_corrector.py

# Install cron
RUN apt-get update && apt-get install -y cron && rm -rf /var/lib/apt/lists/*

# Create cron job to run at 00:10 daily
RUN echo "10 0 * * * cd /app && python3 daily_rain_corrector.py >> /var/log/rain_corrector.log 2>&1" > /etc/cron.d/rain-corrector
RUN chmod 0644 /etc/cron.d/rain-corrector
RUN crontab /etc/cron.d/rain-corrector

# Create log file
RUN touch /var/log/rain_corrector.log

WORKDIR /app

CMD ["cron", "-f"]