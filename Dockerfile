FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PORT=10000 FASTAPI_URL=http://127.0.0.1:8000
WORKDIR /app
COPY requirements.txt ./
RUN pip install -r requirements.txt
COPY . .
RUN useradd --create-home appuser && mkdir -p .runtime && chown -R appuser:appuser /app
USER appuser
EXPOSE 10000
CMD ["python", "scripts/start_render.py"]
