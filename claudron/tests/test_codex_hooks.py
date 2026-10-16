"""Measured Codex lifecycle shape and the engine's compact-delivery correction."""
from __future__ import annotations

import io
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from claudron import CAPABILITIES, hooks, doctor
from claudron.cli import main
from claudron.tests.doc_parity import fenced_block
from claudron.vault import detect


@pytest.mark.parametrize('agent_cli', ['claude', 'codex'])
def test_compact_stdout_once_per_session_and_precompact_is_noninjecting(vault_dir, monkeypatch, capsys, agent_cli):
    monkeypatch.setattr(hooks, 'session_start_brief', lambda *_: 'Recall stays first.')
    monkeypatch.setattr(hooks.tempfile, 'gettempdir', lambda: str(vault_dir.parent))
    args = ['--vault', str(vault_dir), '--agent-cli', agent_cli, 'hook']
    payload = {'session_id': 'example-session', 'source': 'compact'}
    monkeypatch.setattr('sys.stdin', io.StringIO(json.dumps(payload)))
    assert main(args + ['pre-compact']) == 0
    assert capsys.readouterr().out == ''
    monkeypatch.setattr('sys.stdin', io.StringIO(json.dumps(payload)))
    assert main(args + ['session-start']) == 0
    out = capsys.readouterr().out
    assert out.startswith('Recall stays first.\n')
    assert 'claudron capture --stdin' in out
    assert 'after compaction' in out.lower()
    assert 'claudna' not in out.lower()
    monkeypatch.setattr('sys.stdin', io.StringIO(json.dumps(payload)))
    assert main(args + ['session-start']) == 0
    assert capsys.readouterr().out == 'Recall stays first.\n'


@pytest.mark.parametrize('source', ['startup', 'resume', 'clear', None, '', 'unknown'])
def test_other_start_sources_do_not_prompt(vault_dir, monkeypatch, capsys, source):
    monkeypatch.setattr(hooks, 'session_start_brief', lambda *_: '')
    monkeypatch.setattr('sys.stdin', io.StringIO(json.dumps({'source': source, 'session_id': 's'})))
    assert main(['--vault', str(vault_dir), 'hook', 'session-start']) == 0
    assert capsys.readouterr().out == ''


@pytest.mark.parametrize('session_id', [None, '', '../escape', '/absolute', ['s'], 1, 'x' * 129])
def test_invalid_session_id_never_creates_marker_or_capture(vault_dir, monkeypatch, capsys, session_id):
    monkeypatch.setattr(hooks, 'session_start_brief', lambda *_: '')
    monkeypatch.setattr(hooks.tempfile, 'gettempdir', lambda: str(vault_dir.parent))
    monkeypatch.setattr('sys.stdin', io.StringIO(json.dumps({'source': 'compact', 'session_id': session_id})))
    assert main(['--vault', str(vault_dir), 'hook', 'session-start']) == 0
    assert capsys.readouterr().out == ''
    assert not list(vault_dir.parent.glob('claudron-capture-*'))


def test_claim_is_atomic_and_namespaced(vault_dir, tmp_path, monkeypatch):
    monkeypatch.setattr(hooks.tempfile, 'gettempdir', lambda: str(tmp_path))
    vault = detect(vault_dir)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: hooks.capture_prompt(vault, {'source': 'compact', 'session_id': 's'}, 'codex'), range(16)))
    assert sum(bool(s) for s in results) == 1
    assert hooks.capture_prompt(vault, {'source': 'compact', 'session_id': 's'}, 'claude')
    other = type(vault)(**{**vault.__dict__, 'root': tmp_path / 'other'})
    assert hooks.capture_prompt(other, {'source': 'compact', 'session_id': 's'}, 'codex')
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in tmp_path.glob('claudron-capture-*'))


def test_marker_failure_preserves_brief_without_prompt(vault_dir, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(hooks, 'session_start_brief', lambda *_: 'Brief')
    monkeypatch.setattr(hooks.tempfile, 'gettempdir', lambda: str(tmp_path / 'absent'))
    monkeypatch.setattr('sys.stdin', io.StringIO('{"source":"compact","session_id":"s"}'))
    assert main(['--vault', str(vault_dir), 'hook', 'session-start']) == 0
    assert capsys.readouterr().out == 'Brief\n'


@pytest.mark.parametrize('wire', ['[]', 'null', '"text"', '{'])
def test_malformed_hook_input_fails_open(vault_dir, monkeypatch, capsys, wire):
    monkeypatch.setattr(hooks, 'session_start_brief', lambda *_: 'Must not inject for malformed input')
    monkeypatch.setattr('sys.stdin', io.StringIO(wire))
    assert main(['--vault', str(vault_dir), 'hook', 'session-start']) == 0
    assert capsys.readouterr().out == ''


def test_codex_install_preserves_foreign_hooks_and_replaces_old_install(vault_dir, tmp_path, monkeypatch, capsys):
    codex_home = tmp_path / 'codex-home'
    codex_home.mkdir()
    monkeypatch.setenv('CODEX_HOME', str(codex_home))
    foreign = {'matcher': '', 'hooks': [{'type': 'command', 'command': 'foreign-command'}]}
    path = codex_home / 'hooks.json'
    path.write_text(json.dumps({'kept': True, 'hooks': {'SessionStart': [foreign]}}))
    args = ['--vault', str(vault_dir), 'hooks', 'install', '--agent-cli', 'codex', '--write']
    assert main(args) == 0
    installed = json.loads(path.read_text())
    assert installed['kept'] is True
    assert installed['hooks']['SessionStart'][0] == foreign
    assert len(installed['hooks']['SessionStart']) == 2
    assert installed['hooks']['SessionEnd'][0]['hooks'][0]['timeout'] > hooks.SESSION_END_PUSH_TIMEOUT
    assert main(args) == 0
    assert json.loads(path.read_text()) == installed
    assert 'already installed' in capsys.readouterr().err
    assert not (Path.home() / '.claude/settings.json').exists()


def test_codex_default_and_normative_parity(tmp_path, monkeypatch):
    monkeypatch.delenv('CODEX_HOME', raising=False)
    assert hooks.default_settings_path('codex') == Path.home() / '.codex/hooks.json'
    monkeypatch.setenv('CODEX_HOME', str(tmp_path))
    assert hooks.default_settings_path('codex') == tmp_path / 'hooks.json'
    text = fenced_block('docs/CLI_CONTRACT.md', 'Codex session-loop snippet')
    body = text.split('\n', 1)[1] if text.lstrip().startswith('json') else text
    rendered = json.dumps(hooks.settings_snippet('/EXE', '/VAULT', agent_cli='codex'))
    rendered = rendered.replace('/EXE', '<absolute-executable>').replace('/VAULT', '<absolute-vault-root>')
    assert json.loads(body) == json.loads(rendered)
    assert 'codex-session-loop' in CAPABILITIES


def test_doctor_codex_uses_selected_shape_and_gives_selected_remedy(vault_dir, tmp_path, capsys):
    path = tmp_path / 'hooks.json'
    snippet = hooks.settings_snippet('/bin/sh', str(vault_dir), agent_cli='codex')
    path.write_text(json.dumps(snippet))
    report = doctor.diagnose(detect(vault_dir), settings=[path], agent_cli='codex')
    assert not [f for f in report.findings if f.code in ('D009', 'D010')]
    snippet['hooks']['SessionEnd'][0]['hooks'][0].pop('timeout')
    path.write_text(json.dumps(snippet))
    assert main(['--vault', str(vault_dir), 'doctor', '--agent-cli', 'codex', '--settings', str(path), '--json']) == 0
    data = json.loads(capsys.readouterr().out)['data']
    assert data['hooks'][0]['state'] == 'ok'
    report = doctor.diagnose(detect(vault_dir), settings=[path], agent_cli='codex')
    drift = [f for f in report.findings if f.code == 'D009']
    assert len(drift) == 1
    assert '--agent-cli codex' in drift[0].message


@pytest.mark.parametrize('data', ['[]', '{"hooks":[]}', '{"hooks":{"SessionStart":[]},"kept":true}'])
def test_codex_malformed_settings_refused_or_empty_event_repaired(vault_dir, tmp_path, capsys, data):
    path = tmp_path / 'hooks.json'
    path.write_text(data)
    rc = main(['--vault', str(vault_dir), 'hooks', 'install', '--agent-cli', 'codex', '--write', '--settings', str(path)])
    if data.startswith('{"hooks":{"SessionStart"'):
        assert rc == 0
        assert json.loads(path.read_text())['kept'] is True
    else:
        assert rc == 3
        assert path.read_text() == data


@pytest.mark.parametrize('path', sorted((Path(__file__).parent / 'fixtures/codex').glob('*-*.json')))
def test_actual_native_lifecycle_fixtures(path, vault_dir, tmp_path, monkeypatch, capsys):
    payload = json.loads(path.read_text())
    monkeypatch.setattr(hooks, 'session_start_brief', lambda *_: 'Recall')
    monkeypatch.setattr(hooks.tempfile, 'gettempdir', lambda: str(tmp_path))
    monkeypatch.setattr(hooks, 'hook_session_end', lambda *_, **__: 0)
    # Use the real recorded key/types through normal CLI dispatch, not fixture-made fields.
    event = hooks.SNIPPET_EVENTS[payload['hook_event_name']]
    monkeypatch.setattr('sys.stdin', io.StringIO(json.dumps(payload)))
    assert main(['--vault', str(vault_dir), '--agent-cli', 'codex', 'hook', event]) == 0
    out = capsys.readouterr().out
    if event == 'session-start':
        assert out.startswith('Recall\n')
        assert ('claudron capture --stdin' in out) == (payload['source'] == 'compact')
    else:
        assert out == ''


def test_codex_doctor_other_vault_remedy_keeps_agent_cli(vault_dir, tmp_path):
    other = tmp_path / 'other-vault'
    (other / '_shared').mkdir(parents=True)
    from claudron.vault import IDENTITY_FILE, identity_text
    (other / IDENTITY_FILE).write_text(identity_text('other', '_shared'))
    path = tmp_path / 'hooks.json'
    path.write_text(json.dumps(hooks.settings_snippet('/bin/sh', str(other), agent_cli='codex')))
    report = doctor.diagnose(detect(vault_dir), settings=[path], agent_cli='codex')
    findings = [f for f in report.findings if f.code == 'D010']
    assert len(findings) == 3
    assert all('--agent-cli codex' in f.message for f in findings)
