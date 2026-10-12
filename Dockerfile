FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy
WORKDIR /app
RUN pip install --no-cache-dir requests
COPY bot.py .
CMD ["python", "-u", "bot.py"]
