"""
Gera uma página HTML com o grafo do Fuseki desenhado (nós e setas), com
opções para explorar: filtrar por tipo de relação, esconder itens do
Wikidata, buscar um nó, destacar os vizinhos de um nó e marcar os
fabricantes que ficaram sem ligação com o Wikidata.

Lê as triplas do Fuseki (as mesmas que você consulta em http://localhost:3030)
e escreve resultados/grafo.html. Depois é só abrir esse arquivo no navegador.

Uso, de dentro do container (pasta /work), depois de rodar es_para_fuseki.py:
  python scripts/grafo_html.py

Para mostrar nomes em vez de códigos (Q30 -> Estados Unidos, P17 -> país), o
script pergunta os nomes ao Wikidata e guarda em resultados/wikidata_nomes.json
(só pergunta o que ainda não tem). Se o Wikidata não responder, o grafo sai
igual, só com os códigos.
"""
import json
import time
from pathlib import Path

import requests

ENDPOINT = "http://fuseki:3030/heritage-connector/sparql"
API = "https://www.wikidata.org/w/api.php"
SAIDA = Path("resultados/grafo.html")
CACHE = Path("resultados/wikidata_nomes.json")
LOCAL = "http://example.org/facom/"

PREFIXOS = {
    "http://www.w3.org/2000/01/rdf-schema#": "rdfs:",
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#": "rdf:",
    "http://www.w3.org/2002/07/owl#": "owl:",
    "http://xmlns.com/foaf/0.1/": "foaf:",
    "http://www.wikidata.org/prop/direct/": "",       # P17, P31...
    "http://www.wikidata.org/entity/": "",            # Q30, Q5...
    LOCAL: "",
}
LABEL = "http://www.w3.org/2000/01/rdf-schema#label"

# Nomes das relações que não são do Wikidata
NOMES_FIXOS = {
    "rdf:type": "tipo",
    "foaf:maker": "feito por",
    "foaf:made": "fez",
    "owl:sameAs": "mesmo que (Wikidata)",
}

try:
    from heritageconnector.config import config
    CONTATO = getattr(config, "CUSTOM_USER_AGENT", "heritageconnector-teste")
except Exception:
    CONTATO = "heritageconnector-teste"
HEADERS = {"User-Agent": f"FacomTeste/0.1 ({CONTATO})"}


def curto(uri):
    for base, pref in PREFIXOS.items():
        if uri.startswith(base):
            return pref + uri[len(base):]
    return uri.rsplit("/", 1)[-1].rsplit("#", 1)[-1]


def tipo_do_no(uri):
    if uri.startswith(LOCAL):
        return "objeto" if uri[len(LOCAL):].startswith("obj-") else "fabricante"
    if "wikidata.org" in uri:
        return "wikidata"
    return "outro"


def buscar_triplas():
    resp = requests.post(
        ENDPOINT,
        data={"query": "SELECT ?s ?p ?o WHERE { ?s ?p ?o }"},
        headers={"Accept": "application/sparql-results+json"},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["results"]["bindings"]


def montar(triplas):
    nos, arestas, detalhes, rotulos = {}, [], {}, {}

    def no(uri):
        if uri not in nos:
            nos[uri] = {"id": uri, "grupo": tipo_do_no(uri)}
            detalhes[uri] = []
        return nos[uri]

    for t in triplas:
        s, p, o = t["s"]["value"], t["p"]["value"], t["o"]
        no(s)
        if o["type"] == "uri":
            no(o["value"])
            arestas.append({"from": s, "to": o["value"], "chave": curto(p)})
        else:
            if p == LABEL and s not in rotulos:
                rotulos[s] = o["value"]
            detalhes[s].append(f"{curto(p)}: {o['value']}")

    for uri, n in nos.items():
        n["codigo"] = curto(uri)
        n["label"] = rotulos.get(uri) or curto(uri)
        n["info"] = sorted(detalhes[uri])
        n["uri"] = uri
    return list(nos.values()), arestas


def buscar_nomes(ids):
    """Pergunta ao Wikidata o nome (pt, senão en) de cada código Q/P."""
    nomes = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    faltam = sorted(i for i in ids if i not in nomes)
    for i in range(0, len(faltam), 50):
        lote = faltam[i:i + 50]
        for tentativa in range(1, 5):
            try:
                r = requests.get(API, params={
                    "action": "wbgetentities", "ids": "|".join(lote),
                    "props": "labels", "languages": "pt|en", "format": "json",
                }, headers=HEADERS, timeout=30)
                if r.status_code == 429:
                    retry = r.headers.get("Retry-After", "")
                    time.sleep(int(retry) if retry.isdigit() else 5 * tentativa)
                    continue
                r.raise_for_status()
                for k, v in r.json().get("entities", {}).items():
                    lab = v.get("labels", {})
                    nome = (lab.get("pt") or lab.get("en") or {}).get("value")
                    if nome:
                        nomes[k] = nome
                break
            except requests.RequestException as erro:
                print(f"  (sem resposta do Wikidata: {erro.__class__.__name__})")
                time.sleep(3)
        time.sleep(1)
    CACHE.parent.mkdir(exist_ok=True)
    CACHE.write_text(json.dumps(nomes, ensure_ascii=False, indent=1), encoding="utf-8")
    return nomes


PALETA = ["#1f77b4", "#2ca02c", "#d62728", "#8c564b", "#17becf", "#bcbd22",
          "#e377c2", "#ff7f0e", "#7f7f7f", "#0b6e4f", "#a05195", "#665191"]


def preparar_relacoes(nos, arestas, nomes):
    for n in nos:
        if n["grupo"] == "wikidata":
            n["nome"] = nomes.get(n["codigo"])
    contagem = {}
    for a in arestas:
        contagem[a["chave"]] = contagem.get(a["chave"], 0) + 1
    rels = []
    for i, (chave, qtd) in enumerate(sorted(contagem.items(), key=lambda x: -x[1])):
        nome = NOMES_FIXOS.get(chave) or nomes.get(chave) or chave
        cor = "#b0b0b0" if chave == "rdf:type" else (
            "#9a6fc4" if chave == "owl:sameAs" else PALETA[i % len(PALETA)])
        rels.append({"chave": chave, "nome": nome, "n": qtd, "cor": cor})
    nome_rel = {r["chave"]: r["nome"] for r in rels}
    for a in arestas:
        a["nome"] = nome_rel[a["chave"]]
    return rels


PAGINA = """<!doctype html>
<html lang="pt-br"><head><meta charset="utf-8">
<title>Grafo do acervo - Museu FACOM</title>
<script src="https://unpkg.com/vis-network@9.1.9/standalone/umd/vis-network.min.js"></script>
<style>
 body{margin:0;font-family:system-ui,sans-serif;display:flex;height:100vh;font-size:14px}
 #rede{flex:1;min-width:0}
 #lado{width:360px;border-left:1px solid #ccc;padding:12px;overflow:auto}
 .leg span.b{display:inline-block;width:12px;height:12px;border-radius:50%;margin-right:6px;vertical-align:middle}
 .leg div{margin:3px 0}
 #esq{width:340px;border-right:1px solid #ccc;padding:12px;overflow:auto;box-sizing:border-box}
 #lado{box-sizing:border-box}
 #det h4{margin:0 0 4px;font-size:16px}
 #det .uri{color:#777;font-size:12px;word-break:break-all;margin-bottom:6px}
 #det h5{margin:12px 0 4px;font-size:12px;color:#444;text-transform:uppercase;letter-spacing:.04em}
 #det ul{margin:0;padding-left:16px}
 #det li{margin:2px 0}
 #det a{color:#1a5fb4;cursor:pointer;text-decoration:underline}
 #det .off{color:#999}
 #det .aviso{color:#d62728;margin:6px 0}
 #det details{margin-top:12px;color:#666;font-size:12px}
 #det .nota{color:#999;font-size:12px;margin-top:10px}
 h3{margin:.9em 0 .3em} h3:first-child{margin-top:0}
 label{display:block;margin:3px 0;cursor:pointer}
 .rel{display:flex;align-items:center;gap:6px}
 .rel i{display:inline-block;width:18px;height:4px;flex:none}
 .rel small{color:#777;margin-left:auto}
 button{margin:2px 4px 2px 0;padding:3px 8px;cursor:pointer}
 input[type=text]{width:100%;box-sizing:border-box;padding:5px}
 #cont{color:#555;margin:.4em 0}
</style></head><body>
<div id="esq">
 <h3>Detalhes</h3>
 <div id="det"></div>
</div>
<div id="rede"></div>
<div id="lado">
 <h3>Grafo do acervo</h3>
 <div id="cont"></div>
 <div class="leg">
  <div><span class="b" style="background:#4f8bd6"></span>objeto do museu</div>
  <div><span class="b" style="background:#e8923c"></span>fabricante / pessoa</div>
  <div><span class="b" style="background:#9a6fc4"></span>item do Wikidata</div>
  <div><span class="b" style="background:#fff;border:3px dashed #d62728;box-sizing:border-box"></span>fabricante sem ligação com o Wikidata</div>
 </div>

 <h3>Buscar</h3>
 <input type="text" id="busca" list="nomes" placeholder="nome de um objeto ou fabricante">
 <datalist id="nomes"></datalist>

 <h3>Mostrar</h3>
 <label><input type="checkbox" id="wd" checked> itens do Wikidata</label>
 <label><input type="checkbox" id="soltos" checked> esconder itens do Wikidata sem nenhuma seta visível</label>
 <label><input type="checkbox" id="rotulos"> nomes em todas as setas (ao clicar num nó, as dele aparecem sozinhas)</label>
 <label><input type="checkbox" id="codigos"> códigos junto dos nomes (Q30)</label>
 <label><input type="checkbox" id="semlig" checked> destacar fabricantes sem ligação</label>
 <label><input type="checkbox" id="viz" checked> ao clicar, destacar só os vizinhos</label>
 <label><input type="checkbox" id="parar"> congelar as posições (desmarque para o desenho se reorganizar)</label>

 <h3>Relações (setas)</h3>
 <div>
  <button id="limpa">visão limpa</button><button id="todas">todas</button><button id="nenhuma">nenhuma</button>
  <button id="museu">só objeto ↔ fabricante</button>
  <button id="semtipo">tudo, menos tipo</button>
 </div>
 <div id="rels"></div>

 <p style="color:#777">Arraste os círculos, use a roda do mouse para o zoom e clique no fundo para limpar o destaque.</p>
</div>
<script>
const nos = __NOS__;
const arestas = __ARESTAS__;
const rels = __RELS__;
const cor = {objeto:"#4f8bd6", fabricante:"#e8923c", wikidata:"#9a6fc4", outro:"#999"};
const estado = {wd:true, soltos:true, rotulos:false, codigos:false, semlig:true, viz:true, foco:null, sel:null};
const relOn = {};
const relPor = {};
// visão inicial limpa: só o que conta a história (quem fez, quem é no Wikidata, país, sede, fundador)
const PADRAO = new Set(["foaf:maker", "owl:sameAs", "P17", "P159", "P112"]);
rels.forEach(r => { relOn[r.chave] = PADRAO.has(r.chave); relPor[r.chave] = r; });
const porId = {};
nos.forEach(n => { porId[n.id] = n; });
const comSame = new Set(arestas.filter(a => a.chave === "owl:sameAs").map(a => a.from));
nos.forEach(n => { n.semLigacao = n.grupo === "fabricante" && !comSame.has(n.id); });

const $ = id => document.getElementById(id);
const esc = t => String(t).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");

function nomeNo(n) {
  if (n.grupo !== "wikidata") return n.label;
  if (!n.nome) return n.codigo;
  return estado.codigos ? n.nome + " (" + n.codigo + ")" : n.nome;
}

const dsNos = new vis.DataSet();
const dsAr = new vis.DataSet();
const rede = new vis.Network($("rede"), {nodes:dsNos, edges:dsAr},
  {physics:{solver:"forceAtlas2Based", forceAtlas2Based:{gravitationalConstant:-90, springLength:140, avoidOverlap:0.6},
            stabilization:{iterations:200, updateInterval:50}},
   interaction:{hover:false, hideEdgesOnDrag:true, hideEdgesOnZoom:true},
   edges:{smooth:false, arrows:{to:{scaleFactor:0.5}}}});
// depois de organizar o desenho, para a física: fica leve para arrastar e dar zoom
rede.once("stabilizationIterationsDone", () => {
  rede.setOptions({physics:{enabled:false}});
  $("parar").checked = true;
});

function aplicar() {
  const ok = arestas.map(a => {
    if (!relOn[a.chave]) return false;
    if (!estado.wd && (porId[a.from].grupo === "wikidata" || porId[a.to].grupo === "wikidata")) return false;
    return true;
  });
  const grau = {};
  const vizinhos = {};
  arestas.forEach((a, i) => {
    if (!ok[i]) return;
    grau[a.from] = (grau[a.from] || 0) + 1;
    grau[a.to] = (grau[a.to] || 0) + 1;
    (vizinhos[a.from] = vizinhos[a.from] || new Set()).add(a.to);
    (vizinhos[a.to] = vizinhos[a.to] || new Set()).add(a.from);
  });
  const foco = estado.foco;
  const emFoco = foco ? new Set([foco].concat(Array.from(vizinhos[foco] || []))) : null;

  const lista = nos.map(n => {
    const wd = n.grupo === "wikidata";
    let oculto = wd && !estado.wd;
    if (!oculto && wd && estado.soltos && !grau[n.id]) oculto = true;
    const fraco = emFoco && !emFoco.has(n.id);
    const c = cor[n.grupo];
    const marca = estado.semlig && n.semLigacao;
    return {
      id:n.id, label:nomeNo(n), hidden:oculto, shape:"dot",
      size: n.grupo === "objeto" ? 14 : 20,
      opacity: fraco ? 0.15 : 1,
      font:{size:12, color: fraco ? "rgba(0,0,0,0.25)" : "#222", strokeWidth:3, strokeColor:"#ffffff"},
      borderWidth: marca ? 4 : 1,
      shapeProperties:{borderDashes: marca ? [4,3] : false},
      color:{background:c, border: marca ? "#d62728" : "#333",
             highlight:{background:c, border:"#000"},
             hover:{background:c, border:"#000"}}
    };
  });
  dsNos.update(lista);

  const ocultoNo = {};
  lista.forEach(x => { ocultoNo[x.id] = x.hidden; });
  ocultos = ocultoNo;
  let visAr = 0;
  const listaAr = arestas.map((a, i) => {
    const r = relPor[a.chave];
    const fraca = emFoco && !(a.from === foco || a.to === foco);
    const oculta = !ok[i] || ocultoNo[a.from] || ocultoNo[a.to];
    if (!oculta) visAr++;
    return {
      id:i, from:a.from, to:a.to, arrows:{to:{enabled:true, scaleFactor:0.5}}, hidden:oculta,
      label: (estado.rotulos || (foco && !fraca)) ? a.nome : "", font:{size:10, align:"middle"},
      dashes: a.chave === "owl:sameAs",
      width: a.chave === "rdf:type" ? 1 : 1.5,
      color:{color:r.cor, opacity: fraca ? 0.08 : 1}
    };
  });
  dsAr.update(listaAr);
  const visNos = lista.filter(x => !x.hidden).length;
  if (estado.sel) mostrarDetalhes(estado.sel); else $("det").innerHTML = VAZIO_DET;
  $("cont").textContent = visNos + " nós e " + visAr + " setas visíveis (de " + nos.length + " e " + arestas.length + ")";
}

const TEC = new Set(["database", "hasTopConcept"]);   // triplas técnicas, vão para "dados técnicos"
const VAZIO_DET = '<p style="color:#777">Clique em um nó para ver os detalhes dele aqui.</p>';
let ocultos = {};

function ligacao(id) {
  const t = esc(nomeNo(porId[id]));
  return ocultos[id] ? '<span class="off">' + t + '</span>' : '<a data-id="' + esc(id) + '">' + t + '</a>';
}

function mostrarDetalhes(id) {
  const n = porId[id];
  const textos = [], tec = [];
  n.info.forEach(t => { (TEC.has(t.split(":")[0]) ? tec : textos).push(t); });
  const saem = arestas.filter(a => a.from === id);
  const chegam = arestas.filter(a => a.to === id);
  const cls = a => relOn[a.chave] ? "" : ' class="off"';
  let h = '<h4>' + esc(nomeNo(n)) + '</h4><div class="uri">' + esc(n.uri) + '</div>';
  if (n.semLigacao) h += '<div class="aviso">Fabricante sem ligação com o Wikidata</div>';
  if (textos.length) h += '<h5>Textos</h5><ul>' + textos.map(t => '<li>' + esc(t) + '</li>').join("") + '</ul>';
  if (saem.length) h += '<h5>Aponta para</h5><ul>' + saem.map(a =>
    '<li' + cls(a) + '>' + esc(a.nome) + ' → ' + ligacao(a.to) + '</li>').join("") + '</ul>';
  if (chegam.length) h += '<h5>Recebe de</h5><ul>' + chegam.map(a =>
    '<li' + cls(a) + '>' + ligacao(a.from) + ' → ' + esc(a.nome) + '</li>').join("") + '</ul>';
  if (saem.concat(chegam).some(a => !relOn[a.chave]))
    h += '<div class="nota">Em cinza: relações desligadas no filtro.</div>';
  if (tec.length) h += '<details><summary>dados técnicos</summary>' + tec.map(t => esc(t)).join("<br>") + '</details>';
  $("det").innerHTML = h;
}

function selecionar(id) {
  estado.sel = id;
  estado.foco = estado.viz ? id : null;
  rede.selectNodes([id]);
  rede.focus(id, {scale:1.3, animation:true});
  aplicar();
}
// links dentro do painel de detalhes levam ao outro nó
$("det").addEventListener("click", e => {
  const id = e.target.dataset && e.target.dataset.id;
  if (id) selecionar(id);
});

// painel de relações
$("rels").innerHTML = rels.map(r =>
  '<label class="rel"><input type="checkbox" data-chave="' + esc(r.chave) + '"' + (relOn[r.chave] ? ' checked' : '') + '>' +
  '<i style="background:' + r.cor + '"></i><span>' + esc(r.nome) + ' <small>(' + esc(r.chave) + ')</small></span>' +
  '<small>' + r.n + '</small></label>').join("");
function marcarRels(fn) {
  document.querySelectorAll("#rels input").forEach(c => {
    c.checked = fn(c.dataset.chave);
    relOn[c.dataset.chave] = c.checked;
  });
  aplicar();
}
document.querySelectorAll("#rels input").forEach(c =>
  c.addEventListener("change", () => { relOn[c.dataset.chave] = c.checked; aplicar(); }));
$("limpa").addEventListener("click", () => marcarRels(k => PADRAO.has(k)));
$("todas").addEventListener("click", () => marcarRels(() => true));
$("nenhuma").addEventListener("click", () => marcarRels(() => false));
$("museu").addEventListener("click", () => marcarRels(k => k === "foaf:maker" || k === "foaf:made" || k === "P1056"));
$("semtipo").addEventListener("click", () => marcarRels(k => k !== "rdf:type"));

// opções
[["wd","wd"],["soltos","soltos"],["rotulos","rotulos"],["codigos","codigos"],["semlig","semlig"],["viz","viz"]].forEach(p =>
  $(p[0]).addEventListener("change", e => { estado[p[1]] = e.target.checked; if (p[0] === "viz" && !e.target.checked) estado.foco = null; aplicar(); }));
$("parar").addEventListener("change", e => rede.setOptions({physics:{enabled: !e.target.checked}}));

// busca
$("nomes").innerHTML = nos.filter(n => n.grupo !== "wikidata").map(n => '<option value="' + esc(n.label) + '">').join("");
$("busca").addEventListener("change", e => {
  const t = e.target.value.trim().toLowerCase();
  if (!t) return;
  const acha = x => nomeNo(x).toLowerCase() === t;
  const contem = x => nomeNo(x).toLowerCase().includes(t);
  const n = nos.find(acha) || nos.find(contem);
  if (!n) { $("det").innerHTML = '<p>Nada encontrado para: ' + esc(e.target.value) + '</p>'; return; }
  if (ocultos[n.id]) {
    $("det").innerHTML = '<p>"' + esc(nomeNo(n)) + '" existe, mas está escondido pelos filtros atuais. Ligue os itens do Wikidata ou a relação dele.</p>';
    return;
  }
  selecionar(n.id);
});

rede.on("click", p => {
  if (!p.nodes.length) { estado.sel = null; estado.foco = null; aplicar(); return; }
  estado.sel = p.nodes[0];
  estado.foco = estado.viz ? p.nodes[0] : null;
  aplicar();
});

aplicar();
</script></body></html>
"""


def js_json(obj):
    """JSON para colar dentro de <script>: evita que um texto com '</script>' quebre a página."""
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")


def main():
    triplas = buscar_triplas()
    nos, arestas = montar(triplas)
    ids = {n["codigo"] for n in nos if n["grupo"] == "wikidata"}
    ids |= {a["chave"] for a in arestas if a["chave"][:1] == "P" and a["chave"][1:].isdigit()}
    print(f"Buscando {len(ids)} nomes no Wikidata (os já conhecidos vêm do cache)...")
    nomes = buscar_nomes(ids)
    rels = preparar_relacoes(nos, arestas, nomes)

    SAIDA.parent.mkdir(exist_ok=True)
    html = (PAGINA
            .replace("__NOS__", js_json(nos))
            .replace("__ARESTAS__", js_json(arestas))
            .replace("__RELS__", js_json(rels)))
    SAIDA.write_text(html, encoding="utf-8")
    print(f"{len(triplas)} triplas -> {len(nos)} nós e {len(arestas)} setas")
    print(f"Abra no navegador: {SAIDA}")


if __name__ == "__main__":
    main()
