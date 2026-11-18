<!-- OBJETIVO (Início): Guia operacional completo do Projeto Final para o avaliador,
     descrevendo como subir toda a stack com um único comando, gerar carga e consultar os 3 sinais. -->

# Projeto Final — Observabilidade Ponta a Ponta (Métricas, Logs e Traces)

**Disciplina:** Fundamentos de Observabilidade: Métricas, Logs e Traces  
**Professor:** Mateus Valgueiro  
**Repositório:** `https://github.com/dhuberto/observabilidade`  

---

## 1. Como Subir Toda a Stack (Um Único Comando)

Execute: `git clone https://github.com/dhuberto/observabilidade.git`:

```bash
cd ~/observabilidade

docker compose up -d --build
```

Verifique se todos os **8 serviços** estão ativos (`Up`):

```bash
docker compose ps
```

Serviços iniciados automaticamente:
* `loja-api` (`http://localhost:8080`) — Microsserviço de entrada instrumentado
* `pagamento-service` (`http://localhost:8081`) — Microsserviço downstream de pagamentos
* `trafego` — Gerador automático de requisições HTTP contínuas
* `grafana` (`http://localhost:3000`) — Visualização unificada e correlação
* `prometheus` (`http://localhost:9090`) — Coleta e armazenamento de métricas (Pull)
* `loki` (`http://localhost:3100`) — Armazenamento de logs estruturados
* `tempo` (`http://localhost:3200`) — Armazenamento de traces distribuídos
* `alloy` (`http://localhost:12345`) — Coletor unificado de Logs (Docker) e Traces (OTLP)

---

## 2. Como Gerar Tráfego (Automático e Manual)

1. **Automático (já ativo):** O container `trafego` executa `trafego/gerar-trafego.sh` continuamente assim que o `docker compose up` termina.
2. **Manual (opcional via terminal):**
   ```bash
   curl -i -X POST http://localhost:8080/checkout
   curl -i http://localhost:8080/produtos
   curl -i http://localhost:8080/erro
   ```

---

## 3. Como Acessar o Grafana e Visualizar Cada Sinal

* **URL:** `http://localhost:3000`
* **Usuário:** `admin`
* **Senha:** `admin`

### Onde olhar cada pilar no Grafana:

1. **Dashboard Provisionado (Visão Unificada RED + Logs):**
   * Menu lateral **Dashboards → Projeto Final - Observabilidade → Projeto Final - Observabilidade RED & Logs**.
2. **Métricas (Prometheus):**
   * Menu **Explorar** → Selecione o datasource **Prometheus**.
   * Taxa de requisições por serviço/rota: `sum by (service, path) (rate(http_requests_total[1m]))`
   * Latência p95 por serviço: `histogram_quantile(0.95, sum by (le, service) (rate(http_request_duration_seconds_bucket[1m])))`
3. **Logs (Loki) e Navegação para Traces:**
   * Menu **Explorar** → Selecione o datasource **Loki**.
   * Query: `{service=~"loja-api|pagamento-service"} | json`
   * Expanda qualquer linha de log e clique no botão azul **Tempo** no campo derivado `TraceID` para saltar diretamente para o trace daquela requisição.
4. **Traces Distribuídos (Tempo) e Navegação para Logs:**
   * Menu **Explorar** → Selecione o datasource **Tempo** → Aba **Search** → Clique em **Run query**.
   * Abra um trace da `loja-api` (rota `POST /checkout`) para visualizar a árvore de spans atravessando `loja-api` → `reservar_estoque` → `chamar_pagamento_service` → `pagamento-service` (`POST /pagar` → `analise_antifraude`).
   * Clique em **Logs for this span** dentro de qualquer span para visualizar os logs filtrados pelo `trace_id`.

---

## 4. Documentação e Evidências

* **Arquitetura e Decisões de Instrumentação:** [`docs/arquitetura-e-decisoes.md`](docs/arquitetura-e-decisoes.md)
* **Evidências de Execução (Screenshots):** Pasta [`evidencias/`](evidencias/)

<!-- RESUMO FINAL (Fim): Instruções claras e reproduzíveis para execução, validação dos três
     pilares e navegação entre sinais no Grafana. -->
