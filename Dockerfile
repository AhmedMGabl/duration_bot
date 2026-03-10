FROM python:3.11-slim

WORKDIR /app

# Install Chromium system dependencies (same as scrap_bot)
RUN apt-get update && apt-get install -y \
    libglib2.0-0 libnss3 libnspr4 libdbus-1-3 \
    libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
    libxrandr2 libgbm1 libasound2 libpango-1.0-0 libcairo2 \
    fonts-wqy-zenhei fonts-wqy-microhei \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright Chromium browser
RUN playwright install chromium

# Copy all application files
COPY app.py .
COPY db_init.py .
COPY dashboard_client.py .
COPY lark_sender.py .
COPY pipeline_cm_eg.py .
COPY screenshotter.py .
COPY crm_scraper_linux.py .
COPY data_prep.py .

# Create necessary directories
RUN mkdir -p /app/db /app/Input /app/Output /app/static

# Expose port
EXPOSE 5000

# Run the application
CMD ["python", "app.py"]
