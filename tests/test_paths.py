import sys
from pathlib import Path

from key_wizard.paths import data_dir, install_dir


def test_source_data_lives_in_project_root(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    root = Path(__file__).resolve().parents[1]
    assert install_dir() == root
    assert data_dir() == root / "data"


def test_frozen_data_lives_beside_executable(monkeypatch, tmp_path):
    exe = tmp_path / "KeyWizard.exe"
    exe.touch()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    assert install_dir() == tmp_path
    assert data_dir() == tmp_path / "data"
