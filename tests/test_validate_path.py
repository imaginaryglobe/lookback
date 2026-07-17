from pathlib import Path

import pytest
from fastapi import HTTPException

import main


@pytest.fixture
def ssd_root(tmp_path, monkeypatch):
    root = tmp_path / "ssd"
    root.mkdir()
    monkeypatch.setattr(main, "SSD_ROOT", root.resolve())
    return root.resolve()


def test_path_inside_ssd_root_is_allowed(ssd_root):
    inside = ssd_root / "vacation" / "img.jpg"
    assert main._validate_path(str(inside)) == inside.resolve()


def test_path_outside_ssd_root_is_rejected(ssd_root, tmp_path):
    outside = tmp_path / "elsewhere" / "img.jpg"
    with pytest.raises(HTTPException) as exc_info:
        main._validate_path(str(outside))
    assert exc_info.value.status_code == 400


def test_traversal_out_of_ssd_root_is_rejected(ssd_root):
    traversal = ssd_root / ".." / "elsewhere" / "img.jpg"
    with pytest.raises(HTTPException) as exc_info:
        main._validate_path(str(traversal))
    assert exc_info.value.status_code == 400


def test_ssd_root_itself_is_allowed(ssd_root):
    assert main._validate_path(str(ssd_root)) == ssd_root
