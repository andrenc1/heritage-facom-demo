"""
Gera um RDF (Turtle) com TODOS os campos do CSV exportado do Tainacan.

Diferente do pipeline principal (facom_loader.py), este script NÃO usa o
framework, o Elasticsearch nem o Wikidata. Ele lê o CSV bruto e escreve uma
afirmação RDF para cada célula preenchida. Serve para mostrar que dá para ter
todos os campos em RDF, e para discutir qual propriedade cada campo deve virar.

Uso, de dentro do container (pasta /work), com o CSV em bruto/:
  python scripts/csv_para_rdf.py

Gera, em resultados/:
  acervo_completo.ttl     -> o RDF (abre em qualquer editor de texto)
  campos_propostos.csv    -> uma linha por coluna do CSV: se é publicada, qual
                             propriedade RDF recebe e em quantos itens está preenchida

Para mudar o que vira o quê, edite o dicionário CAMPOS logo abaixo:
  - troque a propriedade (DCTERMS.*, SDO.*, FACOM.* ou outra);
  - troque o segundo valor para False para NÃO publicar a coluna.
"""
import csv
import glob
import re
from pathlib import Path

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import DCTERMS, FOAF, RDF, RDFS, XSD

PREFIX = "http://example.org/facom/"      # provisório, como no resto do projeto
FACOM = Namespace(PREFIX + "prop/")       # termos próprios, para o que não tem vocabulário pronto
SDO = Namespace("https://schema.org/")

ENTRADA = sorted(glob.glob("bruto/*.csv"))
SAIDA_TTL = Path("resultados/acervo_completo.ttl")
SAIDA_CAMPOS = Path("resultados/campos_propostos.csv")

VAZIOS = {"", "-", "s", "s/r", "s\\r", "nan"}   # "s\\r" = "sem registro" digitado com barra invertida
CORRECOES_FABRICANTE = {"Dell lnc": "Dell Inc"}   # erro de digitação conhecido

# tipos: texto (como está), curto (tira ponto final), numero, url, autoria (vira ligação com o fabricante)
# formato: "coluna do Tainacan": (propriedade RDF, publicar?, tipo)
CAMPOS = {
    # --- identificação
    "special_item_id": (DCTERMS.identifier, True, "texto"),
    "Código do inventário": (FACOM.codigoInventario, True, "curto"),
    "Título": (RDFS.label, True, "texto"),
    "Categoria do acervo": (SDO.isPartOf, True, "curto"),
    "Termo": (DCTERMS.type, True, "curto"),
    "Classificação": (FACOM.classificacao, True, "curto"),
    # --- datas, autoria e origem
    "Data": (DCTERMS.date, True, "curto"),
    "Data Atribuída": (DCTERMS.created, True, "curto"),
    "Data de Aquisição": (DCTERMS.dateAccepted, True, "curto"),
    "Autoria": (FOAF.maker, True, "autoria"),
    "Origem": (DCTERMS.spatial, True, "curto"),
    "Procedência": (DCTERMS.provenance, True, "texto"),
    "Modo de aquisição": (FACOM.modoAquisicao, True, "curto"),
    # --- descrição física
    "Material e técnica": (DCTERMS.medium, True, "texto"),
    "Marcas e Inscrições": (FACOM.marcasInscricoes, True, "texto"),
    "Estado de Conservação": (FACOM.estadoConservacao, True, "curto"),
    "Dimensões": (DCTERMS.extent, True, "texto"),
    "Altura": (FACOM.altura, True, "numero"),
    "Comprimento": (FACOM.comprimento, True, "numero"),
    "Largura": (FACOM.largura, True, "numero"),
    "Diâmetro": (FACOM.diametro, True, "numero"),
    "Profundidade": (FACOM.profundidade, True, "numero"),
    "Peso": (FACOM.peso, True, "numero"),
    # --- textos
    "Descrição": (DCTERMS.description, True, "texto"),
    "Observações": (FACOM.observacoes, True, "texto"),
    "Dados Históricos": (FACOM.dadosHistoricos, True, "texto"),
    "Características técnicas/gerais": (FACOM.caracteristicasTecnicas, True, "texto"),
    "Registro Digital": (FACOM.registroDigital, True, "texto"),
    "Quantidade no Acervo": (FACOM.quantidade, True, "texto"),
    "Modalidade de preservação": (FACOM.modalidadePreservacao, True, "texto"),
    "public_url": (SDO.url, True, "url"),
    # --- internos: NÃO publicar por padrão (nomes de equipe, local físico, notas de conservação)
    "Localização": (FACOM.localizacao, False, "texto"),
    "Diagnóstico": (FACOM.diagnostico, False, "texto"),
    "Recomendações": (FACOM.recomendacoes, False, "texto"),
    "Fotógrafo": (FACOM.fotografo, False, "texto"),
    "Data foto": (FACOM.dataFoto, False, "texto"),
    "Responsável": (FACOM.responsavel, False, "texto"),
    "Data Preenchimento": (FACOM.dataPreenchimento, False, "texto"),
    # --- técnicos do Tainacan: não publicar
    "special_item_status": (FACOM.statusTainacan, False, "texto"),
    "special_document": (FACOM.documentoTainacan, False, "texto"),
    "special_thumbnail": (FACOM.miniaturaTainacan, False, "texto"),
    "special_attachments": (FACOM.anexosTainacan, False, "texto"),
    "special_comment_status": (FACOM.comentariosTainacan, False, "texto"),
    "special_item_author": (FACOM.autorCadastro, False, "texto"),
    "special_item_slug": (FACOM.slugTainacan, False, "texto"),
    "creation_date": (DCTERMS.created, False, "texto"),
    "user_last_modified": (FACOM.ultimoEditor, False, "texto"),
    "modification_date": (DCTERMS.modified, False, "texto"),
}


def limpar(valor, curto=False):
    """'sem informação' vira None; tira \\r e espaços; em campos curtos, tira o ponto final."""
    texto = (valor or "").replace("\r", "").strip()
    if texto.lower() in VAZIOS:
        return None
    if curto:
        texto = texto.rstrip(". ").strip()
    return texto or None


def slug(texto):
    return re.sub(r"[^a-z0-9]+", "-", texto.lower()).strip("-")


def como_numero(texto):
    try:
        n = texto.replace(",", ".")
        float(n)
        return Literal(n, datatype=XSD.decimal)   # decimal evita 1.4e+01 na saída
    except ValueError:
        return Literal(texto)   # não era número: guarda como texto, sem perder a informação


def main():
    if not ENTRADA:
        raise SystemExit("Nenhum CSV em bruto/. Coloque o arquivo exportado do Tainacan lá.")
    caminho = ENTRADA[0]
    print("Lendo:", caminho)

    g = Graph()
    for pref, ns in [("dcterms", DCTERMS), ("foaf", FOAF), ("rdfs", RDFS), ("schema", SDO), ("facom", FACOM)]:
        g.bind(pref, ns)

    preenchidos = {c: 0 for c in CAMPOS}
    desconhecidas = set()
    n_itens = 0
    organizacoes = set()

    with open(caminho, encoding="utf-8-sig", newline="") as f:
        for linha in csv.DictReader(f):
            # "Título|core_title|display_yes" -> "Título"
            linha = {c.split("|")[0]: v for c, v in linha.items()}
            desconhecidas |= set(linha) - set(CAMPOS)
            item = URIRef(PREFIX + "obj-" + linha["special_item_id"].strip())
            g.add((item, RDF.type, FACOM.Objeto))
            n_itens += 1

            for coluna, (prop, publicar, tipo) in CAMPOS.items():
                valor = limpar(linha.get(coluna), curto=(tipo in ("curto", "autoria")))
                if valor is None:
                    continue
                preenchidos[coluna] += 1
                if not publicar:
                    continue
                if tipo == "numero":
                    g.add((item, prop, como_numero(valor)))
                elif tipo == "url" and valor.startswith("http"):
                    g.add((item, prop, URIRef(valor)))
                elif tipo == "autoria":
                    nome = CORRECOES_FABRICANTE.get(valor, valor)
                    org = URIRef(PREFIX + "org-" + slug(nome))
                    g.add((item, prop, org))
                    if org not in organizacoes:
                        organizacoes.add(org)
                        g.add((org, RDFS.label, Literal(nome)))
                else:
                    g.add((item, prop, Literal(valor)))

    SAIDA_TTL.parent.mkdir(exist_ok=True)
    dados = g.serialize(format="turtle")
    if isinstance(dados, bytes):          # rdflib 5 devolve bytes; rdflib 6+ devolve texto
        dados = dados.decode("utf-8")
    SAIDA_TTL.write_text(dados, encoding="utf-8")

    with open(SAIDA_CAMPOS, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["coluna_tainacan", "publicar", "propriedade_rdf", "tipo", "itens_preenchidos"])
        for coluna, (prop, publicar, tipo) in CAMPOS.items():
            w.writerow([coluna, "sim" if publicar else "não", str(prop), tipo, preenchidos[coluna]])

    pub = [c for c, v in CAMPOS.items() if v[1]]
    print(f"{n_itens} itens, {len(organizacoes)} fabricantes, {len(g)} triplas -> {SAIDA_TTL}")
    print(f"Colunas publicadas: {len(pub)} de {len(CAMPOS)} (as outras são internas; veja {SAIDA_CAMPOS})")
    if desconhecidas:
        print("ATENÇÃO: colunas do CSV que não estão em CAMPOS (ignoradas):", sorted(desconhecidas))


if __name__ == "__main__":
    main()
