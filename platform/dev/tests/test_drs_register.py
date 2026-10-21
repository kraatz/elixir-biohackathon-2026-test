"""drs_register.py: the checksum cache written ahead of time (--hash-only) and reused when registering."""
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

PLATFORM = Path(__file__).resolve().parents[2]
SCRIPT = PLATFORM / "ansible" / "roles" / "drs_register" / "files" / "drs_register.py"


def load():
    spec = importlib.util.spec_from_file_location("drs_register", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def dr():
    return load()


@pytest.fixture
def data(tmp_path):
    root = tmp_path / "data"
    (root / "ref").mkdir(parents=True)
    (root / "sensitive" / "registry").mkdir(parents=True)
    (root / "ref" / "chr20.fa").write_bytes(b"ACGT" * 1000)
    (root / "sensitive" / "registry" / "registry.csv").write_text("id,name\n")
    (root / "PROVENANCE.md").write_text("# provenance\n")
    return root


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_hash_only_writes_every_file_of_the_tiers(dr, data, tmp_path, monkeypatch):
    cache = tmp_path / "hashes.json"
    monkeypatch.setattr(sys, "argv", ["drs_register.py", "--root", str(data), "--tiers", "ref,registry",
                                      "--hash-only", "--hashes", str(cache)])
    assert dr.main() == 0
    entries = json.loads(cache.read_text())
    assert set(entries) == {"ref/chr20.fa", "sensitive/registry/registry.csv", "PROVENANCE.md"}
    f = data / "ref" / "chr20.fa"
    assert entries["ref/chr20.fa"] == {"size": f.stat().st_size, "mtime_ns": f.stat().st_mtime_ns, "sha256": sha(f)}
    assert not cache.with_suffix(".json.tmp").exists()


def test_cached_hash_is_reused_only_while_size_and_mtime_match(dr, data):
    f = data / "ref" / "chr20.fa"
    st = f.stat()
    cache = {"ref/chr20.fa": {"size": st.st_size, "mtime_ns": st.st_mtime_ns, "sha256": "cached"}}
    assert dr.file_hash(f, "ref/chr20.fa", cache) == "cached"
    os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns + 1))
    assert dr.file_hash(f, "ref/chr20.fa", cache) == sha(f)
    assert dr.file_hash(f, "ref/other", cache) == sha(f)


def test_missing_or_broken_cache_is_empty(dr, tmp_path):
    assert dr.load_hashes(None) == {}
    assert dr.load_hashes(str(tmp_path / "absent.json")) == {}
    broken = tmp_path / "broken.json"
    broken.write_text("[1, 2")
    assert dr.load_hashes(str(broken)) == {}
    lst = tmp_path / "list.json"
    lst.write_text("[]")
    assert dr.load_hashes(str(lst)) == {}


def test_registering_needs_api_and_seed(dr, data, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["drs_register.py", "--root", str(data)])
    with pytest.raises(SystemExit):
        dr.main()
