# OBJETIVO (Início): Construir a imagem do microsserviço loja-api com Python 3.12 e as bibliotecas
# oficiais do Prometheus Client e OpenTelemetry SDK + Exportador OTLP/HTTP.

FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    prometheus-client==0.21.1 \
    opentelemetry-api==1.30.0 \
    opentelemetry-sdk==1.30.0 \
    opentelemetry-exporter-otlp-proto-http==1.30.0

COPY app.py .

ENV PYTHONUNBUFFERED=1
ENV SERVICE_NAME=loja-api
ENV PORT=8080

EXPOSE 8080

CMD ["python", "app.py"]

# RESUMO FINAL (Fim): Gera uma imagem leve e reprodutível do serviço de entrada loja-api.
