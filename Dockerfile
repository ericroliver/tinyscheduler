# TinyScheduler Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for layer caching
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/
COPY tinyscheduler ./

# Create directories for state/config
RUN mkdir -p /data /config

# Make CLI executable
RUN chmod +x tinyscheduler

ENV PYTHONPATH=/app
ENV TINYSCHEDULER_DATA_DIR=/data
ENV TINYSCHEDULER_CONFIG_DIR=/config

ENTRYPOINT ["./tinyscheduler"]
CMD ["run", "--daemon"]
