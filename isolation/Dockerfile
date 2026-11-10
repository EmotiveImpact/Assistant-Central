FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pilot/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && groupadd --gid 21001 atlas \
    && groupadd --gid 21002 beacon \
    && groupadd --gid 21003 controller \
    && useradd --uid 21001 --gid 21001 --no-create-home atlas \
    && useradd --uid 21002 --gid 21002 --no-create-home beacon \
    && useradd --uid 21003 --gid 21003 --no-create-home controller \
    && mkdir -p /private/atlas /private/beacon \
    && chown 21001:21001 /private/atlas \
    && chown 21002:21002 /private/beacon \
    && chmod 0700 /private/atlas /private/beacon
COPY pilot /app/pilot
COPY isolation /app/isolation
USER 21003:21003
CMD ["python", "-B", "-c", "import time; time.sleep(3600)"]
