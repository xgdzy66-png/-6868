FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv/app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --system --uid 10001 botuser
COPY app ./app
COPY static ./static
COPY scripts ./scripts
USER botuser
EXPOSE 3000
CMD ["sh", "-c", "exec gunicorn 'app.server:app' --bind 0.0.0.0:${PORT:-3000} --workers 1 --threads 4 --timeout 30 --access-logfile - --error-logfile -"]
