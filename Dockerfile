FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser

COPY . .

# Collect static files during build to generate manifest
RUN python manage.py collectstatic --noinput

# Change ownership of app directory to appuser
RUN chown -R appuser:appuser /app

COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 8000

# Switch to non-root user
USER appuser

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["sh", "-c", "gunicorn HackFlow.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 3"]
