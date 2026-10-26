FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create non-root user with home directory for gunicorn control socket
RUN groupadd -r appuser && \
    useradd -r -g appuser -m -d /home/appuser -s /bin/sh appuser

COPY . .

# Collect static files during build to generate manifest
# Use DJANGO_DEBUG=False to ensure manifest storage is used
RUN DJANGO_DEBUG=False DJANGO_SECRET_KEY=build-time-key python manage.py collectstatic --noinput

# Change ownership to appuser
RUN chown -R appuser:appuser /app

COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 8000

# Switch to non-root user
USER appuser

# Set HOME for gunicorn/Python temp file writes
ENV HOME=/home/appuser

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["sh", "-c", "gunicorn HackFlow.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 3"]
