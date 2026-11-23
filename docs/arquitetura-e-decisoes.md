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

Os screenshots comprobatórios estão na pasta [`evidencias/`](../evidencias/), com legenda em [`evidencias/README.md`](../evidencias/README.md):

| Sinal | Arquivo | O que prova |
| :--- | :--- | :--- |
| Stack | `01-docker-compose-ps.png` | Os 8 containers ativos (`Up`). |
| Métricas + Logs | `02-grafana-dashboard-red.png` | Dashboard RED provisionado (Rate, Errors, Duration p95) e logs com `trace_id`. |
| Logs | `03-loki-logs-traceid.png` | Logs JSON no Loki e salto direto para o trace (campo derivado `TraceID`). |
| Traces | `04-tempo-trace-distribuido.png` | Trace `POST /checkout` atravessando `loja-api` e `pagamento-service` (5 spans, 2 serviços). |
| Correlação | `05-trace-para-logs.png`, `05b-trace-para-logs-loja-api.png` | Do trace para os logs da mesma requisição, via `trace_id`. |
| Métricas | `06-prometheus-targets.png` | Os 4 targets do Prometheus em `UP`. |
| Erros (logs) | `07-loki-log-erro.png` | Logs `level="ERROR"` com `trace_id`. |
| Erros (traces) | `08b-tempo-trace-erro-checkout.png` | Trace de checkout com erro atravessando os dois serviços. |
| Erros (métricas) | `09-prometheus-erros.png` | Taxa de respostas 5xx por serviço e rota. |

> Os erros observados são **intencionais**: a rota `/erro` é chamada de propósito pelo gerador de tráfego (~5%) e o `pagamento-service` falha em ~10% das chamadas, para que haja falhas a investigar.

## 6. Como o App Funciona

A aplicação é uma loja virtual simplificada, escrita em Python (servidor HTTP da biblioteca padrão), dividida em **dois microsserviços** que se comunicam por HTTP. O código está em `services/loja-api/app.py` e `services/pagamento-service/app.py`.

### `loja-api` (porta 8080) — serviço de entrada

| Rota | O que faz | Comportamento simulado |
| :--- | :--- | :--- |
| `GET /` | Página inicial (`{"status": "loja online"}`) | Resposta rápida (poucos ms) |
| `GET /produtos` | Lista de produtos | Atraso de ~20 a 90 ms |
| `POST /checkout` | Finaliza uma compra | Reserva estoque e chama o `pagamento-service` (fluxo abaixo) |
| `GET /erro` | Rota de falha proposital | Lança uma exceção e responde HTTP 500 |
| `GET /metrics` | Métricas no formato Prometheus | Lido pelo Prometheus (pull) |

Qualquer outra rota é contabilizada como `path="outro"` nas métricas, para não criar séries novas a cada URL diferente.

### Fluxo do `POST /checkout`

1. A `loja-api` abre o span raiz `HTTP POST /checkout` e gera um número de pedido (`pedido.id`) e um valor (`pedido.valor`).
2. Span `reservar_estoque`: simula a verificação e a reserva do estoque (eventos `verificando_disponibilidade_sku` e `estoque_reservado_com_sucesso`).
3. Span `chamar_pagamento_service`: faz `POST /pagar` no `pagamento-service`, enviando o cabeçalho W3C `traceparent` (propagação de contexto).
4. O `pagamento-service` extrai o `traceparent` e continua o **mesmo trace**: span `POST /pagar` e, dentro dele, `analise_antifraude`, que simula uma consulta de risco de ~50 a 350 ms.
5. Em cerca de **10% das chamadas** o pagamento falha de propósito (erro 502, "Timeout na comunicação com operadora de cartão"). A `loja-api` converte isso em **HTTP 500** para o cliente e marca o span com erro.
6. Se tudo der certo, a resposta é HTTP 200 com o pedido e o status `aprovado`.

### `pagamento-service` (porta 8081) — serviço interno

Expõe `POST /pagar` (aprovação do pagamento), `GET /` (verificação de que está ativo) e `GET /metrics`. Tem as próprias métricas, logs e spans, todos com `service="pagamento-service"`.

### Por que esse app é bom para observabilidade

- **Tem falhas e lentidão previsíveis** (`/erro`, 10% de falha no pagamento, latência variável), o que dá algo para investigar nos três sinais.
- **Atravessa dois serviços**, o que permite mostrar um trace distribuído e a correlação entre log e trace pelo `trace_id`.
- **O gerador de tráfego** (`trafego/gerar-trafego.sh`, serviço `trafego` no compose) mantém requisições contínuas: cerca de 45% `POST /checkout`, 30% `/produtos`, 20% `/` e 5% `/erro`.

<!-- RESUMO FINAL (Fim): Documentação completa exigida pelos critérios de avaliação do Projeto Final,
     justificando escolhas técnicas de arquitetura, cardinalidade, estatística e correlação. -->
