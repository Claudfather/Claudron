"""The tag registry (#200 §3): _shared/TAGS.yaml names the canonical tags; capture writes them.

The contract: tags stay open (a note may carry any tag); the registry's
closed facets decide which tags it can name; an alias or a deprecated tag
resolves to its canonical form, and the write door stores that form; usage is
derived from the index, never stored; a malformed registry is reported, not
fatal.
"""

from __future__ import annotations

import json

from claudron import tags
from claudron.cli import main
from claudron.vault import detect

REGISTRY = """\
version: 1
facets: [domain, tech, repo, fleet, team]
tags:
  tech:python:
    description: The Python language
    aliases: [lang:python, py]
  tech:py2:
    status: deprecated
    merged_into: tech:python
  domain:billing: {}
"""


def _registry(vault_dir, text=REGISTRY):
    (vault_dir / "_shared" / tags.REGISTRY).write_text(text)
    return detect(vault_dir)


def test_an_alias_and_a_merged_tag_resolve_to_the_canonical_tag(vault_dir):
    reg = tags.load(_registry(vault_dir))
    assert reg.problems == []
    assert [reg.canonical(t) for t in ("py", "LANG:PYTHON", "tech:py2", "tech:python", "env:staging")] == [
        "tech:python", "tech:python", "tech:python", "tech:python", "env:staging"]


def test_capture_writes_canonical_tags(vault_dir, capsys):
    _registry(vault_dir)
    main(["--vault", str(vault_dir), "capture", "--type", "knowledge", "--title", "Packaging", "--body", "Use uv.",
          "--tags", "py,tech:py2,env:staging", "--owner", "t", "--json"])
    path = json.loads(capsys.readouterr().out)["data"]["path"]
    text = open(path).read()
    assert "tech:python" in text and "tech:py2" not in text and " py" not in text and "env:staging" in text


def test_no_registry_changes_nothing(vault_dir):
    assert tags.canonicalize(detect(vault_dir), ["py", "tech:py2"]) == ["py", "tech:py2"]


def test_the_report_counts_usage_from_the_index_and_lists_what_it_doesnt_cover(vault_dir, capsys):
    vault = _registry(vault_dir)
    data = tags.report(vault, {"tech:python": 3, "tech:rust": 2, "py": 1, "env:staging": 4})
    assert {t["name"]: t["count"] for t in data["tags"]}["tech:python"] == 3
    assert data["unregistered"] == [{"tag": "tech:rust", "count": 2}]
    assert data["noncanonical_in_use"] == [{"tag": "py", "count": 1, "canonical": "tech:python"}]
    assert data["other"] == 2  # env:staging and py: no registered facet


def test_a_malformed_registry_is_reported_not_fatal(vault_dir):
    reg = tags.load(_registry(vault_dir, """\
facets: [tech, colour]
tags:
  python: {}
  tech:a: {status: deprecated}
  tech:b: {merged_into: tech:c, status: deprecated}
  tech:c: {merged_into: tech:b, status: deprecated, aliases: [x]}
  tech:d: {aliases: [x, yes], status: maybe}
  tech:e: {merged_into: tech:d}
  TECH:D: {}
"""))
    joined = " | ".join(reg.problems)
    for expected in ("colour", "python: not `facet:value`", "tech:a: deprecated without", "loops back",
                     "alias 'x' is already an alias of tech:c", "status 'maybe'", "True is not a string",
                     "tech:e: `merged_into` on a tag that isn't deprecated", "TECH:D: the same tag as tech:d"):
        assert expected in joined, expected
    assert tags.load(_registry(vault_dir, "tags: [1, 2\n")).problems[0].startswith("unreadable")


def test_the_cli_reports_and_resolves(vault_dir, capsys):
    _registry(vault_dir)
    main(["--vault", str(vault_dir), "capture", "--type", "knowledge", "--title", "Rust", "--body", "Borrowck.",
          "--tags", "tech:rust", "--owner", "t"])
    capsys.readouterr()
    assert main(["--vault", str(vault_dir), "tags", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)["data"]
    assert data["registry"] == "_shared/TAGS.yaml" and data["unregistered"] == [{"tag": "tech:rust", "count": 1}]
    assert main(["--vault", str(vault_dir), "tags", "--resolve", "py", "tech:rust", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["data"]["resolved"] == {"py": "tech:python", "tech:rust": "tech:rust"}


def test_the_registry_is_never_a_note(vault_dir, capsys):
    _registry(vault_dir)
    main(["--vault", str(vault_dir), "lookup", "python", "--json"])
    assert all(not r["path"].endswith(tags.REGISTRY) for r in json.loads(capsys.readouterr().out)["data"]["results"])


def test_tags_are_case_insensitive_and_a_registered_tag_is_never_taken_by_an_alias(vault_dir):
    reg = tags.load(_registry(vault_dir, REGISTRY + "  tech:ruby: {}\n  tech:go: {aliases: [TECH:RUBY]}\n"))
    assert "alias 'TECH:RUBY' is the registered tag tech:ruby" in " | ".join(reg.problems)
    assert reg.canonical("tech:ruby") == "tech:ruby" and reg.canonical("TECH:Python") == "tech:python"
    assert tags.canonicalize(detect(vault_dir), ["tech:PYTHON", "tech:python", " py "]) == ["tech:python"]


def test_a_merged_into_on_an_active_tag_redirects_nothing(vault_dir):
    reg = tags.load(_registry(vault_dir, REGISTRY + "  tech:a: {merged_into: tech:python}\n"))
    assert reg.canonical("tech:a") == "tech:a"


def test_stdin_tags_are_stripped_before_they_resolve(vault_dir, capsys, monkeypatch):
    import io

    _registry(vault_dir)
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(
        {"type": "knowledge", "title": "Strip", "body": "x.", "tags": ["py ", " tech:py2"], "owner": "t"})))
    main(["--vault", str(vault_dir), "capture", "--stdin", "--json"])
    text = open(json.loads(capsys.readouterr().out)["data"]["path"]).read()
    assert '"tech:python"' in text and '"py"' not in text and "py2" not in text


def test_new_writes_canonical_tags_too(vault_dir, capsys):
    _registry(vault_dir)
    main(["--vault", str(vault_dir), "new", "knowledge", "Fresh note", "--tags", "py", "--json"])
    text = open(json.loads(capsys.readouterr().out)["data"]["path"]).read()
    assert "tech:python" in text and '"py"' not in text


def test_a_case_variant_in_use_is_reported_as_noncanonical(vault_dir):
    data = tags.report(_registry(vault_dir), {"tech:PYTHON": 2})
    assert data["unregistered"] == [] and data["noncanonical_in_use"] == [
        {"tag": "tech:PYTHON", "count": 2, "canonical": "tech:python"}]


def test_a_merge_target_in_another_case_is_the_registered_spelling(vault_dir):
    reg = tags.load(_registry(vault_dir, REGISTRY.replace("merged_into: tech:python", "merged_into: Tech:Python")))
    assert reg.problems == [] and reg.canonical("tech:py2") == "tech:python"
    assert tags.canonicalize(detect(vault_dir), ["tech:py2", "py"]) == ["tech:python"]


def test_scalar_aliases_bad_entries_and_empty_values_are_reported(vault_dir):
    reg = tags.load(_registry(vault_dir, "tags:\n  tech:a: {aliases: yes}\n  tech:b: just text\n  tech: {}\n"))
    joined = " | ".join(reg.problems)
    for expected in ("alias True is not a string", "tech:b: its entry is not a mapping", "tech: not `facet:value`"):
        assert expected in joined, expected


def test_empty_tags_never_land(vault_dir):
    assert tags.canonicalize(_registry(vault_dir), ["", " ", "py"]) == ["tech:python"]
    assert tags.canonicalize(detect(vault_dir), ["", "x"]) == ["x"]
