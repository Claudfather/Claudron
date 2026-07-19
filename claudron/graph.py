"""Knowledge-graph export — the vault's wikilink graph as data or a visual.

The showcase on top of the graph slice (E4's scale-free half): ``build_edges``
already computes every note↔note wikilink edge, so this is a thin serialization
+ render layer. ``build_graph`` emits ``{nodes, edges}`` any tool can consume;
``render_html`` wraps it in a **self-contained, dependency-free** interactive
force-directed page (no CDN, no Obsidian, opens in any browser offline).

Nodes carry the **maturity** trust axis (E5), so the graph is *curation-aware* —
canonical/verified/draft are colored, and unresolved ``[[links]]`` render as
faded ghost nodes (wanted-but-unwritten knowledge), the way Obsidian shows them.
It is a demo of the brain, not the brain — the moat is the governed memory
underneath, not the picture.
"""

from __future__ import annotations

import json
from collections import Counter

from .knowledge import build_edges
from .vault import Vault


def build_graph(vault: Vault) -> dict:
    """The vault's wikilink graph as ``{nodes, edges}``.

    A node per indexed note (``id`` = vault-relative path, plus ``label``,
    ``tier``, ``maturity``, ``deg``), plus a **ghost** node per unresolved
    ``[[target]]`` (a wanted-but-unwritten note). An edge per wikilink,
    ``{source, target}`` over node ids.
    """
    edges_raw, entries = build_edges(vault)
    in_deg: Counter = Counter()
    out_deg: Counter = Counter()
    links: list[dict] = []
    ghosts: dict[str, str] = {}  # ghost id → display text

    for src, target, dst in edges_raw:
        if dst is not None:
            links.append({"source": src, "target": dst})
            out_deg[src] += 1
            in_deg[dst] += 1
        else:
            gid = "?" + target.lower()  # unresolved → a wanted-but-unwritten note
            ghosts[gid] = target
            links.append({"source": src, "target": gid})
            out_deg[src] += 1
            in_deg[gid] += 1

    nodes: list[dict] = []
    for e in entries:
        p = str(e.get("path", ""))
        if not p:
            continue
        nodes.append({
            "id": p,
            "label": e.get("title") or p,
            "tier": (str(e.get("tier") or "").split(":", 1)[0]) or "shared",
            "maturity": e.get("maturity") or "unrated",
            "deg": in_deg[p] + out_deg[p],
            "ghost": False,
        })
    for gid, text in ghosts.items():
        nodes.append({
            "id": gid, "label": text, "tier": "", "maturity": "",
            "deg": in_deg[gid], "ghost": True,
        })

    return {"nodes": nodes, "edges": links}


def render_html(graph: dict, *, title: str = "Claudron knowledge graph") -> str:
    """A self-contained interactive force-directed page for *graph*.

    Zero dependencies — the physics + rendering are inline vanilla JS on a
    canvas, the data is embedded, no external fetch — so the file works offline
    in any browser. All-pairs repulsion is O(n²)/frame: fine to a few hundred
    notes (a personal vault); larger graphs want a spatial index (deferred with
    the SQLite tier)."""
    data = json.dumps(graph, separators=(",", ":"))
    return (
        _HTML_TEMPLATE
        .replace("__TITLE__", _escape(title))
        .replace("__DATA__", data)
    )


def _escape(s: str) -> str:
    return (
        s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# Placeholders (__TITLE__, __DATA__) are string-replaced, not f-string/format,
# so the CSS/JS braces below need no escaping.
_HTML_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<style>
  html,body{margin:0;height:100%;background:#12151c;color:#c9d1d9;
    font:13px/1.4 -apple-system,Segoe UI,Roboto,sans-serif;overflow:hidden}
  #c{display:block;width:100vw;height:100vh;cursor:grab}
  #hud{position:fixed;top:12px;left:14px;pointer-events:none}
  #hud h1{margin:0 0 6px;font-size:15px;font-weight:600}
  #legend{position:fixed;bottom:14px;left:14px;font-size:12px}
  #legend div{margin:2px 0}
  .dot{display:inline-block;width:9px;height:9px;border-radius:50%;
    margin-right:6px;vertical-align:middle}
  #tip{position:fixed;padding:3px 7px;background:#000a;border:1px solid #333;
    border-radius:4px;font-size:12px;pointer-events:none;display:none;max-width:40ch}
  #stats{position:fixed;top:12px;right:14px;text-align:right;color:#8b949e;font-size:12px}
</style></head><body>
<canvas id="c"></canvas>
<div id="hud"><h1>__TITLE__</h1><div id="sub" style="color:#8b949e"></div></div>
<div id="stats"></div>
<div id="legend">
  <div><span class="dot" style="background:#f5c518"></span>canonical</div>
  <div><span class="dot" style="background:#4caf50"></span>verified</div>
  <div><span class="dot" style="background:#7e8aa2"></span>draft</div>
  <div><span class="dot" style="background:#4a5163"></span>unrated</div>
  <div><span class="dot" style="border:1px dashed #6b7280;background:transparent"></span>unwritten (broken link)</div>
</div>
<div id="tip"></div>
<script>
const DATA = __DATA__;
const COLOR = {canonical:"#f5c518",verified:"#4caf50",draft:"#7e8aa2",unrated:"#4a5163"};
const cv = document.getElementById("c"), ctx = cv.getContext("2d");
const tip = document.getElementById("tip");
let W, H, DPR = window.devicePixelRatio || 1;
function resize(){ W=cv.clientWidth; H=cv.clientHeight; cv.width=W*DPR; cv.height=H*DPR; ctx.setTransform(DPR,0,0,DPR,0,0); }
window.addEventListener("resize", resize); resize();

const nodes = DATA.nodes.map(n => ({...n, x:W/2+(Math.random()-.5)*300, y:H/2+(Math.random()-.5)*300, vx:0, vy:0}));
const idx = new Map(nodes.map((n,i)=>[n.id,i]));
const edges = DATA.edges.map(e=>({s:idx.get(e.source), t:idx.get(e.target)})).filter(e=>e.s!=null&&e.t!=null);
document.getElementById("sub").textContent = nodes.length+" notes";
const broken = nodes.filter(n=>n.ghost).length;
const canon = nodes.filter(n=>n.maturity==="canonical").length;
document.getElementById("stats").textContent = canon+" canonical · "+edges.length+" links · "+broken+" unwritten";

// camera + interaction state (declared before the sim loop reads drag/hover)
let ox=0, oy=0, zoom=1;
let drag=null, hover=null, panning=false, px=0, py=0;
function radius(n){ return (n.ghost?3:4) + Math.min(n.deg,12)*1.1; }

// force sim (all-pairs repulsion + edge springs + gravity)
function step(){
  for(const n of nodes){ n.vx*=0.86; n.vy*=0.86; }
  for(let i=0;i<nodes.length;i++){
    const a=nodes[i];
    for(let j=i+1;j<nodes.length;j++){
      const b=nodes[j];
      let dx=a.x-b.x, dy=a.y-b.y, d2=dx*dx+dy*dy+0.01;
      const f=1400/d2, d=Math.sqrt(d2);
      dx/=d; dy/=d; a.vx+=dx*f; a.vy+=dy*f; b.vx-=dx*f; b.vy-=dy*f;
    }
    a.vx += (W/2-a.x)*0.002; a.vy += (H/2-a.y)*0.002;   // gravity to center
  }
  for(const e of edges){
    const a=nodes[e.s], b=nodes[e.t];
    let dx=b.x-a.x, dy=b.y-a.y, d=Math.sqrt(dx*dx+dy*dy)+0.01;
    const f=(d-80)*0.01; dx/=d; dy/=d;
    a.vx+=dx*f; a.vy+=dy*f; b.vx-=dx*f; b.vy-=dy*f;
  }
  for(const n of nodes){ if(n!==drag){ n.x+=n.vx; n.y+=n.vy; } }
}
function toScreen(n){ return [n.x*zoom+ox, n.y*zoom+oy]; }

function draw(){
  ctx.clearRect(0,0,W,H);
  ctx.lineWidth=1;
  for(const e of edges){
    const a=nodes[e.s], b=nodes[e.t], [ax,ay]=toScreen(a), [bx,by]=toScreen(b);
    ctx.strokeStyle = b.ghost ? "#2b3140" : "#39404f";
    if(b.ghost){ ctx.setLineDash([3,3]); } else { ctx.setLineDash([]); }
    ctx.beginPath(); ctx.moveTo(ax,ay); ctx.lineTo(bx,by); ctx.stroke();
  }
  ctx.setLineDash([]);
  for(const n of nodes){
    const [x,y]=toScreen(n), r=radius(n)*zoom;
    ctx.beginPath(); ctx.arc(x,y,r,0,7);
    if(n.ghost){ ctx.fillStyle="transparent"; ctx.strokeStyle="#6b7280";
      ctx.setLineDash([2,2]); ctx.stroke(); ctx.setLineDash([]); }
    else { ctx.fillStyle=COLOR[n.maturity]||COLOR.unrated; ctx.fill(); }
    if(n.deg>=6 || n===hover){
      ctx.fillStyle="#c9d1d9"; ctx.font="11px sans-serif";
      ctx.fillText(n.label, x+r+3, y+4);
    }
  }
}
function frame(){ step(); draw(); requestAnimationFrame(frame); }
frame();

// interaction: pan, zoom, drag nodes, hover tooltip (state hoisted above)
function pick(mx,my){
  for(let i=nodes.length-1;i>=0;i--){
    const [x,y]=toScreen(nodes[i]); const r=radius(nodes[i])*zoom+2;
    if((mx-x)**2+(my-y)**2<=r*r) return nodes[i];
  }
  return null;
}
cv.addEventListener("mousedown", ev=>{
  const n=pick(ev.clientX,ev.clientY);
  if(n){ drag=n; } else { panning=true; px=ev.clientX; py=ev.clientY; cv.style.cursor="grabbing"; }
});
window.addEventListener("mousemove", ev=>{
  if(drag){ drag.x=(ev.clientX-ox)/zoom; drag.y=(ev.clientY-oy)/zoom; drag.vx=drag.vy=0; }
  else if(panning){ ox+=ev.clientX-px; oy+=ev.clientY-py; px=ev.clientX; py=ev.clientY; }
  else {
    hover=pick(ev.clientX,ev.clientY);
    if(hover){ tip.style.display="block"; tip.style.left=(ev.clientX+12)+"px";
      tip.style.top=(ev.clientY+12)+"px";
      tip.textContent = hover.ghost ? hover.label+" — unwritten" :
        hover.label+"  ("+(hover.maturity)+", "+hover.tier+")"; }
    else tip.style.display="none";
  }
});
window.addEventListener("mouseup", ()=>{ drag=null; panning=false; cv.style.cursor="grab"; });
cv.addEventListener("wheel", ev=>{ ev.preventDefault();
  const f=ev.deltaY<0?1.1:0.9; const mx=ev.clientX, my=ev.clientY;
  ox=mx-(mx-ox)*f; oy=my-(my-oy)*f; zoom*=f;
}, {passive:false});
</script></body></html>
"""
