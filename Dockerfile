FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MTG_TRACKER_DB_PATH=/data/collection.db

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && groupadd --system --gid 10001 mtgtracker \
    && useradd --system --uid 10001 --gid mtgtracker --home-dir /nonexistent --shell /usr/sbin/nologin mtgtracker \
    && mkdir -p /data \
    && chown mtgtracker:mtgtracker /data

COPY --chown=mtgtracker:mtgtracker app.py api.py ./
COPY --chown=mtgtracker:mtgtracker templates ./templates
COPY --chown=mtgtracker:mtgtracker static ./static
COPY --chown=mtgtracker:mtgtracker collection.db /data/collection.db

USER mtgtracker
EXPOSE 9006

CMD ["gunicorn", "--workers", "1", "--bind", "0.0.0.0:9006", "--access-logfile", "-", "--error-logfile", "-", "app:app"]
