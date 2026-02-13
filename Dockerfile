FROM python:3.11-slim-bookworm

# Install dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    iptables \
    iproute2 && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install Tailscale
RUN curl -fsSL https://tailscale.com/install.sh | sh

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY main.py .
COPY proxy_server.py .
COPY tailscale-entrypoint.sh .
RUN chmod +x tailscale-entrypoint.sh

# Environment variables for phone backend
ENV PHONE_IP=100.87.250.20
ENV PHONE_PORT=8081
ENV SKIP_CHECKS=true

EXPOSE 8080

# Use entrypoint script to start Tailscale then proxy
CMD ["./tailscale-entrypoint.sh"]
