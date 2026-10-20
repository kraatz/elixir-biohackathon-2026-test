"""The dummy dataset must be accepted by spe_seed.py exactly as the real one is."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

PLATFORM = Path(__file__).resolve().parents[2]
GEN = PLATFORM / "dev" / "make_dummy_dataset.py"
SEED = PLATFORM / "ansible" / "roles" / "spe_data" / "files" / "spe_seed.py"
ONTOLOGY = PLATFORM / "ansible" / "roles" / "spe_data" / "files" / "ontology"
SAMPLES = {"HG002": "BIH-SPE-0001", "HG003": "BIH-SPE-0002", "HG004": "BIH-SPE-0003", "HG005": "BIH-SPE-0004"}


def generate(out: Path, seed: int = 7) -> dict:
    res = subprocess.run([sys.executable, str(GEN), "--out", str(out), "--seed", str(seed)],
                         check=True, capture_output=True, text=True)
    return json.loads(res.stdout)


def test_layout(tmp_path):
    summary = generate(tmp_path / "d")
    root = tmp_path / "d"
    for name in ("dummy.chr20.fa", "dummy.chr20.fa.fai", "dbsnp.chr20.vcf.gz", "dbsnp.chr20.vcf.gz.tbi"):
        assert (root / "ref" / name).is_file(), name
    for giab, d in SAMPLES.items():
        sd = root / "sensitive" / "genomes" / d
        for suffix in (".chr20.cram", ".chr20.cram.crai", ".truth.chr20.bed", ".truth.vcf.gz"):
            assert (sd / f"{giab}{suffix}").is_file(), f"{giab}{suffix}"
    assert set(summary["samples"]) == set(SAMPLES)


def test_reads_in_checked_region(tmp_path):
    generate(tmp_path / "d")
    cram = tmp_path / "d" / "sensitive" / "genomes" / "BIH-SPE-0001" / "HG002.chr20.cram"
    n = subprocess.run(["samtools", "view", "-c", str(cram), "chr20:1000000-1100000"],
                       check=True, capture_output=True, text=True).stdout.strip()
    assert int(n) > 0


def test_deterministic(tmp_path):
    generate(tmp_path / "a", seed=3)
    generate(tmp_path / "b", seed=3)
    for rel in ("ref/dummy.chr20.fa", "sensitive/genomes/BIH-SPE-0002/HG003.truth.chr20.bed"):
        assert (tmp_path / "a" / rel).read_bytes() == (tmp_path / "b" / rel).read_bytes(), rel


def test_refuses_existing_without_force(tmp_path):
    generate(tmp_path / "d")
    res = subprocess.run([sys.executable, str(GEN), "--out", str(tmp_path / "d")], capture_output=True, text=True)
    assert res.returncode != 0 and "--force" in res.stderr


def test_spe_seed_accepts_it(tmp_path):
    src = tmp_path / "src"
    generate(src)
    root = tmp_path / "root"
    shutil.copytree(src / "ref", root / "ref")
    staging = root / ".staging"
    args = []
    for giab, d in SAMPLES.items():
        shutil.copytree(src / "sensitive" / "genomes" / d, staging / giab)
        args.append(f"--sample={giab}={staging / giab}")
    res = subprocess.run(
        [sys.executable, str(SEED), "--root", str(root), "--seed", "11", "--prefix", "STUDY",
         "--tiers", "ref,genomes,registry,secret", "--ontology-dir", str(ONTOLOGY),
         "--vcf-canaries-per-sample", "5", *args,
         "--canary-registry-tokens", "--canary-honeypot-files", "--canary-vcf-variants", "--canary-flag-file"],
        capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout)
    assert sorted(out["study_ids"].values()) == ["STUDY-0001", "STUDY-0002", "STUDY-0003", "STUDY-0004"]
    assert sum(1 for c in out["canaries"] if c["type"] == "vcf-canary-variant") == 20
