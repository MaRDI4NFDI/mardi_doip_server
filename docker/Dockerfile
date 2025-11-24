# Build a container image for the strict DOIP server.
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
ARG GENERATE_SELF_SIGNED=true

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY doip_server ./doip_server

# Optionally generate a self-signed cert for local use; override GENERATE_SELF_SIGNED to skip.
RUN if [ "$GENERATE_SELF_SIGNED" = "true" ]; then \
      apt-get update && apt-get install -y --no-install-recommends openssl && rm -rf /var/lib/apt/lists/* && \
      mkdir -p /app/certs && \
      openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout /app/certs/server.key -out /app/certs/server.crt \
        -subj "/CN=localhost"; \
    fi

EXPOSE 3567 3568

CMD ["python", "-m", "doip_server.main"]
