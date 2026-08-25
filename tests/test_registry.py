"""Provenance registry: immutability, checksums, explicit errors."""
import json
import zipfile

import pytest

from cota_opt.download import _assert_valid_zip
from cota_opt.registry import Registry, RegistryError, load_sources, sha256_file


@pytest.fixture
def reg(tmp_path):
    return Registry(tmp_path / "raw")


def test_register_records_checksum_size_and_timestamp(reg, tmp_path):
    f = tmp_path / "d.csv"
    f.write_text("a,b\n1,2\n")
    rec = reg.register_file("demo", f, origin="http://example.test/d.csv")
    assert rec.sha256 == sha256_file(f)
    assert rec.size_bytes == f.stat().st_size
    assert rec.retrieved_at.endswith("+00:00")
    assert reg.get("demo").sha256 == rec.sha256


def test_registered_file_is_marked_read_only(reg, tmp_path):
    """Raw files are chmod 0444. (Root bypasses mode bits, so assert the mode,
    and rely on the checksum guard — tested below — as the real integrity check.)"""
    import os
    import stat
    f = tmp_path / "d.csv"
    f.write_text("x")
    reg.register_file("demo", f, origin="test")
    dest = reg.path_for("demo")
    assert stat.S_IMODE(dest.stat().st_mode) == 0o444
    if os.geteuid() != 0:
        with pytest.raises(PermissionError):
            dest.write_text("tampered")


def test_reregistering_different_content_is_refused(reg, tmp_path):
    a, b = tmp_path / "d.csv", tmp_path / "sub" / "d.csv"
    b.parent.mkdir()
    a.write_text("one")
    b.write_text("two")
    reg.register_file("demo", a, origin="test")
    with pytest.raises(RegistryError, match="immutable"):
        reg.register_file("demo", b, origin="test")


def test_reregistering_identical_content_is_idempotent(reg, tmp_path):
    a = tmp_path / "d.csv"
    a.write_text("same")
    r1 = reg.register_file("demo", a, origin="test")
    r2 = reg.register_file("demo", a, origin="test")
    assert r1.sha256 == r2.sha256


def test_unregistered_source_raises(reg):
    with pytest.raises(RegistryError, match="not registered"):
        reg.path_for("nope")


def test_missing_file_raises(reg, tmp_path):
    with pytest.raises(RegistryError, match="missing file"):
        reg.register_file("demo", tmp_path / "ghost.csv", origin="test")


def test_checksum_drift_is_detected(reg, tmp_path):
    f = tmp_path / "d.csv"
    f.write_text("original")
    reg.register_file("demo", f, origin="test")
    idx = json.loads((reg.root / "_provenance.json").read_text())
    idx["demo"]["sha256"] = "0" * 64
    (reg.root / "_provenance.json").write_text(json.dumps(idx))
    with pytest.raises(RegistryError, match="checksum drift"):
        reg.path_for("demo")


def test_sources_config_loads_with_required_fields():
    sources = load_sources()
    assert "cota_gtfs_static" in sources
    s = sources["cota_gtfs_static"]
    assert s.url.startswith("https://")
    assert s.publisher and s.status
    # every declared source must carry a status
    assert all(v.status for v in sources.values())


def test_zip_validation_rejects_non_gtfs(tmp_path):
    bad = tmp_path / "b.zip"
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("readme.txt", "not gtfs")
    with pytest.raises(RegistryError, match="missing required files"):
        _assert_valid_zip(bad)
    notzip = tmp_path / "n.zip"
    notzip.write_text("plain text")
    with pytest.raises(RegistryError, match="not a valid zip"):
        _assert_valid_zip(notzip)
