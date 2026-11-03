"""
Busca no Wikidata as propriedades dos itens que você ligou em data/sameas.csv
e as junta aos registros do museu.

Fluxo:
  1. lê data/sameas.csv (só linhas com wikidata_id preenchido);
  2. pede ao Wikidata os dados desses itens (API wbgetentities);
  3. salva uma tabela legível em resultados/wikidata_propriedades.csv;
  4. grava no Elasticsearch, nos seus registros, as relações cujo valor é
     outro item do Wikidata (país, tipo, setor...), como o artigo faz.

Uso, de dentro do container (pasta /app), DEPOIS de rodar o facom_loader.py:
  python scripts/buscar_propriedades.py

ATENÇÃO: o facom_loader.py apaga e recria o índice. Se rodá-lo de novo,
rode este script em seguida.
"""
import os
import time

import pandas as pd
import requests

API = "https://www.wikidata.org/w/api.php"
IDIOMAS = "pt|en"
PREFIX = "http://example.org/facom/"  # o mesmo do facom_loader.py

# Propriedades cujo valor é OUTRO ITEM do Wikidata (viram relações no grafo)
PROPS_ITEM = {
    "P31": "instância de",
    "P17": "país",
    "P159": "sede",
    "P452": "setor/indústria",
    "P112": "fundado por",
    "P27": "cidadania",
    "P106": "ocupação",
    "P749": "empresa-mãe",
}
# Propriedades cujo valor é texto ou data (só vão para o CSV)
PROPS_TEXTO = {
    "P571": "data de fundação",
    "P856": "site oficial",
    "P569": "data de nascimento",
    "P570": "data de morte",
}

try:
    from heritageconnector.config import config
    CONTATO = getattr(config, "CUSTOM_USER_AGENT", "heritageconnector-teste")
except Exception:
    config = None
    CONTATO = "heritageconnector-teste"
HEADERS = {"User-Agent": f"FacomTeste/0.1 ({CONTATO})"}


def pedir(ids, props):
    """Chama wbgetentities para até 50 ids de uma vez."""
    resp = requests.get(
        API,
        params={
            "action": "wbgetentities",
            "ids": "|".join(ids),
            "props": props,
            "languages": IDIOMAS,
            "format": "json",
        },
        headers=HEADERS,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("entities", {})


def rotulo(ent):
    labels = ent.get("labels", {})
    for lang in ("pt", "en"):
        if lang in labels:
            return labels[lang]["value"]
    return ent.get("id", "")


def valores(ent, pid):
    """Devolve os valores 'brutos' de uma propriedade (ignora os sem valor)."""
    saida = []
    for decl in ent.get("claims", {}).get(pid, []):
        dv = decl.get("mainsnak", {}).get("datavalue")
        if dv:
            saida.append(dv["value"])
    return saida


def formatar_data(v):
    # '+1908-00-00T00:00:00Z' -> '1908'; '+1908-05-12T...' -> '1908-05-12'
    t = v["time"].lstrip("+")[:10]
    ano, mes, dia = t.split("-")
    if mes == "00":
        return ano
    if dia == "00":
        return f"{ano}-{mes}"
    return t


def main():
    sameas = pd.read_csv("data/sameas.csv").dropna(subset=["wikidata_id"])
    sameas["wikidata_id"] = sameas["wikidata_id"].astype(str).str.strip()
    sameas = sameas[sameas["wikidata_id"] != ""]
    qids = list(sameas["wikidata_id"].unique())
    print(f"{len(qids)} itens do Wikidata para consultar")

    itens = pedir(qids, "labels|descriptions|claims")

    # 1ª passada: coleta valores e os QIDs que precisam de rótulo
    brutos = {}   # qid -> {pid: [valores]}
    precisam_rotulo = set()
    for qid, ent in itens.items():
        brutos[qid] = {}
        for pid in list(PROPS_ITEM) + list(PROPS_TEXTO):
            vals = valores(ent, pid)
            brutos[qid][pid] = vals
            if pid in PROPS_ITEM:
                precisam_rotulo.update(
                    v["id"] for v in vals if isinstance(v, dict) and "id" in v
                )

    # 2ª passada: rótulos legíveis dos itens referenciados (ex.: Q30 -> EUA)
    rotulos = {}
    alvo = sorted(precisam_rotulo)
    for i in range(0, len(alvo), 50):
        for q, e in pedir(alvo[i:i + 50], "labels").items():
            rotulos[q] = rotulo(e)
        time.sleep(0.5)

    linhas = []
    triplas = []  # (uri_interna, pid, qid_alvo)
    for _, reg in sameas.iterrows():
        qid = reg["wikidata_id"]
        ent = itens.get(qid)
        if not ent or "missing" in ent:
            print(f"  ! {qid} não existe no Wikidata (confira o sameas.csv)")
            continue
        linha = {
            "internal_id": reg["internal_id"],
            "nome_no_museu": reg.get("nome_no_museu", ""),
            "wikidata_id": qid,
            "wikidata_label": rotulo(ent),
            "wikidata_descricao": next(
                (ent["descriptions"][l]["value"] for l in ("pt", "en")
                 if l in ent.get("descriptions", {})), ""),
        }
        for pid, nome in PROPS_ITEM.items():
            alvos = [v["id"] for v in brutos[qid][pid]
                     if isinstance(v, dict) and "id" in v]
            linha[nome] = "; ".join(rotulos.get(a, a) for a in alvos)
            triplas += [(PREFIX + str(reg["internal_id"]), pid, a) for a in alvos]
        for pid, nome in PROPS_TEXTO.items():
            vs = brutos[qid][pid]
            if pid in ("P571", "P569", "P570"):
                txt = "; ".join(formatar_data(v) for v in vs if "time" in v)
            else:
                txt = "; ".join(str(v) for v in vs)
            linha[nome] = txt
        linhas.append(linha)

    tabela = pd.DataFrame(linhas)
    os.makedirs("resultados", exist_ok=True)
    tabela.to_csv("resultados/wikidata_propriedades.csv", index=False)
    print("\nTabela salva em resultados/wikidata_propriedades.csv\n")
    for _, l in tabela.iterrows():
        print(f"=== {l['nome_no_museu']}  ->  {l['wikidata_id']} ({l['wikidata_label']})")
        for nome in list(PROPS_ITEM.values()) + list(PROPS_TEXTO.values()):
            if l[nome]:
                print(f"    {nome}: {l[nome]}")

    # --- grava as relações no Elasticsearch ---
    if not triplas:
        print("\nNenhuma relação para gravar.")
        return
    from heritageconnector import datastore
    from heritageconnector.config import field_mapping
    from heritageconnector.namespace import WDT
    from heritageconnector.utils.wikidata import qid_to_url

    record_loader = datastore.RecordLoader(
        collection_name="FACOM", field_mapping=field_mapping
    )
    df = pd.DataFrame(triplas, columns=["URI", "pid", "qid"])
    df["URL"] = df["qid"].apply(qid_to_url)
    for pid, parte in df.groupby("pid"):
        print(f"gravando {len(parte)} relações {pid} ({PROPS_ITEM[pid]})")
        record_loader.add_triples(
            parte, WDT[pid], subject_col="URI", object_col="URL"
        )
    print("\nPronto. Confira no Elasticsearch o campo graph de uma organização.")


if __name__ == "__main__":
    main()
