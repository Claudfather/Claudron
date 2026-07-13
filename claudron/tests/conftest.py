"""Fixture vaults for claudron tests."""

from __future__ import annotations

import shutil
from pathlib import Path
from textwrap import dedent

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def reference_vault(tmp_path: Path) -> Path:
    """Writable copy of the shipped exemplar vault (examples/reference-vault)."""
    dest = tmp_path / "reference-vault"
    shutil.copytree(REPO_ROOT / "examples" / "reference-vault", dest)
    return dest


@pytest.fixture
def vault_dir(tmp_path: Path) -> Path:
    """Minimal vault with _shared/knowledge/ containing one doc."""
    root = tmp_path / "vault"
    (root / "_shared" / "knowledge").mkdir(parents=True)
    (root / "_shared" / "decisions").mkdir(parents=True)
    (root / "_shared" / "runbooks").mkdir(parents=True)
    (root / "projects").mkdir()

    (root / "_shared" / "knowledge" / "auth-patterns.md").write_text(
        dedent("""\
        ---
        title: Auth Patterns Across Services
        type: knowledge
        status: current
        owner: mason
        tags: [auth, jwt, architecture]
        created: 2026-04-01
        updated: 2026-05-01
        ---

        # Auth Patterns Across Services

        All services use JWT with RS256. Tokens issued by auth-service,
        validated by middleware in each service.

        ## Token Refresh

        Refresh tokens are stored in httpOnly cookies.
    """)
    )

    (root / "_shared" / "knowledge" / "deploy-checklist.md").write_text(
        dedent("""\
        ---
        title: Deploy Checklist
        type: knowledge
        status: current
        owner: alex
        tags: [deploy, operations]
        created: 2026-03-15
        updated: 2026-04-20
        ---

        # Deploy Checklist

        Before deploying, verify migrations, env vars, and health checks.
    """)
    )

    return root


@pytest.fixture
def vault_with_projects(vault_dir: Path) -> Path:
    """Vault with project-specific knowledge."""
    proj = vault_dir / "projects" / "storydump"
    proj.mkdir(parents=True)
    (proj / "neon-pooling.md").write_text(
        dedent("""\
        ---
        title: Neon Connection Pooling Gotchas
        type: knowledge
        status: current
        owner: alex
        tags: [neon, database, storydump]
        created: 2026-04-10
        updated: 2026-05-05
        ---

        # Neon Connection Pooling Gotchas

        Neon's serverless driver pools differently than pg.
        Connection limits are per-branch, not per-project.
    """)
    )
    return vault_dir


@pytest.fixture
def vault_with_fleet(vault_dir: Path) -> Path:
    """Vault with a fleet overlay containing fleet-scoped knowledge."""
    fleet = vault_dir / "test-fleet"
    fleet.mkdir()
    (fleet / "fleet.yaml").write_text(
        dedent("""\
        fleet:
          name: test-fleet
          service_prefix: com.test
          bots: {}
    """)
    )
    (fleet / "shared" / "knowledge").mkdir(parents=True)
    (fleet / "shared" / "knowledge" / "railway-gotchas.md").write_text(
        dedent("""\
        ---
        title: Railway Deploy Gotchas
        type: knowledge
        status: current
        owner: branden
        tags: [railway, deploy]
        created: 2026-04-15
        updated: 2026-05-10
        ---

        # Railway Deploy Gotchas

        Railway needs RAILWAY_TOKEN set. Watch for cold-start timeouts.
    """)
    )
    return vault_dir


@pytest.fixture
def nested_system_vault(tmp_path: Path) -> Path:
    """Vault with an opt-in ``.claudron-system`` container holding a nested fleet.

    Exercises the P1 nested-tolerant scanner (Claudlobby#602). Layout::

        vault/_shared/knowledge/            — global shared tier (the true root)
        vault/sys1/.claudron-system         — the opt-in marker (empty file)
        vault/sys1/shared/knowledge/        — the system's knowledge bucket
        vault/sys1/fleetA/fleet.yaml        — a fleet nested one level down
        vault/sys1/fleetA/shared/knowledge/ — the nested fleet's knowledge tier
    """
    root = tmp_path / "vault"
    (root / "_shared" / "knowledge").mkdir(parents=True)
    sys1 = root / "sys1"
    (sys1 / "shared" / "knowledge").mkdir(parents=True)
    (sys1 / ".claudron-system").write_text("")  # opt-in marker (empty file)
    fleet = sys1 / "fleetA"
    (fleet / "shared" / "knowledge").mkdir(parents=True)
    (fleet / "fleet.yaml").write_text("fleet: {name: fleetA}")
    return root


@pytest.fixture
def nested_fleet_shadow_vault(tmp_path: Path) -> Path:
    """Vault where a NESTED fleet's bare name collides with an unrelated
    TOP-LEVEL dir — the collateral-shadow regression (Claudlobby#602 review).

    Layout::

        vault/_shared/knowledge/                 — global shared tier (true root)
        vault/experiments/note.md                — a genuine top-level other: dir
        vault/sys1/.claudron-system              — the opt-in system marker
        vault/sys1/experiments/fleet.yaml        — a NESTED fleet, bare name
                                                   `experiments` (collides above)
        vault/sys1/experiments/shared/knowledge/ — the nested fleet's tier

    The nested fleet folds into ``vault.fleets`` under the bare name
    ``experiments``. A *name-based* ``recognized_top_level`` would then shadow
    the unrelated top-level ``experiments/`` out of the ``other:``/S3 hatch —
    silent data loss. Only ONE fleet is named ``experiments``, so this is not an
    F5 global-unique collision: it is pure collateral shadow.
    """
    root = tmp_path / "vault"
    (root / "_shared" / "knowledge").mkdir(parents=True)
    # A genuine top-level `other:` dir carrying a real note.
    exp = root / "experiments"
    exp.mkdir()
    (exp / "note.md").write_text(
        dedent("""\
        ---
        title: Experiment Log
        type: knowledge
        status: current
        owner: c
        created: 2026-05-01
        updated: 2026-05-01
        ---

        # Experiment Log

        Findings from the top-level experiments dir.
    """)
    )
    # System container whose nested fleet's bare name is `experiments`.
    sys1 = root / "sys1"
    (sys1 / "shared" / "knowledge").mkdir(parents=True)
    (sys1 / ".claudron-system").write_text("")  # opt-in marker (empty file)
    nested = sys1 / "experiments"
    (nested / "shared" / "knowledge").mkdir(parents=True)
    (nested / "fleet.yaml").write_text("fleet: {name: experiments}")
    return root


@pytest.fixture
def empty_vault(tmp_path: Path) -> Path:
    """Vault with _shared/ but no docs."""
    root = tmp_path / "empty-vault"
    (root / "_shared" / "knowledge").mkdir(parents=True)
    (root / "_shared" / "decisions").mkdir(parents=True)
    (root / "_shared" / "runbooks").mkdir(parents=True)
    return root


@pytest.fixture
def shared_vault(tmp_path: Path) -> Path:
    """Vault using shared/ (no underscore) as the marker directory."""
    root = tmp_path / "shared-vault"
    (root / "shared" / "knowledge").mkdir(parents=True)
    (root / "shared" / "decisions").mkdir(parents=True)
    (root / "shared" / "runbooks").mkdir(parents=True)
    (root / "projects").mkdir()

    (root / "shared" / "knowledge" / "testing-guide.md").write_text(
        dedent("""\
        ---
        title: Testing Guide
        type: knowledge
        status: current
        owner: alex
        tags: [testing, guide]
        created: 2026-04-01
        updated: 2026-05-01
        ---

        # Testing Guide

        Always run pytest before pushing.
    """)
    )
    return root
