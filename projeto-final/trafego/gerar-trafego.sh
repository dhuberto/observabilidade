#!/bin/sh
# OBJETIVO (Início): Gerar tráfego HTTP contínuo contra a loja-api (/, /produtos, /checkout e /erro)
# assim que o docker compose subir, garantindo dados imediatos em métricas, logs e traces.

APP=${APP:-http://loja-api:8080}

sorteio() {
  echo $(( $(od -An -N1 -tu1 /dev/urandom) % 100 ))
}

sleep 3

while true; do
  n=$(sorteio)

  if [ "$n" -lt 45 ]; then
    curl -s -X POST -o /dev/null "$APP/checkout"
  elif [ "$n" -lt 75 ]; then
    curl -s -o /dev/null "$APP/produtos"
  elif [ "$n" -lt 95 ]; then
    curl -s -o /dev/null "$APP/"
  else
    curl -s -o /dev/null "$APP/erro"
  fi

  sleep 0.4
done

# RESUMO FINAL (Fim): Automatiza a geração de carga sem intervenção manual.
