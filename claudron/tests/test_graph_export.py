"""Tests for the knowledge-graph export (`claudron graph`)."""

from __future__ import annotations

import json
from pathlib import Path

from claudron.cli import main
from claudron.graph import build_graph, render_html
from claudron.vault import detect


def _note(vault: Path, fn: str, title: str, body: str) -> None:
    d = vault / "_shared" / "knowledge"
    d.mkdir(parents=True, exist_ok=True)
    (d / fn).write_text(
        f"---\ntitle: {title}\ntype: knowledge\nstatus: current\nowner: t\n"
        f"created: 2026-01-01\nupdated: 2026-01-01\n---\n\n# {title}\n\n{body}\n"
    )


def _graph_vault(tmp_path: Path) -> Path:
    v = tmp_path / "v"
    (v / "_shared" / "knowledge").mkdir(parents=True)
    _note(v, "a.md", "Note A", "links to [[Note B]] and [[Missing Thing]]")
    _note(v, "b.md", "Note B", "plain leaf")
    return v


class TestBuildGraph:
    def test_nodes_and_edges(self, tmp_path: Path):
        g = build_graph(detect(_graph_vault(tmp_path)))
        ids = {n["id"] for n in g["nodes"]}
        assert "_shared/knowledge/a.md" in ids
        assert "_shared/knowledge/b.md" in ids
        # a resolved edge A → B
        assert {"source": "_shared/knowledge/a.md",
                "target": "_shared/knowledge/b.md"} in g["edges"]

    def test_unresolved_link_becomes_a_ghost_node(self, tmp_path: Path):
        g = build_graph(detect(_graph_vault(tmp_path)))
        ghosts = [n for n in g["nodes"] if n["ghost"]]
        assert any(n["label"] == "Missing Thing" for n in ghosts)
        # and an edge points at the ghost
        ghost_id = next(n["id"] for n in ghosts if n["label"] == "Missing Thing")
        assert any(e["target"] == ghost_id for e in g["edges"])

    def test_nodes_carry_maturity(self, tmp_path: Path):
        v = _graph_vault(tmp_path)
        vault = detect(v)
        from claudron.promote import promote
        promote(vault, v / "_shared" / "knowledge" / "b.md",
                to_maturity="canonical", actor="t")
        g = build_graph(detect(v))
        b = next(n for n in g["nodes"] if n["id"] == "_shared/knowledge/b.md")
        assert b["maturity"] == "canonical"


class TestRenderHtml:
    def test_html_is_self_contained_and_embeds_data(self, tmp_path: Path):
        g = build_graph(detect(_graph_vault(tmp_path)))
        html = render_html(g, title="My Vault")
        assert html.lstrip().startswith("<!doctype html>")
        assert "My Vault" in html
        # data embedded, no external fetch/CDN
        assert "const DATA =" in html
        assert "http://" not in html and "https://" not in html
        assert "src=" not in html  # no external scripts

    def test_title_is_escaped(self, tmp_path: Path):
        g = {"nodes": [], "edges": []}
        html = render_html(g, title="<script>x</script>")
        assert "<script>x</script>" not in html.split("const DATA")[0]
        assert "&lt;script&gt;" in html

    def test_embedded_js_actually_runs(self, tmp_path: Path):
        """Regression guard: the rendered JS must EXECUTE, not just parse. A
        `let drag`-after-use TDZ error once threw on frame 1 and blanked the
        canvas while every structural test stayed green — this runs the script
        under a canvas/DOM stub in node and asserts it initializes + steps
        frames without throwing. Skips where node is unavailable."""
        import re
        import shutil
        import subprocess

        node = shutil.which("node")
        if node is None:
            import pytest
            pytest.skip("node not available")

        html = render_html(build_graph(detect(_graph_vault(tmp_path))))
        js = re.search(r"<script>(.*?)</script>", html, re.DOTALL).group(1)
        js_file = tmp_path / "graph.js"
        js_file.write_text(js)
        harness = tmp_path / "harness.js"
        harness.write_text(
            "const noop=()=>{};"
            "const ctx=new Proxy({},{get:(t,p)=>p==='measureText'?(()=>({width:10})):noop});"
            "const el={c:{getContext:()=>ctx,clientWidth:800,clientHeight:600,width:0,height:0,"
            "addEventListener:noop,style:{}}};"
            "let f=0;"
            "global.document={getElementById:id=>el[id]||{textContent:'',style:{},addEventListener:noop},addEventListener:noop};"
            "global.window={devicePixelRatio:1,addEventListener:noop};"
            "global.requestAnimationFrame=fn=>{if(f++<2)fn();};"
            "global.cancelAnimationFrame=noop;"
            "eval(require('fs').readFileSync(process.argv[2],'utf8'));"
        )
        r = subprocess.run(
            [node, str(harness), str(js_file)], capture_output=True, text=True, timeout=20
        )
        assert r.returncode == 0, f"graph JS threw at runtime: {r.stderr.strip()}"


class TestGraphCLI:
    def test_json_output(self, tmp_path: Path, capsys):
        rc = main(["--vault", str(_graph_vault(tmp_path)), "graph", "--json"])
        assert rc == 0
        env = json.loads(capsys.readouterr().out)
        assert env["command"] == "graph"
        assert env["data"]["nodes"] and env["data"]["edges"]

    def test_writes_html_file(self, tmp_path: Path, capsys):
        v = _graph_vault(tmp_path)
        out = tmp_path / "graph.html"
        rc = main(["--vault", str(v), "graph", "-o", str(out)])
        assert rc == 0
        assert out.is_file()
        assert out.read_text().lstrip().startswith("<!doctype html>")
        assert "wrote" in capsys.readouterr().out

    def test_default_output_path(self, tmp_path: Path):
        v = _graph_vault(tmp_path)
        main(["--vault", str(v), "graph"])
        assert (v / ".claudron" / "graph.html").is_file()
