# Disposable acceptance only. Package installation occurs before network removal.
FROM node:24.22.1-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/owner-review \
    && /opt/owner-review/bin/pip install --no-cache-dir cryptography==50.0.0
ENV PATH="/opt/owner-review/bin:${PATH}"
WORKDIR /repo
