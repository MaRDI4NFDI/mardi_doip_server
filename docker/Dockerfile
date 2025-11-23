# Build a container image for the strict DOIP server.
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY doip_server ./doip_server

EXPOSE 3567 3568

CMD ["python", "-m", "doip_server.main"]
