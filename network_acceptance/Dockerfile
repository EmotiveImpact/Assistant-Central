FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pilot/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && groupadd --gid 22001 atlas && groupadd --gid 22002 beacon \
    && useradd --uid 22001 --gid 22001 --no-create-home atlas \
    && useradd --uid 22002 --gid 22002 --no-create-home beacon \
    && mkdir -p /private/atlas /private/beacon /quarantine/atlas /quarantine/beacon /tls/atlas /tls/beacon \
    && chown 22001:22001 /private/atlas /quarantine/atlas /tls/atlas \
    && chown 22002:22002 /private/beacon /quarantine/beacon /tls/beacon \
    && chmod 0700 /private/atlas /private/beacon /quarantine/atlas /quarantine/beacon /tls/atlas /tls/beacon
COPY pilot /app/pilot
COPY network_acceptance /app/network_acceptance
USER 22001:22001
CMD ["python", "-B", "-c", "import time; time.sleep(3600)"]
