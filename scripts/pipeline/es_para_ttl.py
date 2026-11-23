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
from rdflib import Literal, Namespace
from rdflib.namespace import XSD
from rdflib.namespace import FOAF, OWL, RDFS

SAIDA = Path("resultados/pipeline/final/grafo_framework.ttl")

print("Lendo o grafo do Elasticsearch...")
g = es_to_rdflib_graph(index=config.ELASTIC_SEARCH_INDEX)
print(f"{len(g)} triplas")

# 1) Números inteiros escritos como 2000, e não como 2e+03.
#    (o framework guarda o ano como decimal; o valor é o mesmo, só muda a escrita)
for s, p, o in list(g):
    if isinstance(o, Literal) and o.datatype in (XSD.decimal, XSD.double, XSD.float):
        try:
            valor = float(o)
        except (TypeError, ValueError):
            continue
        if valor == int(valor):
            g.remove((s, p, o))
            g.add((s, p, Literal(int(valor))))

# 2) Prefixos com nome legível (o rdflib inventaria ns1, ns2, ns3...).
#    Não mudam o conteúdo, só a leitura. replace=True troca os nomes automáticos.
PREFIXOS = {
    "foaf": FOAF, "owl": OWL, "rdfs": RDFS,
    "skos": Namespace("http://www.w3.org/2004/02/skos/core#"),
    "schema": Namespace("https://schema.org/"),
    "hc": Namespace("http://www.heritageconnector.org/RDF/"),
    "wd": Namespace("http://www.wikidata.org/entity/"),
    "wdt": Namespace("http://www.wikidata.org/prop/direct/"),
    "facom": Namespace("http://example.org/facom/"),
}
for nome, ns in PREFIXOS.items():
    g.bind(nome, ns, override=True, replace=True)

SAIDA.parent.mkdir(parents=True, exist_ok=True)
dados = g.serialize(format="turtle")
if isinstance(dados, bytes):  # rdflib 5 devolve bytes
    dados = dados.decode("utf-8")
SAIDA.write_text(dados, encoding="utf-8")
print("Salvo em", SAIDA)
