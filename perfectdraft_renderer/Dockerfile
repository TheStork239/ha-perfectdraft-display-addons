FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy

WORKDIR /app

# Ensure container points to pre-installed browsers in the base image
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Install Pillow for image quantization and Floyd-Steinberg dithering
RUN pip install --no-cache-dir playwright==1.48.0 Pillow

COPY render_server.py /app/

CMD ["python3", "-u", "/app/render_server.py"]