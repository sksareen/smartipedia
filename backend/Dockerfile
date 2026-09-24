FROM python:3.12-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml .
RUN uv sync --no-dev --no-install-project

# Country-only GeoIP database. The IP is looked up in memory and discarded;
# only a two-letter country code is stored. Build continues if the download fails.
ENV GEOIP_DB_PATH=/app/data/GeoLite2-Country.mmdb
RUN python -c "\
import pathlib, sys, urllib.request
path = pathlib.Path('/app/data/GeoLite2-Country.mmdb')
path.parent.mkdir(parents=True, exist_ok=True)
url = 'https://github.com/P3TERX/GeoLite.mmdb/releases/latest/download/GeoLite2-Country.mmdb'
try:
    urllib.request.urlretrieve(url, path)
    print('downloaded', path, 'bytes', path.stat().st_size)
except Exception as e:
    print('GeoIP download failed:', e, file=sys.stderr)
"

COPY . .

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
