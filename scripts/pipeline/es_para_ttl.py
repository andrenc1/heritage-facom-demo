"""
Exporta o grafo do Framework (Elasticsearch) para um arquivo Turtle.

Este é o RDF "feito pelo Heritage Connector": o framework carregou os dados do
museu no Elasticsearch (facom_loader.py), trouxe as propriedades do Wikidata
(buscar_propriedades.py) e este script converte tudo para RDF com a mesma
função que o framework usa para alimentar o Fuseki (es_to_rdflib_graph).

Uso, de dentro do container (pasta /work), DEPOIS do facom_loader.py e,
se quiser as propriedades do Wikidata, do buscar_propriedades.py:
  python scripts/pipeline/es_para_ttl.py

Gera: resultados/pipeline/final/grafo_framework.ttl
"""
from pathlib import Path

from heritageconnector.config import config
from heritageconnector.datastore import es_to_rdflib_graph
from rdflib import Namespace
from rdflib.namespace import FOAF, OWL, RDFS

SAIDA = Path("resultados/pipeline/final/grafo_framework.ttl")

print("Lendo o grafo do Elasticsearch...")
g = es_to_rdflib_graph(index=config.ELASTIC_SEARCH_INDEX)
print(f"{len(g)} triplas")

# Prefixos legíveis no arquivo (não mudam o conteúdo)
g.bind("foaf", FOAF)
g.bind("owl", OWL)
g.bind("rdfs", RDFS)
g.bind("wd", Namespace("http://www.wikidata.org/entity/"))
g.bind("wdt", Namespace("http://www.wikidata.org/prop/direct/"))
g.bind("facom", Namespace("http://example.org/facom/"))

SAIDA.parent.mkdir(parents=True, exist_ok=True)
dados = g.serialize(format="turtle")
if isinstance(dados, bytes):  # rdflib 5 devolve bytes
    dados = dados.decode("utf-8")
SAIDA.write_text(dados, encoding="utf-8")
print("Salvo em", SAIDA)
