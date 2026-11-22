FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PUBLIC_BIND=1 \
    MODEL_PROVIDER=off \
    PORT=8000
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home --no-log-init app

COPY app.py providers.py project.py example.json ./
COPY web/index.html web/style.css web/ui.js web/diagram.js ./web/
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ['PORT'] + '/health', timeout=3).close()"
CMD ["sh", "-c", "exec gunicorn --bind \"0.0.0.0:${PORT:-8000}\" --workers 1 --threads 4 --timeout 125 --access-logfile - app:application"]
