# OBJETIVO (Início): Construir a imagem do microsserviço downstream 'pagamento-service'
# com suporte a Prometheus Client e OpenTelemetry SDK para continuar traces distribuídos.

FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    prometheus-client==0.21.1 \
    opentelemetry-api==1.30.0 \
    opentelemetry-sdk==1.30.0 \
    opentelemetry-exporter-otlp-proto-http==1.30.0

COPY app.py .

ENV PYTHONUNBUFFERED=1
ENV SERVICE_NAME=pagamento-service
ENV PORT=8081

EXPOSE 8081

CMD ["python", "app.py"]

# RESUMO FINAL (Fim): Empacota o serviço de pagamentos com as mesmas bibliotecas de telemetria.
