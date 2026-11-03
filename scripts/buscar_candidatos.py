"""
Busca, no Wikidata, candidatos para cada registro de data/organisations.csv.

É a mesma ideia da etapa "Search" do Record Linkage do artigo (seção 4.1.2):
para cada registro, procurar pelo nome os itens mais parecidos do Wikidata.
Aqui usamos a API pública do Wikidata, que serve bem para poucos registros
(o artigo usa um índice próprio porque a API é lenta para milhares).

Se o Wikidata responder "429 Too Many Requests" (limite de pedidos), o script
espera e tenta de novo, em vez de parar.

Uso, de dentro do container (pasta /work):
  python scripts/buscar_candidatos.py

Gera:
  resultados/sameas_candidatos.csv  -> todos os candidatos, para você consultar
  data/sameas.csv             -> modelo para VOCÊ preencher o wikidata_id
                                 (só é criado se ainda não existir, para não
                                 apagar o que você já preencheu)
"""
import time
from pathlib import Path

import pandas as pd
import requests

API = "https://www.wikidata.org/w/api.php"
IDIOMAS = ["pt", "en"]   # procura nos dois e junta os resultados
POR_BUSCA = 5            # quantos candidatos por idioma
PAUSA_ENTRE_BUSCAS = 1.5     # segundos entre uma busca e outra
PAUSA_ENTRE_REGISTROS = 1.0  # segundos entre um fabricante e o próximo
TENTATIVAS = 5               # quantas vezes tentar de novo após um 429
ESPERA_MAXIMA = 120          # nunca esperar mais que isso de uma vez (s)

try:
    from heritageconnector.config import config
    CONTATO = getattr(config, "CUSTOM_USER_AGENT", "heritageconnector-teste")
except Exception:
    CONTATO = "heritageconnector-teste"

HEADERS = {"User-Agent": f"FacomTeste/0.1 ({CONTATO})"}


def buscar(nome, idioma):
    """Uma busca na API. Devolve a lista de itens, ou None se não conseguiu."""
    params = {
        "action": "wbsearchentities",
        "search": nome,
        "language": idioma,
        "uselang": idioma,
        "type": "item",
        "limit": POR_BUSCA,
        "format": "json",
    }
    espera = 5
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            resp = requests.get(API, params=params, headers=HEADERS, timeout=30)
        except requests.RequestException as erro:
            print(f"  (erro de rede: {erro.__class__.__name__}; tentativa {tentativa}/{TENTATIVAS})")
            time.sleep(espera)
            espera = min(espera * 2, ESPERA_MAXIMA)
            continue

        if resp.status_code == 429:
            # O Wikidata às vezes diz quanto esperar no cabeçalho Retry-After
            retry = resp.headers.get("Retry-After", "")
            pausa = int(retry) if retry.isdigit() else espera
            pausa = min(pausa, ESPERA_MAXIMA)
            print(f"  (limite do Wikidata: aguardando {pausa}s; tentativa {tentativa}/{TENTATIVAS})")
            time.sleep(pausa)
            espera = min(espera * 2, ESPERA_MAXIMA)
            continue

        resp.raise_for_status()
        return resp.json().get("search", [])

    return None  # desistiu


def main():
    Path("resultados").mkdir(exist_ok=True)
    registros = pd.read_csv("data/organisations.csv")
    linhas = []
    falhas = []

    for _, reg in registros.iterrows():
        nome = reg["label"]
        vistos = set()
        falhou = False
        print(f"\n=== {nome}  ({reg['id']})")
        ordem = 0
        for idioma in IDIOMAS:
            itens = buscar(nome, idioma)
            if itens is None:
                falhou = True
                itens = []
            for item in itens:
                if item["id"] in vistos:
                    continue
                vistos.add(item["id"])
                ordem += 1
                desc = item.get("description", "")
                rotulo = item.get("label", "")
                print(f"  {item['id']:<10} {rotulo}  |  {desc}")
                linhas.append({
                    "internal_id": reg["id"],
                    "nome_no_museu": nome,
                    "ordem": ordem,
                    "wikidata_id": item["id"],
                    "wikidata_label": rotulo,
                    "wikidata_descricao": desc,
                    "url": f"https://www.wikidata.org/wiki/{item['id']}",
                })
            time.sleep(PAUSA_ENTRE_BUSCAS)  # gentileza com o servidor
        if falhou:
            falhas.append(nome)
            print("  (busca incompleta: o Wikidata não respondeu a tempo)")
        elif not vistos:
            print("  (nenhum candidato encontrado)")
        time.sleep(PAUSA_ENTRE_REGISTROS)

    pd.DataFrame(linhas).to_csv("resultados/sameas_candidatos.csv", index=False)
    print("\nCandidatos salvos em resultados/sameas_candidatos.csv")

    if falhas:
        print("\nATENÇÃO: estas buscas ficaram incompletas (limite de pedidos).")
        print("Espere alguns minutos e rode o script de novo:")
        for n in falhas:
            print(f"  - {n}")

    modelo = Path("data/sameas.csv")
    if modelo.exists():
        print("data/sameas.csv já existe: não foi alterado.")
    else:
        pd.DataFrame(
            {"internal_id": registros["id"], "nome_no_museu": registros["label"],
             "wikidata_id": ""}
        ).to_csv(modelo, index=False)
        print("Modelo criado em data/sameas.csv. Preencha a coluna wikidata_id.")


if __name__ == "__main__":
    main()