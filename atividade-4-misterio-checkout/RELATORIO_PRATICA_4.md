# Relatório de Investigação de Incidente: O Mistério do Checkout

---

## 1. O chamado

> *Suporte, 14:07: "Desde o deploy de hoje, vários clientes dizem que não conseguem finalizar a compra. Outros dizem que o site está lento. O time de desenvolvimento jura que não mudou nada no checkout."*

Regras: o código da loja não está disponível; só temos o `compose.yaml`, as métricas (Prometheus) e os logs (Loki), vistos pelo Grafana (Explorar).

**Ambiente:** `loja` (imagem `mvalgueiroschool/pratica-misterio-app:1.0.0`), `trafego` (8 clientes em paralelo), `prometheus`, `loki`, `alloy` e `grafana`, subidos com `docker compose up -d`. O `compose.yaml` do chamado define só `DB_POOL_SIZE=2` e **não** define `DB_POOL_TIMEOUT` (vale o padrão de 2 s, segundo o enunciado).

## 2. Passo 1 — Reproduzir o problema

Cinco compras seguidas com `curl` na rota `/checkout`:

```bash
for i in 1 2 3 4 5; do curl -s -o /dev/null -w "%{http_code} %{time_total}s\n" localhost:8080/checkout; done
```

![curl antes da correção](p4-01-reproducao-curl.png)

| # | Status | Tempo |
|---|--------|-------|
| 1 | 200 | 3,31 s |
| 2 | **500** | 2,00 s |
| 3 | 200 | 2,58 s |
| 4 | **500** | 2,01 s |
| 5 | **500** | 2,01 s |

**Leitura:** 3 de 5 compras falharam com HTTP 500, todas em cerca de 2,00 s. As duas que passaram também demoraram muito mais que o normal (0,5 a 1,5 s). O problema é real e tem os dois sintomas do chamado: erro e lentidão.

## 3. Passo 2 — Métricas (RED por rota): onde dói?

Aguardamos alguns minutos para acumular histórico e consultamos o Prometheus em Explorar.

**Rate** — `sum by (path) (rate(http_requests_total[1m]))`

![Rate por rota](p4-02-rate-por-rota.png)

As três rotas (`/`, `/produtos`, `/checkout`) tinham taxa parecida, de cerca de 2 a 3 req/s. **O Rate sozinho não denuncia o problema.**

**Errors** — `sum by (path) (rate(http_requests_total{status=~"5.."}[1m])) / sum by (path) (rate(http_requests_total[1m]))`

![Taxa de erro por rota](p4-03-erros-por-rota.png)

Só a série `/checkout` aparece, com taxa de erro entre cerca de 26% e 34% (valor de 0,2727 na tabela *Raw* no momento do print). `/` e `/produtos` **não aparecem**: não têm nenhuma resposta 5xx, ou seja, 0% de erro.

**Duration (p95)** — `histogram_quantile(0.95, sum by (le, path) (rate(http_request_duration_seconds_bucket[1m])))`

O gráfico do p95 por rota está no print `p4-12` (Seção 7), que cobre o período antes e depois da correção. Antes da correção, o p95 do `/checkout` ficou em torno de 4,2 a 4,5 s (normal: 0,5 a 1,5 s), enquanto `/` e `/produtos` ficaram em valores baixos (`/produtos` na casa de 0,2 s, `/` abaixo disso).

**Conclusão do passo 2:** o problema está isolado no `/checkout`: cerca de 1 em cada 3 requisições falha e o p95 está muito acima do normal. As outras rotas não têm erro. Isso diz **onde** dói, mas ainda não **por quê**.

## 4. Passo 3 — Logs (Loki): o que a loja está dizendo?

```logql
{service="loja"} | json | level="ERROR"
```

![Logs ERROR](p4-05-logs-error.png)

Há muitos logs `ERROR` (mais de mil na janela observada). Para não olhar linha a linha, contamos por tipo de mensagem:

```logql
sum by (message) (count_over_time({service="loja"} | json | level="ERROR" [15m]))
```

![Tipos de erro](p4-06-tipos-de-erro.png)

Aparecem **três tipos** de ERROR:

| Mensagem | Volume relativo | Afeta o cliente? | Decisão |
|----------|-----------------|------------------|---------|
| `falha ao buscar recomendações` | o mais frequente | **Não** | Descartado |
| `timeout ao obter conexão do pool do banco` | o segundo | **Sim** | **Causa investigada** |
| `falha ao enviar newsletter` | o menor | Não | Descartado |

**Pistas descartadas (e por quê):**

1. **`falha ao buscar recomendações` (o erro que mais aparece).** Os logs vêm da rota `/produtos` e trazem `"erro": "timeout de 50ms no serviço de recomendações"` e `"acao": "usando lista padrão"`: a loja usa um *fallback* e responde normalmente. A métrica confirma: `/produtos` tem **0% de erro HTTP** (Seção 3). Um log `ERROR` não significa que o cliente sentiu o problema; quem diz isso é a métrica. Investigar este erro seria um falso positivo.
2. **`falha ao enviar newsletter`.** É um job em segundo plano, sem `path` e sem cliente esperando resposta. Não entra no RED. Descartado.

<!-- Se o grupo testou outras hipóteses (ex.: investigou a rota /produtos mais a fundo, mexeu em algo e voltou atrás), registre aqui com o que observou. Não preencher com tentativas que não aconteceram. -->

**O erro restante** é o `timeout ao obter conexão do pool do banco`. Detalhe do log:

```logql
{service="loja"} | json | message="timeout ao obter conexão do pool do banco"
```

![Erro do pool](p4-07-erro-pool.png)

Campos do log do `/checkout`: `"pool_size": 2`, `"espera_s": 2.0`, `"status": 500`, `"duration_ms": ≈2001`. O pool tem **2 conexões**; o pedido esperou **2 s** por uma conexão livre e desistiu, devolvendo **500** ao cliente. Todas as linhas desse erro têm `path=/checkout`.

## 5. Passo 4 — Juntando as pistas (USE): saturação do pool

O log informa o tamanho do pool (2), mas a loja não expõe o máximo como métrica. Falta ver quantas conexões estão **em uso**:

```promql
db_conexoes_em_uso
```

![Conexões em uso antes da correção](p4-08-db-conexoes-em-uso.png)

A linha fica **reta em 2** o tempo todo: o pool está 100% ocupado (2 de 2).

**Causa raiz:** cada `/checkout` segura uma conexão por 0,5 a 1,5 s para gravar o pedido. Com 8 clientes simultâneos e só 2 conexões, os pedidos entram em fila. Quem espera mais que o `DB_POOL_TIMEOUT` (2 s, padrão) desiste e recebe 500. É **saturação** (o "S" do método USE): a lentidão aparece primeiro como fila e depois vira erro.

Conferindo o `compose.yaml` da loja, a configuração bate com o achado: `DB_POOL_SIZE=2` e nenhuma definição de `DB_POOL_TIMEOUT`.

## 6. Passo 5 — Correção

Alteração no serviço `loja` do `compose.yaml`:

```yaml
    environment:
      - DB_POOL_SIZE=20
      - DB_POOL_TIMEOUT=5
```

Aplicada recriando somente a loja (horário aproximado: 22:22):

```bash
docker compose up -d loja
```

Conferência de que o container já usa os valores novos (saída obtida no terminal do grupo):

```
$ docker exec loja env | grep DB_POOL
DB_POOL_SIZE=20
DB_POOL_TIMEOUT=5
```

![Correção aplicada: compose.yaml e variáveis dentro do container](p4-09-correcao-aplicada.png)

## 7. Prova de que a correção funcionou

Esperamos alguns minutos e repetimos as consultas.

**a) `curl` do checkout (os mesmos 5 pedidos)**

![curl depois da correção](p4-10-curl-depois.png)

| | Antes (pool = 2) | Depois (pool = 20) |
|---|---|---|
| Status | 3 × 500 e 2 × 200 | **5 × 200** |
| Tempos | 2,00 s a 3,31 s | **0,56 s a 1,49 s** |

**b) Taxa de erro do `/checkout`**

![Erros depois da correção](p4-11-erros-depois.png)

A taxa, que vinha em torno de 25 a 34%, despenca por volta de 22:22 e a série termina: não há mais respostas 5xx (sem erro, a série deixa de existir).

**c) Latência p95 por rota**

![p95 depois da correção](p4-12-p95-depois.png)

O p95 do `/checkout` cai de cerca de 4,3 s para cerca de 1,45 s e se estabiliza, dentro da faixa normal do enunciado (0,5 a 1,5 s, perto do teto, o que é coerente com um p95). `/` e `/produtos` não mudam.

**d) Conexões em uso**

![Conexões em uso depois da correção](p4-13-conexoes-depois.png)

Antes da correção, reta em 2; depois, passa a oscilar entre cerca de 3 e 8 (o pico acompanha os 8 clientes simultâneos). Com um pool de 20, sobra folga e ninguém mais espera por conexão.

**e) Taxa de requisições**

![Rate depois da correção](p4-14-rate-depois.png)

A taxa **subiu** em todas as rotas por volta de 22:22 (o `/checkout` foi de cerca de 2,8 para cerca de 5,7 req/s). Explicação: cada cliente do tráfego só faz a próxima requisição depois que a anterior termina. Antes, ficavam presos até 2 s esperando conexão; com o pool destravado terminam mais rápido e voltam a navegar. O pool pequeno não só gerava erros: **limitava a vazão da loja inteira**.

**f) Logs**

No Loki (janela de 1 hora), os erros `timeout ao obter conexão do pool do banco` aparecem de cerca de 22:03 até 22:22 (946 registros, todos com `path=/checkout`, `pool_size: 2` e `espera_s: 2.0`). O último registro é de **22:22:11** e não há nenhum depois disso até o fim da janela, momento da correção. Os outros ERROR (recomendações e newsletter) **continuam**, como esperado: eram outro assunto e não afetavam o cliente.

![Erros do pool no Loki, janela de 1 hora](p4-15-logs-depois.png)
**g) Estado final dos serviços**

![docker compose ps](p4-16-compose-ps.png)

Todos os serviços (`alloy`, `grafana`, `loja`, `loki`, `prometheus` e `trafego`) estão `Up`. A `loja` aparece com cerca de 28 minutos de vida, contra cerca de 47 dos demais: foi a única recriada pela correção (`docker compose up -d loja`).

## 8. Resumo do incidente

| | Antes (pool = 2) | Depois (pool = 20) |
|---|---|---|
| `curl` do `/checkout` | 3 × 500; 2,0 a 3,3 s | 5 × 200; 0,56 a 1,49 s |
| Erro no `/checkout` | ~25 a 34% | sem novos 5xx |
| p95 do `/checkout` | ~4,3 s | ~1,45 s |
| `db_conexoes_em_uso` | fixo em 2 | oscila de ~3 a ~8 |
| Taxa do `/checkout` | ~2,8 req/s | ~5,7 req/s |
| ERROR do pool no Loki | presente | sem novos registros |

Valores lidos dos gráficos dos prints; são aproximados.

**Causa raiz:** pool de conexões com o banco subdimensionado (`DB_POOL_SIZE=2`) para 8 clientes simultâneos, com timeout de espera de 2 s: saturação que gerou fila, lentidão e depois erros 500 no `/checkout`.

**Aprendizados**
- Métricas dizem **onde e quando**; logs dizem **por quê**. A investigação usou os dois.
- O erro que mais aparece no log (recomendações) não era o que importava: quem diz o impacto no cliente é o RED.
- "2 conexões em uso" só virou problema porque sabíamos que o máximo era 2. Vale expor o tamanho do pool também como métrica.
- A saturação apareceu primeiro como latência (fila) e só depois como erro (timeout).
- Corrigir não termina o incidente: é preciso **provar** com as métricas.
