# Build from repository root:
#   docker build -f services/flowfish-l7-collector/Dockerfile .
FROM python:3.11-slim

WORKDIR /app

COPY services/flowfish-l7-collector/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/flowfish-l7-collector/app/ ./app/

EXPOSE 8080

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
