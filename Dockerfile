FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch==2.6.0 \
 && pip install -r backend/requirements.txt

COPY . .
# Models, index and the per-corpus sufficiency calibration are baked into the image,
# so the container starts offline and behaves exactly like the benchmarked system.
RUN python scripts/download_models.py  && python scripts/build_index.py  && python scripts/calibrate_sufficiency.py

EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"
CMD ["python", "-m", "uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000"]
