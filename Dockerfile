FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 1000 --create-home dashboard
COPY app_core ./app_core
COPY backend ./backend
COPY scripts ./scripts
COPY data/file.geojson ./data/file.geojson
RUN chown -R dashboard:dashboard /app
ARG VCS_REF
ENV ENERGY_CODE_COMMIT=$VCS_REF
USER dashboard
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
