"""
Copia o grafo do Elasticsearch para o Fuseki e roda consultas SPARQL.

Segue a ideia do smg_jobs/es_to_csv.py (que converte o índice em triplas),
mas sem as partes do museu SMG (vários índices, cache do Wikidata etc.).

Uso, de dentro do container (pasta /app), DEPOIS do facom_loader.py e do
buscar_propriedades.py:
  python scripts/es_para_fuseki.py

Pode rodar quantas vezes quiser: ele SUBSTITUI o conteúdo do Fuseki
(não duplica).
"""
import requests

from heritageconnector.config import config
from heritageconnector.datastore import es_to_rdflib_graph

# Fuseki dentro do Docker. O endereço do config termina em /sparql;
# a carga usa o endereço /data do mesmo dataset.
SPARQL = getattr(config, "FUSEKI_ENDPOINT",
                 "http://fuseki:3030/heritage-connector/sparql")
BASE = SPARQL.rsplit("/", 1)[0]
DATA = BASE + "/data"
AUTH = ("admin", "admin")  # o ADMIN_PASSWORD do docker-compose.yml

PREFIXOS = """
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX owl:  <http://www.w3.org/2002/07/owl#>
PREFIX foaf: <http://xmlns.com/foaf/0.1/>
PREFIX wd:   <http://www.wikidata.org/entity/>
PREFIX wdt:  <http://www.wikidata.org/prop/direct/>
"""

CONSULTAS = {
    "1) Quantas triplas existem no total":
        "SELECT (COUNT(*) AS ?triplas) WHERE { ?s ?p ?o }",

    "2) Objetos e o fabricante de cada um":
        """SELECT ?objeto ?fabricante WHERE {
             ?o foaf:maker ?f .
             ?o rdfs:label ?objeto .
             ?f rdfs:label ?fabricante .
           } ORDER BY ?fabricante""",

    # Q30 = Estados Unidos no Wikidata. A ligação passa por 3 passos:
    # objeto -> fabricante -> (país gravado pelo buscar_propriedades.py)
    "3) Objetos feitos por empresas dos Estados Unidos (Q30)":
        """SELECT ?objeto ?fabricante WHERE {
             ?o foaf:maker ?f .
             ?f wdt:P17 wd:Q30 .
             ?o rdfs:label ?objeto .
             ?f rdfs:label ?fabricante .
           } ORDER BY ?fabricante""",

    "4) Quantos objetos por país do fabricante (código do Wikidata)":
        """SELECT ?pais (COUNT(?o) AS ?objetos) WHERE {
             ?o foaf:maker ?f .
             ?f wdt:P17 ?pais .
           } GROUP BY ?pais ORDER BY DESC(?objetos)""",

    "5) Fabricantes ligados ao Wikidata (sameAs)":
        """SELECT ?fabricante ?wikidata WHERE {
             ?f owl:sameAs ?wikidata .
             ?f rdfs:label ?fabricante .
           } ORDER BY ?fabricante""",
}


def carregar():
    print("Lendo o grafo do Elasticsearch...")
    g = es_to_rdflib_graph(index=config.ELASTIC_SEARCH_INDEX)
    print(f"{len(g)} triplas")
    dados = g.serialize(format="nt")
    if isinstance(dados, str):  # rdflib >= 6 devolve texto
        dados = dados.encode("utf-8")
    # PUT = substitui o grafo padrão (não duplica ao repetir)
    resp = requests.put(
        DATA,
        params={"default": ""},
        data=dados,
        headers={"Content-Type": "application/n-triples"},
        auth=AUTH,
        timeout=60,
    )
    resp.raise_for_status()
    print(f"Enviado ao Fuseki ({resp.status_code}): {DATA}\n")


def consultar(sparql):
    resp = requests.post(
        SPARQL,
        data={"query": PREFIXOS + sparql},
        headers={"Accept": "application/sparql-results+json"},
        timeout=60,
    )
    resp.raise_for_status()
    j = resp.json()
    colunas = j["head"]["vars"]
    linhas = [[b.get(c, {}).get("value", "") for c in colunas]
              for b in j["results"]["bindings"]]
    return colunas, linhas


def main():
    carregar()
    for titulo, q in CONSULTAS.items():
        print(f"=== {titulo}")
        colunas, linhas = consultar(q)
        print("   " + " | ".join(colunas))
        for l in linhas:
            print("   " + " | ".join(v.replace("http://www.wikidata.org/entity/", "wd:")
                                       .replace("http://example.org/facom/", "")
                                       for v in l))
        print(f"   ({len(linhas)} linhas)\n")


if __name__ == "__main__":
    main()
