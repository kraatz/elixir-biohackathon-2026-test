"""spe_preflight.py decides whether an existing host may be configured for an instance."""
import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "ansible" / "roles" / "existing_host" / "files" / "spe_preflight.py"


def load():
    spec = importlib.util.spec_from_file_location("spe_preflight", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def pf():
    return load()


class FakeHost:
    """What the host looks like: listening ports, which compose project publishes each, free disk."""

    def __init__(self, listening=(), port_projects=None, projects_running=(), free_gb=100, docker_root=None):
        self.listening = set(listening)
        self.port_projects = port_projects or {}
        self.projects_running = set(projects_running)
        self.free = free_gb
        self.docker_root_dir = docker_root

    def listening_ports(self):
        return self.listening

    def projects_publishing(self, port):
        return self.port_projects.get(port, set())

    def running_projects(self):
        return self.projects_running

    def free_gb(self, path):
        return self.free

    def docker_root(self):
        return self.docker_root_dir


def cfg(tmp_path, **over):
    base = {
        "instance": "dev-local",
        "provision": "existing",
        "marker": str(tmp_path / "etc" / "spe-instance"),
        "manifest": str(tmp_path / "etc" / "spe-instance.json"),
        "paths": {
            "stack_dir": str(tmp_path / "srv" / "workflow-stack"),
            "frontend_dir": str(tmp_path / "srv" / "spe-frontend"),
            "data_root": str(tmp_path / "srv" / "data"),
        },
        "ports": {"443": "workflow-stack", "3000": "spe-frontend", "8100": "spe-frontend"},
        "projects": ["workflow-stack", "spe-frontend"],
        "min_free_gb": 15,
    }
    base.update(over)
    (tmp_path / "etc").mkdir(exist_ok=True)
    (tmp_path / "srv").mkdir(exist_ok=True)
    return base


def own(c, tmp_path, instance="dev-local", paths=None):
    """Make the host look as if `instance` had already been created here."""
    Path(c["marker"]).write_text(instance + "\n")
    Path(c["manifest"]).write_text(json.dumps({
        "instance": instance, "provision": "existing",
        "paths": paths if paths is not None else c["paths"],
        "compose_projects": c["projects"],
    }))


def test_fresh_host_is_accepted(pf, tmp_path):
    c = cfg(tmp_path)
    res = pf.check(c, FakeHost())
    assert res["problems"] == []
    assert res["owner"] == ""
    assert res["resolved"]["stack_dir"] == c["paths"]["stack_dir"]


def test_other_instance_is_refused(pf, tmp_path):
    c = cfg(tmp_path)
    own(c, tmp_path, instance="dev-local")
    res = pf.check({**c, "instance": "intruder"}, FakeHost())
    assert any("belongs to instance 'dev-local', not 'intruder'" in p for p in res["problems"])


def test_unmarked_host_with_stack_dir_is_refused(pf, tmp_path):
    c = cfg(tmp_path)
    Path(c["paths"]["stack_dir"]).mkdir()
    res = pf.check(c, FakeHost())
    assert any("stack_dir" in p and "not owned" in p for p in res["problems"])


def test_unmarked_host_with_443_in_use_is_refused(pf, tmp_path):
    res = pf.check(cfg(tmp_path), FakeHost(listening={443}))
    assert any("443" in p for p in res["problems"])


def test_unmarked_host_with_our_project_running_is_refused(pf, tmp_path):
    res = pf.check(cfg(tmp_path), FakeHost(projects_running={"spe-frontend"}))
    assert any("spe-frontend" in p for p in res["problems"])


def test_owned_host_converges(pf, tmp_path):
    c = cfg(tmp_path)
    own(c, tmp_path)
    for p in c["paths"].values():
        Path(p).mkdir()
    host = FakeHost(listening={443, 3000}, port_projects={443: {"workflow-stack"}, 3000: {"spe-frontend"}},
                    projects_running={"workflow-stack", "spe-frontend"})
    assert pf.check(c, host)["problems"] == []


def test_owned_host_with_foreign_listener_is_refused(pf, tmp_path):
    c = cfg(tmp_path)
    own(c, tmp_path)
    host = FakeHost(listening={3000}, port_projects={3000: {"someone-else"}})
    res = pf.check(c, host)
    assert any("3000" in p for p in res["problems"])


def test_owned_host_with_unrecorded_existing_path_is_refused(pf, tmp_path):
    c = cfg(tmp_path)
    own(c, tmp_path, paths={**c["paths"], "frontend_dir": "/elsewhere"})
    Path(c["paths"]["frontend_dir"]).mkdir()
    res = pf.check(c, FakeHost())
    assert any("frontend_dir" in p for p in res["problems"])


def test_marker_without_manifest_is_refused(pf, tmp_path):
    c = cfg(tmp_path)
    Path(c["marker"]).write_text("dev-local\n")
    res = pf.check(c, FakeHost())
    assert any("manifest" in p for p in res["problems"])


@pytest.mark.parametrize("bad", ["relative/dir", "/", "/home/someone", "/root"])
def test_unsafe_paths_are_refused(pf, tmp_path, bad):
    c = cfg(tmp_path)
    c["paths"]["data_root"] = bad
    res = pf.check(c, FakeHost())
    assert any("data_root" in p for p in res["problems"])


def test_symlinked_path_is_refused(pf, tmp_path):
    c = cfg(tmp_path)
    (tmp_path / "shared").mkdir()
    Path(c["paths"]["data_root"]).symlink_to(tmp_path / "shared")
    res = pf.check(c, FakeHost())
    assert any("data_root" in p and "symlink" in p for p in res["problems"])


def test_low_disk_is_refused(pf, tmp_path):
    res = pf.check(cfg(tmp_path), FakeHost(free_gb=3, docker_root="/var/lib/docker"))
    assert any("3 GB free" in p for p in res["problems"])


def test_path_inside_docker_root_is_refused(pf, tmp_path):
    c = cfg(tmp_path)
    res = pf.check(c, FakeHost(docker_root=str(tmp_path / "srv")))
    assert any("Docker" in p for p in res["problems"])


def test_cli_prints_json(tmp_path):
    import base64
    import subprocess
    import sys
    c = cfg(tmp_path, ports={})
    arg = base64.b64encode(json.dumps(c).encode()).decode()
    out = subprocess.run([sys.executable, str(SCRIPT), arg], check=True, capture_output=True, text=True).stdout
    assert "problems" in json.loads(out)
