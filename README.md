git clone https://github.com/dhuberto/observabilidade.git
cd observabilidade

docker compose up -d      # sobe em background
docker compose ps         # lista os serviços
docker compose logs -f grafana   # acompanha os logs do Grafana
docker compose down       # derruba (mantém o volume)
docker compose down -v    # derruba e apaga o volume
