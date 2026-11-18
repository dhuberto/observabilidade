<!-- OBJETIVO (Início): Relatório técnico avaliativo da Prática 4 (O Mistério do Checkout),
     documentando passo a passo a investigação do incidente, hipóteses descartadas, correção e validação. -->

# Relatório de Investigação de Incidente — Prática 4: O Mistério do Checkout

**Disciplina:** Fundamentos de Observabilidade: Métricas, Logs e Traces  
**Professor:** Mateus Valgueiro  
**Aluno(a) / Grupo:** Danilo Humberto (`github.com/dhuberto/observabilidade`)  

---

## 1. Contexto e Reprodução do Chamado

* **Chamado (14:07):** Clientes relatam falhas (HTTP 500) e lentidão ao tentar finalizar compras na rota `/checkout`, embora o time de desenvolvimento afirme não ter alterado o código do checkout.
* **Ambiente:** Stack composta por `loja`, `trafego` (8 clientes concorrentes), `prometheus`, `loki`, `alloy` e `grafana`.
* **Validação inicial via terminal:**
  ```bash
  for i in 1 2 3 4 5; do curl -s -o /dev/null -w "%{http_code} %{time_total}s\n" localhost:8080/checkout; done
  ```
  Observou-se retorno frequente de status `500` com tempo próximo a `2.00s` (indicativo de timeout).

---

## 2. Investigação por Métricas (Método RED — Sintoma e Impacto)

No Grafana (**Explorar → Prometheus**), aplicamos as três dimensões do método RED segmentadas por rota (`path`):

1. **Rate (Taxa de requisições por segundo por rota):**
   ```promql
   sum by (path) (rate(http_requests_total[1m]))
   ```
2. **Errors (Taxa de erro HTTP 5xx por rota):**
   ```promql
   sum by (path) (rate(http_requests_total{status=~"5.."}[1m])) / sum by (path) (rate(http_requests_total[1m]))
   ```
   * **Achado:** As rotas `/` e `/produtos` apresentaram **0% de erro**. Exclusivamente a rota `/checkout` apresentou alta taxa de erro `500`.
3. **Duration (Latência p95 por rota):**
   ```promql
   histogram_quantile(0.95, sum by (le, path) (rate(http_request_duration_seconds_bucket[1m])))
   ```
   * **Achado:** `/` (~25ms) e `/produtos` (~90ms) operavam dentro do esperado, enquanto `/checkout` atingiu p95 próximo de **2.0s** (teto do timeout).

> **[INSERIR SCREENSHOT 1: Gráficos PromQL de Taxa de Erro e Latência p95 por rota mostrando o problema isolado no `/checkout`]**

---

## 3. Investigação por Logs (Loki) e Descarte de Caminhos Errados

No Grafana (**Explorar → Loki**), consultamos todos os logs de erro emitidos pela aplicação:

```logql
{service="loja"} | json | level="ERROR"
```

Encontramos **três categorias distintas** de `ERROR`:

1. **Erro no Job de Newsletter (Descartado):**
   * *Análise:* Logs sem campo `path`, originados por uma rotina assíncrona em segundo plano. Não há cliente aguardando resposta HTTP e não impacta o RED.
2. **Erro no Serviço de Recomendações na rota `/produtos` (Descartado):**
   * *Análise:* Apesar de gerar logs `ERROR` com alto volume, a métrica RED da rota `/produtos` provou que **0% dos clientes receberam erro** (a aplicação aplica fallback para uma lista padrão e responde HTTP 200). Investigar isso seria um falso positivo.
3. **Erro de Timeout ao obter conexão do Pool de Banco de Dados no `/checkout` (Causa Confirmada):**
   * *Análise:* Mensagens explícitas de falha por esgotamento do tempo de espera (`DB_POOL_TIMEOUT`) ao tentar obter conexão livre para gravar o pedido.

> **[INSERIR SCREENSHOT 2: Consulta LogQL `{service="loja"} | json | level="ERROR"` evidenciando os três tipos de erro e o detalhe da mensagem do checkout]**

---

## 4. Correlação Métrica + Log e Diagnóstico de Saturação (Método USE)

Para confirmar a saturação do recurso de banco de dados, consultamos a métrica Gauge de conexões ativas no Prometheus:

```promql
db_conexoes_em_uso
```

* O gráfico mostrava uma linha reta constante no valor **`2`**.
* Cruzando com os logs de startup (`{service="loja"} |= "pool"`) e com o arquivo `compose.yaml`, confirmamos que **`DB_POOL_SIZE=2`**.
* **Conclusão Técnica (Causa Raiz):** Com apenas 2 conexões disponíveis e cada transação de checkout levando entre `0.5s` e `1.5s`, sob carga de **8 clientes simultâneos**, o pool atingiu **100% de utilização e saturação constante**, formando fila até estourar o timeout padrão de `2s` e devolver HTTP `500`.

> **[INSERIR SCREENSHOT 3: Gráfico do `db_conexoes_em_uso` travado em 2 antes da correção]**

---

## 5. Correção Aplicada e Prova de Resolução

Editamos o `compose.yaml` aumentando a capacidade do pool de conexões para suportar a concorrência dos 8 clientes:

```yaml
    environment:
      - DB_POOL_SIZE=20
      - DB_POOL_TIMEOUT=5
```

Aplicamos a alteração sem derrubar o restante da stack:
```bash
docker compose up -d loja
```

### Validação Pós-Correção (Após 2 minutos)

1. **Taxa de erro do `/checkout`:** Caiu para **0%** (`0` respostas HTTP 500).
2. **Latência p95 do `/checkout`:** Caiu de `~2.0s` para a faixa normal de operação (`~1.2s - 1.4s`).
3. **Utilização do Pool (`db_conexoes_em_uso`):** Deixou de ficar colado no teto, oscilando dinamicamente sem esgotamento.
4. **Logs no Loki:** Os erros de timeout de pool no `/checkout` desapareceram completamente.

> **[INSERIR SCREENSHOT 4: Painel/Explore comprovando taxa de erro 0% no `/checkout`, queda da latência p95 e oscilação saudável de `db_conexoes_em_uso`]**

<!-- RESUMO FINAL (Fim): Relatório estruturado segundo os critérios avaliativos da Aula 3/4,
     cobrindo diagnóstico RED/USE, descarte de pistas falsas, correção de infraestrutura e evidências. -->
