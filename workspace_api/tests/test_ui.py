# Copyright 2026, EOX (https://eox.at) and Versioneer (https://versioneer.at)
# SPDX-License-Identifier: Apache-2.0

import os
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from workspace_api import get_dist_dir
from workspace_api.static import UIStaticFiles


def test_incomplete_ui_bundle_is_not_selected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UI_DIST_DIR", str(tmp_path))
    assert get_dist_dir() is None

    (tmp_path / "ui.html").write_text("shell")
    assert get_dist_dir() is None

    (tmp_path / "management").mkdir()
    (tmp_path / "management" / "index.html").write_text("frontend")
    assert get_dist_dir() == tmp_path


@pytest.fixture
def static_ui(tmp_path: Path) -> tuple[TestClient, Path]:
    for name in (
        "management/index.html",
        "management/assets/index-a1B2c3D4.js",
        "management/assets/index-a1B2c3D4.css",
        "standalone/config/app-config.js",
        "logo.svg",
    ):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("original")
    app = FastAPI()
    app.mount("/ui", UIStaticFiles(directory=tmp_path, html=True))
    return TestClient(app), tmp_path


@pytest.mark.parametrize(
    ("path", "status", "cache_control"),
    [
        ("management/", 200, "no-cache"),
        ("management/index.html", 200, "no-cache"),
        ("logo.svg", 200, "no-cache"),
        ("standalone/config/app-config.js", 200, "no-cache"),
        ("management/assets/index-a1B2c3D4.js", 200, "public, max-age=31536000, immutable"),
        ("management/assets/index-a1B2c3D4.css", 200, "public, max-age=31536000, immutable"),
        ("management/assets/missing-a1B2c3D4.js", 404, "no-store"),
    ],
)
def test_ui_files_use_the_required_cache_policy(static_ui: tuple[TestClient, Path], path: str, status: int, cache_control: str) -> None:
    client, _ = static_ui
    response = client.get(f"/ui/{path}")
    assert response.status_code == status
    assert response.headers["cache-control"] == cache_control


def test_ui_entry_revalidates_after_a_new_build(static_ui: tuple[TestClient, Path]) -> None:
    client, directory = static_ui
    response = client.get("/ui/management/")
    validators = {"If-None-Match": response.headers["etag"], "If-Modified-Since": response.headers["last-modified"]}
    unchanged = client.get("/ui/management/", headers=validators)
    assert unchanged.status_code == 304
    assert unchanged.headers["cache-control"] == "no-cache"
    assert client.head("/ui/management/").headers["cache-control"] == "no-cache"

    entry = directory / "management/index.html"
    original = entry.stat()
    entry.write_text("new build with new asset references")
    os.utime(entry, ns=(original.st_atime_ns, original.st_mtime_ns))
    updated = client.get("/ui/management/", headers=validators)
    assert updated.status_code == 200
    assert updated.text == "new build with new asset references"
    assert updated.headers["etag"] != response.headers["etag"]
    assert updated.headers["cache-control"] == "no-cache"
