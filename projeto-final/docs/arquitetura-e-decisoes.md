<!-- OBJETIVO (Início): Documentação técnica obrigatória do Projeto Final detalhando arquitetura,
     responsabilidades dos componentes, fluxo de cada sinal (protocolos/portas) e decisões de instrumentação. -->

# Documento de Arquitetura e Decisões de Instrumentação

## 1. Visão Geral da Arquitetura

O sistema implementa uma arquitetura de microsserviços instrumentada ponta a ponta com a stack open source do ecossistema Grafana (**LGTM + Alloy**) e **OpenTelemetry**:

```text
                       ┌─ stdout (JSON + trace_id) ──► Alloy ──► Loki ────────┐
[loja-api :8080] ──────┼─ traces (OTLP/HTTP :4318) ──► Alloy ──► Tempo ───────┼──► Grafana (:3000)
       │               └─ /metrics (Pull) ◄─────────── Prometheus (:9090) ────┘
       │ (W3C traceparent)
       ▼
[pagamento-service :8081] ──► (emite os mesmos 3 sinais para Alloy e Prometheus)
```

---

## 2. Responsabilidades de Cada Componente

| Componente | Papel na Stack | Responsabilidade Técnica |
| :--- | :--- | :--- |
| **`loja-api`** | Produtor de Telemetria | Porta de entrada HTTP (`:8080`). Gera logs JSON, expõe `/metrics`, cria spans raiz/manuais e injeta o contexto W3C (`traceparent`) ao chamar pagamentos. |
| **`pagamento-service`** | Produtor de Telemetria | Serviço downstream (`:8081`). Extrai `traceparent`, continua a árvore de spans com o mesmo `trace_id`, emite logs JSON e expõe `/metrics`. |
| **`trafego`** | Gerador de Carga | Executa requisições HTTP contínuas contra as rotas da `loja-api` para manter séries temporais, logs e traces ativos. |
| **`alloy`** | Coletor / Agente | Lê logs via `/var/run/docker.sock` (containers com `logging=alloy`) e recebe traces via OTLP (`4317`/`4318`), agrupando em lotes antes de exportar. |
| **`loki`** | Backend de Logs | Armazena logs comprimidos em chunks no disco local, indexando apenas labels de baixa cardinalidade (`service`, `container`). |
| **`prometheus`** | Backend de Métricas | Realiza coleta ativa (*scrape*) a cada `5s` nos endpoints `/metrics` e armazena séries temporais no TSDB local. |
| **`tempo`** | Backend de Traces | Recebe spans OTLP gRPC do Alloy e persiste blocos de traces localmente para busca via TraceQL e visualização de grafos de serviço. |
| **`grafana`** | Visualização e Correlação | Interface única (`:3000`) provisionada via código (`provisioning/`) com datasources integrados (`derivedFields` e `tracesToLogsV2`) e dashboard RED. |

---

## 3. Caminho de Cada Sinal (Protocolo, Direção e Portas)

1. **Logs (Modelo Push via Agente):**
   * `loja-api` e `pagamento-service` escrevem JSON estruturado no `stdout` → o Docker Engine grava no driver `json-file` → o **Grafana Alloy** lê via `/var/run/docker.sock`, aplica *relabeling* (`service`, `container`) e envia via **HTTP POST** (`http://loki:3100/loki/api/v1/push`) para o **Loki** → o **Grafana** consulta o Loki na porta `3100`.
2. **Métricas (Modelo Pull / Scrape):**
   * `loja-api` (`:8080/metrics`) e `pagamento-service` (`:8081/metrics`) mantêm contadores e histogramas em memória → o **Prometheus** busca os dados a cada `5s` via **HTTP GET** → o **Grafana** executa queries PromQL na porta `9090`.
3. **Traces (Modelo Push via OTLP):**
   * O SDK OpenTelemetry nos serviços exporta spans em lote via **OTLP/HTTP** para `http://alloy:4318/v1/traces` → o **Grafana Alloy** processa (`otelcol.processor.batch`) e encaminha via **OTLP/gRPC** para `tempo:4317` → o **Grafana** consulta o **Tempo** via API HTTP na porta `3200`.

---

## 4. Decisões de Instrumentação e Boas Práticas Aplicadas

* **Controle de Cardinalidade nas Métricas e Labels:**
  * Nos labels de métricas Prometheus (`service`, `path`, `status`) e de indexação do Loki (`service`, `container`), utilizamos exclusivamente valores finitos e controlados. Rotas desconhecidas são normalizadas para `path="outro"`, evitando explosão de séries no TSDB e de streams no Loki.
  * Identificadores únicos de alta cardinalidade (`request_id`, `pedido_id`, `trace_id`) foram mantidos apenas no corpo JSON dos logs e nos atributos dos spans do Tempo.
* **Uso de Histograma em vez de Média/Summary para Latência:**
  * Escolhemos `Histogram` (`http_request_duration_seconds`) com buckets calibrados (`0.01s` a `2.5s`) para permitir o cálculo correto de percentis (`histogram_quantile(0.95, sum by (le) (...))`) agregando múltiplas instâncias sem cair na armadilha estatística da média de percentis.
* **Correlação Nativa entre os Três Pilares:**
  * A função `log()` extrai dinamicamente `trace_id` e `span_id` do contexto ativo do OpenTelemetry (`trace.get_current_span()`), permitindo saltar de qualquer linha de log no Loki diretamente para a cascata de spans no Tempo e vice-versa.
* **Spans Manuais e Eventos Semânticos:**
  * Além dos spans de borda HTTP, instrumentamos spans internos (`reservar_estoque`, `chamar_pagamento_service`, `analise_antifraude`) com atributos de negócio (`pedido.id`, `pedido.valor`) e eventos (`add_event`) para isolar gargalos internos dentro de uma mesma transação.

---

## 5. Evidências de Funcionamento

Os screenshots comprobatórios estão salvos na pasta `evidencias/`:
1. `evidencias/01-docker-compose-ps.png` — Todos os 8 containers ativos (`Up`).
2. `evidencias/02-grafana-dashboard-red.png` — Dashboard RED mostrando Rate, Errors, Duration (p95) e logs.
3. `evidencias/03-loki-logs-traceid.png` — Consulta LogQL exibindo logs JSON estruturados com `trace_id` e link para o Tempo.
4. `evidencias/04-tempo-trace-distribuido.png` — Trace distribuído atravessando `loja-api` e `pagamento-service` com spans manuais.

<!-- RESUMO FINAL (Fim): Documentação completa exigida pelos critérios de avaliação do Projeto Final,
     justificando escolhas técnicas de arquitetura, cardinalidade, estatística e correlação. -->
