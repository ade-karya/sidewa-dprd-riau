"""Pengaman agar data production tidak pernah diisi ulang."""

from __future__ import annotations

from argparse import Namespace

import pytest

from app import cli
from app.config import settings
from app.services.seed import seed_demo
from app.services.supabase_sync import copy_local_to_supabase


def test_seed_demo_selalu_ditolak_di_production(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")

    with pytest.raises(RuntimeError, match="tidak boleh diisi ulang"):
        seed_demo(None, force=True)  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="tidak boleh diisi ulang"):
        seed_demo(None, force=False)  # type: ignore[arg-type]


def test_resync_ke_supabase_ditolak_di_production(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")

    with pytest.raises(RuntimeError, match="tidak boleh diisi ulang"):
        copy_local_to_supabase(truncate=True)

    with pytest.raises(RuntimeError, match="tidak boleh diisi ulang"):
        copy_local_to_supabase(truncate=False)


def test_perintah_isi_ulang_ditolak_di_production(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")

    assert cli.cmd_seed(Namespace(force=True)) == 2
    assert cli.cmd_seed(Namespace(force=False)) == 2
    assert cli.cmd_seed_staff(Namespace()) == 2
    assert cli.cmd_resync(Namespace(truncate=True)) == 2
    assert cli.cmd_resync(Namespace(truncate=False)) == 2
    assert cli.cmd_upgrade_portraits(Namespace(dry_run=True)) == 2
