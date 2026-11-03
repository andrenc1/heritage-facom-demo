"""
Loader do Heritage Connector para as tabelas limpas do Museu FACOM.

Baseado no smg_jobs/smg_loader.py, mas SEM as partes específicas do SMG
(leituras em s3://, Mimsy/Adlib, dados privados).

Entrada (tabelas já limpas, preparadas à parte a partir do CSV do Tainacan), na pasta data/:
  objects.csv, organisations.csv, object_maker.csv

Uso, de dentro do container (pasta /app):
  python scripts/facom_loader.py

ATENÇÃO: datastore.create_index() APAGA o índice ELASTIC_SEARCH_INDEX do
config.ini e o recria vazio. Use um índice só de teste.
"""
from pathlib import Path

import pandas as pd

from heritageconnector import datastore, logging
from heritageconnector.config import config, field_mapping
from heritageconnector.namespace import FOAF, OWL, WD, WDT
from heritageconnector.utils.wikidata import qid_to_url
from heritageconnector.utils.data_transformation import get_year_from_date_value

logger = logging.get_logger(__name__)

# Prefixo PROVISÓRIO para criar as URIs dos registros (cada registro precisa
# de uma URI única). Troque por um endereço seu se tiver um.
PREFIX = "http://example.org/facom/"

# Nomes da coluna "Autoria" que são PESSOAS (e não empresas). Eles vão para a
# tabela PERSON, com tipo "humano" (Q5), e não para ORGANISATION.
# Se encontrar outras pessoas na sua lista de fabricantes, adicione aqui.
PESSOAS = {"Douglas Engelbart"}

record_loader = datastore.RecordLoader(
    collection_name="FACOM", field_mapping=field_mapping
)


def vazio_se_nan(valor):
    """O RecordLoader ignora '', None e 'nan'; garantimos texto limpo."""
    return "" if pd.isna(valor) else str(valor)


def load_objects(path):
    df = pd.read_csv(path)
    df["URI"] = PREFIX + df["id"].astype(str)

    # Colunas que o field_mapping (tabela "OBJECT") exige. Se alguma
    # faltar, o loader dá KeyError: "column X not in data for table OBJECT".
    df["TITLE"] = df["label"].map(vazio_se_nan)
    df["DESCRIPTION"] = df["description"].map(vazio_se_nan)
    # Usada como contexto na etapa de NER. Aqui, igual à descrição.
    df["DISAMBIGUATING_DESCRIPTION"] = df["DESCRIPTION"]
    df["ITEM_NAME"] = df["term"].map(
        lambda t: [] if pd.isna(t) else [str(t).strip().lower()]
    )
    df["MATERIALS"] = [[] for _ in range(len(df))]  # não temos essa coluna
    df["DATE_MADE"] = df["date_attributed"].apply(get_year_from_date_value)
    df["CATEGORY1"] = df["category"].map(vazio_se_nan)
    df["DATABASE"] = "tainacan"

    logger.info("loading object data")
    record_loader.add_records("OBJECT", df)


def load_organisations(path):
    df = pd.read_csv(path)
    df = df[~df["label"].isin(PESSOAS)].copy()
    df["URI"] = PREFIX + df["id"].astype(str)

    # Colunas exigidas pela tabela "ORGANISATION" do field_mapping.
    df["PREFERRED_NAME"] = df["label"].map(vazio_se_nan)
    df["BIOGRAPHY"] = ""
    df["DISAMBIGUATING_DESCRIPTION"] = df["PREFERRED_NAME"]
    df["OCCUPATION"] = [[] for _ in range(len(df))]
    df["NATIONALITY"] = [[] for _ in range(len(df))]
    df["BIRTH_DATE"] = None
    df["DEATH_DATE"] = None
    df["DATABASE"] = "tainacan"

    logger.info("loading organisation data")
    # Q43229 = "organização" no Wikidata (mesmo valor usado no smg_loader.py)
    record_loader.add_records("ORGANISATION", df, add_type=WD.Q43229)


def load_people(path):
    df = pd.read_csv(path)
    df = df[df["label"].isin(PESSOAS)].copy()
    if df.empty:
        return
    df["URI"] = PREFIX + df["id"].astype(str)

    # Colunas exigidas pela tabela "PERSON" do field_mapping.
    df["PREFERRED_NAME"] = df["label"].map(vazio_se_nan)
    for col in ["TITLE_NAME", "FIRSTMID_NAME", "LASTSUFF_NAME", "GENDER",
                "BIRTH_PLACE", "DEATH_PLACE", "BIOGRAPHY"]:
        df[col] = ""
    df["DISAMBIGUATING_DESCRIPTION"] = df["PREFERRED_NAME"]
    df["OCCUPATION"] = [[] for _ in range(len(df))]
    df["NATIONALITY"] = [[] for _ in range(len(df))]
    df["BIRTH_DATE"] = None
    df["DEATH_DATE"] = None
    df["DATABASE"] = "tainacan"

    logger.info("loading people data")
    # Q5 = "humano" no Wikidata
    record_loader.add_records("PERSON", df, add_type=WD.Q5)


def load_makers(path, organisations_path):
    """objeto -> fabricante. Segue a convenção do SMG (pessoas x organizações)."""
    df = pd.read_csv(path)
    orgs = pd.read_csv(organisations_path)
    ids_pessoas = set(orgs.loc[orgs["label"].isin(PESSOAS), "id"])

    df["OBJECT_ID"] = PREFIX + df["object_id"].astype(str)
    df["MAKER_ID"] = PREFIX + df["org_id"].astype(str)
    de_pessoas = df[df["org_id"].isin(ids_pessoas)]
    de_orgs = df[~df["org_id"].isin(ids_pessoas)]

    logger.info("loading maker data")
    # objeto foi feito por (pessoa ou organização)
    record_loader.add_triples(
        df, FOAF.maker, subject_col="OBJECT_ID", object_col="MAKER_ID"
    )
    # pessoa fez objeto
    if len(de_pessoas):
        record_loader.add_triples(
            de_pessoas, FOAF.made, subject_col="MAKER_ID", object_col="OBJECT_ID"
        )
    # organização produziu objeto (P1056 = "product or material produced")
    if len(de_orgs):
        record_loader.add_triples(
            de_orgs, WDT.P1056, subject_col="MAKER_ID", object_col="OBJECT_ID"
        )


def load_sameas(path):
    """
    Grava links owl:sameAs entre registros seus e itens do Wikidata.

    O CSV precisa ter as colunas:  internal_id, wikidata_id
      internal_id = o id do seu CSV (ex.: org-olivetti)
      wikidata_id = o QID escolhido por você (ex.: Q123). Linhas com
                    wikidata_id vazio são ignoradas.
    Segue a mesma lógica de load_sameas_from_disambiguator() do smg_loader.py.
    """
    df = pd.read_csv(path)
    df = df.dropna(subset=["wikidata_id"])
    df = df[df["wikidata_id"].astype(str).str.strip() != ""].copy()
    if df.empty:
        logger.info("sameas.csv sem QIDs preenchidos; nada a carregar")
        return

    df["INTERNAL_URI"] = PREFIX + df["internal_id"].astype(str)
    df["wikidata_url"] = df["wikidata_id"].astype(str).str.strip().apply(qid_to_url)

    logger.info("loading sameAs links")
    record_loader.add_triples(
        df, OWL.sameAs, subject_col="INTERNAL_URI", object_col="wikidata_url"
    )


def verificar():
    """add_records/add_triples NÃO avisam se algo falhou. Confira as contagens."""
    es = datastore.es
    es.indices.refresh(index=config.ELASTIC_SEARCH_INDEX)
    total = es.count(index=config.ELASTIC_SEARCH_INDEX)["count"]
    print(f"Documentos no índice {config.ELASTIC_SEARCH_INDEX}: {total}")

    res = es.search(
        index=config.ELASTIC_SEARCH_INDEX,
        body={"query": {"match_all": {}}, "size": 1000},
    )
    com_sameas = []
    for hit in res["hits"]["hits"]:
        grafo = hit["_source"].get("graph", {})
        if "@owl:sameAs" in grafo:
            com_sameas.append((hit["_id"], grafo["@owl:sameAs"]))

    print(f"Documentos com owl:sameAs: {len(com_sameas)} (esperado: 9)")
    for uri, alvo in com_sameas:
        print("  ", uri, "->", alvo)
    return total


if __name__ == "__main__":
    # apaga e recria o índice (só para testes!)
    datastore.create_index(config.ELASTIC_SEARCH_INDEX)

    load_objects("data/objects.csv")
    load_organisations("data/organisations.csv")
    load_people("data/organisations.csv")
    # os registros precisam existir ANTES das relações
    load_makers("data/object_maker.csv", "data/organisations.csv")

    # links com o Wikidata (opcional): só carrega se o arquivo existir
    if Path("data/sameas.csv").exists():
        load_sameas("data/sameas.csv")

    verificar()