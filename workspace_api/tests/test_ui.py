# Copyright 2026, EOX (https://eox.at) and Versioneer (https://versioneer.at)
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

import pytest

from workspace_api import get_dist_dir


def test_incomplete_ui_bundle_is_not_selected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UI_DIST_DIR", str(tmp_path))
    assert get_dist_dir() is None

    (tmp_path / "ui.html").write_text("shell")
    assert get_dist_dir() is None

    (tmp_path / "management").mkdir()
    (tmp_path / "management" / "index.html").write_text("frontend")
    assert get_dist_dir() == tmp_path
