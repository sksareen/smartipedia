FROM python:3.12-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml .
RUN uv sync --no-dev --no-install-project

COPY . .

# Optional local Country MMDB. If it's missing, geo.py downloads it on startup.
ENV GEOIP_DB_PATH=/app/data/GeoLite2-Country.mmdb

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
