FROM python:3.11-slim-bookworm

# Install minimal dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ca-certificates && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY main.py .
COPY track_resolver.py .

# Create cache directory with proper permissions
RUN mkdir -p /tmp/cantio_cache && chmod 777 /tmp/cantio_cache

EXPOSE 8080

# Run backend
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
