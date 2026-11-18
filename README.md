<!-- OBJETIVO (Início): Apresentar a estrutura geral do repositório da disciplina
     Fundamentos de Observabilidade: Métricas, Logs e Traces (Prof. Mateus Valgueiro). -->

# Fundamentos de Observabilidade: Métricas, Logs e Traces

Repositório contendo as entregas avaliativas da disciplina:

1. **[`atividade-4-misterio-checkout/`](atividade-4-misterio-checkout/)** — **Prática 4 (25% da nota):** Investigação do incidente de saturação do pool de conexões no `/checkout` usando Métricas (RED/USE) e Logs (Loki), relatório técnico para exportação em PDF (`RELATORIO_PRATICA_4.md`) e `compose.yaml` corrigido.
2. **[`projeto-final/`](projeto-final/)** — **Projeto Final (75% da nota):** Arquitetura distribuída com dois microsserviços (`loja-api` e `pagamento-service`) instrumentados com OpenTelemetry (Traces + Context Propagation W3C), Prometheus (Métricas RED/Gauge) e Grafana Alloy + Loki (Logs JSON estruturados), orquestrados em um único `compose.yaml`.

## Início Rápido

```bash
# Subir toda a stack do Projeto Final (8 containers)
cd projeto-final
docker compose up -d --build
docker compose ps
```

* **Grafana:** `http://localhost:3000` (usuário `admin` / senha `admin`)
* **Prometheus:** `http://localhost:9090`
* **Grafana Alloy UI:** `http://localhost:12345`

<!-- RESUMO FINAL (Fim): Índice principal do repositório para navegação rápida e execução imediata. -->
