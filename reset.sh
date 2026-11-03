#!/usr/bin/env bash
# Desliga tudo e APAGA os dados guardados (Elasticsearch e Fuseki) deste projeto.
# Serve para começar do zero. Os arquivos da pasta (scripts e CSVs) não são mexidos.
cd "$(dirname "$0")"
read -r -p "Apagar os dados do Elasticsearch e do Fuseki deste projeto? (s/N) " resp
if [ "$resp" = "s" ] || [ "$resp" = "S" ]; then
  docker compose down -v
  echo "Feito. Veja o README para refazer tudo."
else
  echo "Nada foi apagado."
fi
