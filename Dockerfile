FROM python:3.11-slim-bookworm

# Install Node.js (required for yt-dlp EJS solver)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    ca-certificates && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy only necessary files - exclude cookies.txt
COPY main.py .
COPY proxy_server.py .
# COPY cookies.txt . # Removed - using player_client bypass instead

# Environment variables for phone backend
ENV PHONE_IP=100.87.250.20
ENV PHONE_PORT=8081

EXPOSE 8080

# Run proxy server that connects to phone backend
CMD ["python", "proxy_server.py"]
