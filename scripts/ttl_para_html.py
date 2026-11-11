"""
Gera resultados/acervo_completo.html: uma página para explorar o RDF completo.
Lê resultados/acervo_completo.ttl e resultados/campos_propostos.csv (gerados por csv_para_rdf.py).
Uso:  python scripts/ttl_para_html.py     (depois abra o .html com duplo clique)
"""
import csv, json
from pathlib import Path
from rdflib import Graph, URIRef, Literal, RDF, RDFS

TTL = Path("resultados/acervo_completo.ttl")
CAMPOS = Path("resultados/campos_propostos.csv")
SAIDA = Path("resultados/acervo_completo.html")

g = Graph(); g.parse(data=TTL.read_text(encoding="utf-8"), format="turtle")   # data= funciona em qualquer versão do rdflib
colunas = list(csv.DictReader(open(CAMPOS, encoding="utf-8")))
pred2col = {c["propriedade_rdf"]: c["coluna_tainacan"] for c in colunas if c["publicar"] == "sim"}
curto = lambda u: str(u).split("#")[-1].split("/")[-1]

itens = []
for s in g.subjects(RDF.type, None):
    if "/obj-" not in str(s):
        continue
    campos = []
    for p, o in g.predicate_objects(s):
        if p == RDF.type:
            continue
        nome = pred2col.get(str(p), curto(p))
        if isinstance(o, URIRef):
            lab = g.value(o, RDFS.label)
            valor = {"link": str(o), "texto": str(lab) if lab else str(o)}
        else:
            valor = {"texto": str(o)}
        campos.append({"coluna": nome, "pred": g.namespace_manager.normalizeUri(p), "valor": valor})
    ordem = [c["coluna_tainacan"] for c in colunas]
    campos.sort(key=lambda c: ordem.index(c["coluna"]) if c["coluna"] in ordem else 99)
    titulo = g.value(s, RDFS.label)
    itens.append({"uri": str(s), "titulo": str(titulo), "n": len(campos), "campos": campos})
itens.sort(key=lambda i: i["titulo"].lower())

HTML = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Acervo FACOM em RDF</title>
<style>
:root{--bg:#fff;--fg:#1f2328;--mut:#656d76;--bd:#d0d7de;--ac:#0969da;--sf:#f6f8fa;--ok:#1a7f37;--no:#9a6700}
@media(prefers-color-scheme:dark){:root{--bg:#0d1117;--fg:#e6edf3;--mut:#8b949e;--bd:#30363d;--ac:#58a6ff;--sf:#161b22;--ok:#3fb950;--no:#d29922}}
*{box-sizing:border-box}body{margin:0;font:15px/1.5 system-ui,sans-serif;background:var(--bg);color:var(--fg)}
header{padding:14px 20px;border-bottom:1px solid var(--bd)}h1{margin:0;font-size:18px}
header p{margin:2px 0 0;color:var(--mut);font-size:13px}
nav{display:flex;gap:4px;padding:8px 20px;border-bottom:1px solid var(--bd)}
nav button{background:none;border:0;padding:6px 12px;border-radius:6px;color:var(--mut);font:inherit;cursor:pointer}
nav button.on{background:var(--sf);color:var(--fg);font-weight:600}
.pg{display:none}.pg.on{display:block}
#itens.on{display:grid;grid-template-columns:300px 1fr;height:calc(100vh - 112px)}
#lista{border-right:1px solid var(--bd);overflow:auto;padding:10px}
#lista input{width:100%;padding:7px 9px;border:1px solid var(--bd);border-radius:6px;background:var(--bg);color:var(--fg);margin-bottom:8px;font:inherit}
.it{padding:7px 9px;border-radius:6px;cursor:pointer}.it:hover,.it.on{background:var(--sf)}.it.on{outline:1px solid var(--ac)}
.it small{color:var(--mut);display:block}
#det{overflow:auto;padding:16px 24px}#det h2{margin:0 0 2px}
.uri{color:var(--mut);font-size:12px;word-break:break-all;margin-bottom:12px}
.cp{display:grid;grid-template-columns:200px 1fr;gap:2px 16px;padding:8px 0;border-top:1px solid var(--bd)}
.cp .k{font-weight:600}.cp .k small{display:block;font-weight:400;color:var(--mut);font-family:ui-monospace,monospace;font-size:11px}
.cp .v{white-space:pre-wrap;word-break:break-word}
a{color:var(--ac)}
table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:6px 10px;border-bottom:1px solid var(--bd);font-size:13px}
th{position:sticky;top:0;background:var(--sf)}td.m{font-family:ui-monospace,monospace;font-size:11px;color:var(--mut)}
.sim{color:var(--ok);font-weight:600}.nao{color:var(--no);font-weight:600}
.box{padding:16px 24px;overflow:auto;height:calc(100vh - 112px)}
pre{background:var(--sf);border:1px solid var(--bd);border-radius:6px;padding:12px;overflow:auto;font-size:12px;white-space:pre-wrap}
@media(max-width:760px){#itens.on{grid-template-columns:1fr;height:auto}.cp{grid-template-columns:1fr}}
</style></head><body>
<header><h1>Acervo FACOM em RDF</h1><p id="res"></p></header>
<nav><button class="on" data-p="itens">Itens</button><button data-p="cols">Colunas do CSV</button><button data-p="ttl">Turtle (.ttl)</button></nav>
<section id="itens" class="pg on"><div id="lista"><input id="q" placeholder="Buscar item ou texto…"><div id="li"></div></div><div id="det"></div></section>
<section id="cols" class="pg"><div class="box"><p>Cada coluna do CSV do Tainacan: se virou RDF, para qual propriedade e em quantos itens veio preenchida.</p><table id="tb"></table></div></section>
<section id="ttl" class="pg"><div class="box"><p>O mesmo conteúdo em Turtle (primeiros 6000 caracteres).</p><pre id="pre"></pre></div></section>
<script>
const ITENS=__ITENS__, COLS=__COLS__, TTL=__TTL__;
const $=s=>document.querySelector(s), esc=t=>t.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const pub=COLS.filter(c=>c.publicar==='sim').length;
$('#res').textContent=`${ITENS.length} itens · ${pub} de ${COLS.length} colunas publicadas como RDF`;
document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>{document.querySelectorAll('nav button,.pg').forEach(e=>e.classList.remove('on'));b.classList.add('on');$('#'+b.dataset.p).classList.add('on')});
function lista(){const q=$('#q').value.toLowerCase();$('#li').innerHTML=ITENS.map((it,i)=>[it,i]).filter(([it])=>!q||JSON.stringify(it).toLowerCase().includes(q)).map(([it,i])=>`<div class="it" data-i="${i}">${esc(it.titulo)}<small>${it.n} campos</small></div>`).join('');
document.querySelectorAll('.it').forEach(e=>e.onclick=()=>mostra(+e.dataset.i))}
function mostra(i){const it=ITENS[i];document.querySelectorAll('.it').forEach(e=>e.classList.toggle('on',+e.dataset.i===i));
$('#det').innerHTML=`<h2>${esc(it.titulo)}</h2><div class="uri">${esc(it.uri)}</div>`+it.campos.map(c=>`<div class="cp"><div class="k">${esc(c.coluna)}<small>${esc(c.pred)}</small></div><div class="v">${c.valor.link?`<a href="${esc(c.valor.link)}" target="_blank">${esc(c.valor.texto)}</a>`:esc(c.valor.texto)}</div></div>`).join('')}
$('#q').oninput=lista;lista();mostra(0);
$('#tb').innerHTML='<tr><th>Coluna do Tainacan</th><th>Virou RDF?</th><th>Propriedade RDF</th><th>Preenchida em</th></tr>'+COLS.map(c=>`<tr><td>${esc(c.coluna_tainacan)}</td><td class="${c.publicar==='sim'?'sim':'nao'}">${c.publicar==='sim'?'sim':'não (interna)'}</td><td class="m">${c.publicar==='sim'?esc(c.propriedade_rdf):'—'}</td><td>${c.itens_preenchidos} de ${ITENS.length}</td></tr>`).join('');
$('#pre').textContent=TTL.slice(0,6000)+(TTL.length>6000?'\\n…':'');
</script></body></html>"""
html = (HTML.replace("__ITENS__", json.dumps(itens, ensure_ascii=False))
            .replace("__COLS__", json.dumps(colunas, ensure_ascii=False))
            .replace("__TTL__", json.dumps(TTL.read_text(encoding="utf-8"), ensure_ascii=False)))
SAIDA.write_text(html, encoding="utf-8")
print(f"{len(itens)} itens -> {SAIDA}")
