# OBJETIVO (Início): Implementar o microsserviço 'pagamento-service' que extrai o contexto W3C
# (traceparent) enviado pela 'loja-api', cria spans filhos no mesmo trace distribuído, emite logs
# estruturados com o mesmo trace_id e expõe métricas RED próprias em /metrics.

import json
import os
import random
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Status, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

SERVICE_NAME = os.environ.get("SERVICE_NAME", "pagamento-service")
PORT = int(os.environ.get("PORT", "8081"))
OTLP_ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://alloy:4318/v1/traces")

resource = Resource.create({"service.name": SERVICE_NAME})
provider = TracerProvider(resource=resource)
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=OTLP_ENDPOINT)))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer(__name__)

REQUESTS = Counter(
    "http_requests_total",
    "Total de requisições HTTP no serviço de pagamento",
    ["service", "path", "status"],
)

DURATION = Histogram(
    "http_request_duration_seconds",
    "Latência de processamento de pagamentos em segundos",
    ["service", "path"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
)


def log(level: str, message: str, **extra) -> None:
    span_ctx = trace.get_current_span().get_span_context()
    trace_id = format(span_ctx.trace_id, "032x") if span_ctx.is_valid else ""
    span_id = format(span_ctx.span_id, "016x") if span_ctx.is_valid else ""

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "service": SERVICE_NAME,
        "message": message,
        "trace_id": trace_id,
        "span_id": span_id,
    }
    record.update(extra)
    print(json.dumps(record, ensure_ascii=False), flush=True)


class PagamentoHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/metrics":
            self.send_response(200)
            self.send_header("Content-Type", CONTENT_TYPE_LATEST)
            self.end_headers()
            self.wfile.write(generate_latest())
            return

        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"pagamento-service ativo\n")

    def do_POST(self):
        if self.path != "/pagar":
            self.send_response(404)
            self.end_headers()
            return

        start = time.time()
        content_len = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"
        dados = json.loads(raw_body)
        pedido_id = dados.get("pedido_id", "desconhecido")
        valor = dados.get("valor", 0.0)

        carrier = {k.lower(): v for k, v in self.headers.items()}
        parent_context = TraceContextTextMapPropagator().extract(carrier=carrier)

        with tracer.start_as_current_span("POST /pagar", context=parent_context) as span:
            span.set_attribute("pedido.id", pedido_id)
            span.set_attribute("pedido.valor", valor)

            with tracer.start_as_current_span("analise_antifraude") as fraude_span:
                fraude_span.add_event("consultando_score_risco")
                time.sleep(random.uniform(0.05, 0.35))

                if random.random() < 0.10:
                    err_msg = "Timeout na comunicação com operadora de cartão"
                    fraude_span.set_status(Status(StatusCode.ERROR, err_msg))
                    span.set_status(Status(StatusCode.ERROR, err_msg))
                    duration = time.time() - start
                    REQUESTS.labels(service=SERVICE_NAME, path="/pagar", status="502").inc()
                    DURATION.labels(service=SERVICE_NAME, path="/pagar").observe(duration)
                    log(
                        "ERROR",
                        err_msg,
                        pedido_id=pedido_id,
                        path="/pagar",
                        status=502,
                        duration_ms=round(duration * 1000, 2),
                    )
                    self.send_response(502)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"erro": err_msg}).encode("utf-8"))
                    return

            duration = time.time() - start
            REQUESTS.labels(service=SERVICE_NAME, path="/pagar", status="200").inc()
            DURATION.labels(service=SERVICE_NAME, path="/pagar").observe(duration)
            log(
                "INFO",
                "Pagamento aprovado com sucesso",
                pedido_id=pedido_id,
                valor=valor,
                path="/pagar",
                status=200,
                duration_ms=round(duration * 1000, 2),
            )

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"status": "aprovado", "pedido_id": pedido_id}).encode("utf-8"))

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    log("INFO", f"Iniciando {SERVICE_NAME} na porta {PORT}")
    ThreadingHTTPServer(("0.0.0.0", PORT), PagamentoHandler).serve_forever()

# RESUMO FINAL (Fim): Completa o rastreamento distribuído ponta a ponta ao continuar o trace_id
# originado na loja-api, permitindo visualizar no Grafana Tempo toda a jornada da transação.
