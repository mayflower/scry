FROM mcr.microsoft.com/playwright/python:v1.55.0-noble

WORKDIR /app

# Install Google Chrome Stable for reliable CDP in containers
RUN apt-get update && apt-get install -y wget gnupg ca-certificates && \
    wget -qO- https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google.gpg && \
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list && \
    apt-get update && apt-get install -y google-chrome-stable fonts-liberation && \
    rm -rf /var/lib/apt/lists/*

# Install project
COPY pyproject.toml README.md ./
COPY src ./src
COPY scripts ./scripts
COPY tests ./tests
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir . && \
    pip install --no-cache-dir pytest pytest-asyncio && \
    python -m playwright install chromium

EXPOSE 8000

ENV HEADLESS=true \
    ARTIFACTS_ROOT=/app/artifacts \
    SCREENSHOT_DIR=/app/artifacts/screenshots \
    GENERATED_CODE_DIR=/app/artifacts/generated_code \
    HTML_SNAPSHOTS_DIR=/app/artifacts/html \
    EVENT_BACKEND=redis \
    REDIS_URL=redis://redis:6379/0 \
    NAV_BACKEND=playwright

ENV CDP_URL=http://127.0.0.1:9222
CMD ["/bin/sh","-lc","/usr/bin/google-chrome-stable --headless=new --no-sandbox --disable-dev-shm-usage --disable-gpu --remote-debugging-address=127.0.0.1 --remote-debugging-port=9222 >/tmp/chrome.log 2>&1 & exec uvicorn universal_scraper.app:create_app --factory --host 0.0.0.0 --port 8000"]
