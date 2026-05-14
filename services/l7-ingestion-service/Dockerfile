# Build from repository root:
#   docker build -f services/l7-ingestion-service/Dockerfile .
FROM python:3.11-slim

WORKDIR /app

COPY services/l7-ingestion-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install grpcio-tools

COPY proto/l7_ingestion_service.proto /app/proto/
RUN python -m grpc_tools.protoc -I/app/proto --python_out=/app --grpc_python_out=/app /app/proto/l7_ingestion_service.proto

COPY services/l7-ingestion-service/app/ ./app/

EXPOSE 5006

CMD ["python", "-m", "app.main"]
