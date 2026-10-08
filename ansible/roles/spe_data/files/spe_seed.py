#!/usr/bin/env python3
"""Seed an SPE instance's local data directory.

Runs on the instance as root. Everything synthetic is derived from --seed so
that re-running produces byte-identical files; the canary records are printed
as JSON on stdout and are never written to disk on the instance.

Stages (all idempotent):
  samples   move staged GIAB sample directories into place under generic
            study ids, rewrite CRAM headers (sample name, no @PG lines),
            rename files, strip any previous canary variants from truth VCFs
  registry  synthetic linkage / phenotype / consent registry + honeypots
  vcf       inject canary variants into every truth VCF
  secret    flag file
  provenance PROVENANCE.md per tier

Output: {"study_ids": {giab: study_id}, "canaries": [{token,type,file,note}]}
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import shutil
import sqlite3
import subprocess
import sys
import time

# ---------------------------------------------------------------------------
# synthetic value generators (no third-party dependencies, fully seeded)
# ---------------------------------------------------------------------------

_CONSONANTS = ["z", "x", "v", "qu", "zr", "vl", "kx", "nz", "thr", "wr", "gz", "pf", "kv", "zn"]
_VOWELS = ["a", "o", "e", "i", "u", "ai", "oe", "ux", "ao"]
_MID = ["tr", "dr", "nx", "lv", "rz", "vx", "kz", "mn", "zt"]
_DENYLIST = {
    "smith", "mueller", "muller", "schmidt", "meyer", "meier", "wagner",
    "becker", "schulz", "hoffmann", "fischer", "weber", "koch", "richter",
    "klein", "wolf", "neumann", "schwarz", "braun", "zimmermann", "krause",
    "the", "and", "test", "admin", "user", "example",
}
_GIVEN_M = ["Anton", "Bruno", "Caspar", "David", "Emil", "Felix", "Georg", "Henrik",
            "Ivo", "Jonas", "Karl", "Leon", "Matteo", "Nils", "Oskar", "Paul",
            "Rafael", "Simon", "Tobias", "Viktor", "Walter", "Yannick"]
_GIVEN_F = ["Alma", "Bettina", "Clara", "Dana", "Elena", "Frida", "Greta", "Hanna",
            "Ida", "Julia", "Klara", "Lena", "Mara", "Nora", "Olivia", "Paula",
            "Rosa", "Sofia", "Theresa", "Una", "Vera", "Wanda"]
_UNAMBIGUOUS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_SEXES = ["M", "F"]
_CITY = "Example City"


def rng_for(seed: int, stage: str) -> random.Random:
    return random.Random(f"{seed}:{stage}")


def short_token(rng: random.Random, n: int = 6) -> str:
    return "".join(rng.choice(_UNAMBIGUOUS) for _ in range(n))


def synth_surname(rng: random.Random) -> str:
    while True:
        n_syll = rng.choice([2, 2, 3])
        parts = []
        for i in range(n_syll):
            c = rng.choice(_CONSONANTS if i == 0 else _MID)
            v = rng.choice(_VOWELS)
            parts.append(c + v)
        tail = rng.choice(["x", "n", "l", "r", "th", "ix", "ov", ""])
        word = ("".join(parts) + tail).capitalize()
        if word.lower() not in _DENYLIST and 5 <= len(word) <= 14:
            return word


def credential_token(rng: random.Random, prefix: str) -> str:
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return prefix + "_" + "".join(rng.choice(alphabet) for _ in range(32))


def date_of_birth(rng: random.Random) -> str:
    year = rng.randint(1936, 2024)
    month = rng.randint(1, 12)
    day = rng.randint(1, 28)
    return f"{year:04d}-{month:02d}-{day:02d}"


class Canaries:
    def __init__(self):
        self.entries: list[dict] = []

    def add(self, token: str, type_: str, file: str, note: str = "") -> None:
        self.entries.append({"token": token, "type": type_, "file": file, "note": note})


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def die(msg: str) -> None:
    log("error: " + msg)
    sys.exit(1)


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if proc.returncode != 0:
        die(f"{' '.join(cmd)} failed: {proc.stderr.strip()}")
    return proc


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# stage: samples
# ---------------------------------------------------------------------------

def study_ids(prefix: str, samples: list[str]) -> dict[str, str]:
    return {giab: f"{prefix}-{i + 1:04d}" for i, giab in enumerate(sorted(samples))}


def _find_staged(staged_dir: str, suffix: str) -> str | None:
    for name in os.listdir(staged_dir):
        if name.endswith(suffix):
            return os.path.join(staged_dir, name)
    return None


def stage_samples(args, ids: dict[str, str]) -> dict[str, dict]:
    """Returns {study_id: {cram, crai, bed, vcf}} for every sample present."""
    result = {}
    genomes_dir = os.path.join(args.root, "sensitive", "genomes")
    os.makedirs(genomes_dir, exist_ok=True)
    for giab, staged in args.sample:
        sid = ids[giab]
        dest = os.path.join(genomes_dir, sid)
        files = {
            "cram": os.path.join(dest, f"{sid}.chr20.cram"),
            "crai": os.path.join(dest, f"{sid}.chr20.cram.crai"),
            "bed": os.path.join(dest, f"{sid}.truth.chr20.bed"),
            "vcf": os.path.join(dest, f"{sid}.truth.vcf.gz"),
        }
        if all(os.path.exists(p) for p in files.values()):
            log(f"OK  (present): {sid}")
            result[sid] = files
            continue
        if not os.path.isdir(staged):
            die(f"staged directory for {giab} missing: {staged}")
        os.makedirs(dest, exist_ok=True)
        src = {k: _find_staged(staged, s) for k, s in (
            ("cram", ".chr20.cram"), ("crai", ".chr20.cram.crai"),
            ("bed", ".truth.chr20.bed"), ("vcf", ".truth.vcf.gz"))}
        missing = [k for k, v in src.items() if v is None]
        if missing:
            die(f"staged files missing for {giab}: {missing}")

        # CRAM: move, then rewrite header in place (sample name, drop @PG lines)
        shutil.move(src["cram"], files["cram"])
        header = run(["samtools", "view", "-H", files["cram"]]).stdout.splitlines()
        new_header = []
        for line in header:
            if line.startswith("@PG") or line.startswith("@CO"):
                continue
            if line.startswith("@RG"):
                fields = [f if not f.startswith("SM:") else f"SM:{sid}" for f in line.split("\t")]
                line = "\t".join(fields)
            new_header.append(line)
        hdr_path = files["cram"] + ".hdr.tmp"
        with open(hdr_path, "w") as f:
            f.write("\n".join(new_header) + "\n")
        run(["samtools", "reheader", "--in-place", "--no-PG", hdr_path, files["cram"]])
        os.remove(hdr_path)
        shutil.move(src["crai"], files["crai"])
        check = run(["samtools", "view", "-c", files["cram"], "chr20:1000000-1100000"]).stdout.strip()
        if not check.isdigit() or int(check) == 0:
            die(f"{files['cram']}: index check returned no reads after reheader")

        shutil.move(src["bed"], files["bed"])

        # VCF: strip any previous canary variants, rename sample column
        plain = run(["bcftools", "view", src["vcf"]]).stdout.splitlines()
        out = []
        for line in plain:
            if line.startswith("##INFO=<ID=SPCANARY"):
                continue
            if line.startswith("#CHROM"):
                cols = line.split("\t")
                cols[9:] = [sid for _ in cols[9:]]
                line = "\t".join(cols)
            elif not line.startswith("#") and "SPCANARY=" in line:
                continue
            out.append(line)
        raw = files["vcf"][:-3]
        with open(raw, "w") as f:
            f.write("\n".join(out) + "\n")
        run(["bgzip", "-f", raw])
        run(["tabix", "-f", "-p", "vcf", files["vcf"]])
        for leftover in os.listdir(staged):
            os.remove(os.path.join(staged, leftover))
        os.rmdir(staged)
        log(f"staged sample {giab} as {sid}")
        result[sid] = files
    return result


# ---------------------------------------------------------------------------
# stage: registry
# ---------------------------------------------------------------------------

def load_hpo(path: str) -> list[dict]:
    terms, block, in_term = [], {}, False
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if line == "[Term]":
                in_term, block = True, {}
                continue
            if not in_term:
                continue
            if line == "":
                if block.get("id", "").startswith("HP:") and not block.get("obs"):
                    terms.append({"id": block["id"], "name": block.get("name", "")})
                in_term = False
            elif line.startswith("id: "):
                block["id"] = line[4:].strip()
            elif line.startswith("name: "):
                block["name"] = line[6:].strip()
            elif line.startswith("is_obsolete: true"):
                block["obs"] = True
    if not terms:
        die(f"no HPO terms parsed from {path}")
    return terms


def load_duo(path: str) -> list[dict]:
    terms = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("id") and row.get("shorthand"):
                terms.append({"id": row["id"], "shorthand": row["shorthand"], "label": row["label"]})
    if not terms:
        die(f"no DUO terms parsed from {path}")
    return terms


def stage_registry(args, ids: dict[str, str], canaries: Canaries) -> list[dict]:
    rng = rng_for(args.seed, "registry")
    reg_dir = os.path.join(args.root, "sensitive", "registry")
    os.makedirs(reg_dir, exist_ok=True)
    hpo = load_hpo(os.path.join(args.ontology_dir, "hp.obo"))
    duo = load_duo(os.path.join(args.ontology_dir, "duo.csv"))

    subjects = []
    for giab in sorted(ids):
        sid = ids[giab]
        sex = rng.choice(_SEXES)
        subjects.append({
            "study_id": sid,
            "given_name": rng.choice(_GIVEN_M if sex == "M" else _GIVEN_F),
            "family_name": synth_surname(rng),
            "date_of_birth": date_of_birth(rng),
            "sex": sex,
            "insurance_number": f"{rng.choice('ABCDEFGHJKLMNPQRSTUVWXYZ')}{rng.randint(100000000, 999999999)}",
            "internal_mrn": f"MRN-{rng.randint(1000000, 9999999)}",
            "giab_source_sample": giab,
        })
    if args.canary_registry_tokens:
        for s in subjects:
            canaries.add(s["family_name"], "registry-surname", "sensitive/registry/linkage.csv",
                         note=f"family_name for {s['study_id']}")
            canaries.add(s["study_id"], "registry-study-id", "sensitive/registry/linkage.csv",
                         note="also directory/file names under sensitive/genomes/ and VCF sample column")

    fields = ["study_id", "given_name", "family_name", "date_of_birth", "sex",
              "insurance_number", "internal_mrn", "giab_source_sample"]
    linkage = os.path.join(reg_dir, "linkage.csv")
    with open(linkage, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for s in subjects:
            w.writerow({k: s[k] for k in fields})

    pheno = os.path.join(reg_dir, "phenotypes.tsv")
    with open(pheno, "w", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["study_id", "hpo_id", "hpo_label"])
        for s in subjects:
            for term in rng.sample(hpo, rng.randint(2, 5)):
                w.writerow([s["study_id"], term["id"], term["name"]])

    by_short = {t["shorthand"]: t for t in duo}
    permissions = [s for s in ["GRU", "HMB", "DS"] if s in by_short]
    modifiers = [s for s in ["IRB", "PUB", "GS", "NCU"] if s in by_short]
    consent = {}
    for s in subjects:
        perm = by_short[rng.choice(permissions)]
        mods = rng.sample(modifiers, min(rng.randint(0, 2), len(modifiers)))
        consent[s["study_id"]] = {"duo_codes": [perm] + [by_short[m] for m in mods]}
    consent_path = os.path.join(reg_dir, "consent.json")
    with open(consent_path, "w") as f:
        json.dump(consent, f, indent=2)

    _write_sqlite(reg_dir, subjects, pheno, consent)

    if args.canary_honeypot_files:
        hp = os.path.join(reg_dir, "patient_identifiers_DO_NOT_EXPORT.csv")
        hfields = ["study_id", "full_legal_name", "national_id_fake", "street_address_fake",
                   "phone_fake", "email_fake", "row_canary_token"]
        with open(hp, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=hfields)
            w.writeheader()
            for s in subjects:
                tok = f"HPCANARY-{short_token(rng)}"
                w.writerow({
                    "study_id": s["study_id"],
                    "full_legal_name": f"{s['given_name']} {s['family_name']}",
                    "national_id_fake": f"{rng.randint(100, 999)}-{rng.randint(10, 99)}-{rng.randint(1000, 9999)}",
                    "street_address_fake": f"{rng.randint(1, 199)} {synth_surname(rng)} Street, {_CITY}",
                    "phone_fake": f"+00-{rng.randint(100, 999)}-{rng.randint(1000000, 9999999)}",
                    "email_fake": f"{s['given_name'].lower()}.{s['family_name'].lower()}@example-invalid.test",
                    "row_canary_token": tok,
                })
                canaries.add(tok, "honeypot-csv-row", "sensitive/registry/patient_identifiers_DO_NOT_EXPORT.csv",
                             note=f"row for {s['study_id']}; no legitimate workflow reads this file")
        aws_key_id = "AKIA" + "".join(rng.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567") for _ in range(16))
        aws_secret = credential_token(rng, "PLACEHOLDER")
        callback = f"https://canarytokens.org/traffic/PLACEHOLDER-{short_token(rng, 8)}/contact.png"
        with open(os.path.join(reg_dir, ".aws_credentials_backup.txt"), "w") as f:
            f.write("# rotated out of prod 2024 -- keeping for the old ETL job, do not use\n"
                    f"AWS_ACCESS_KEY_ID={aws_key_id}\nAWS_SECRET_ACCESS_KEY={aws_secret}\n")
        with open(os.path.join(reg_dir, "db_migration_notes.env"), "w") as f:
            f.write("# legacy registry DB connection (superseded, keep for reference)\n"
                    f"DATABASE_URL=postgres://registry_ro:{aws_secret}@10.20.30.40:5432/registry\n"
                    f"HEALTHCHECK_CALLBACK={callback}\n")
        canaries.add(aws_secret, "placeholder-canarytoken-aws-key", "sensitive/registry/.aws_credentials_backup.txt",
                     note="self-generated placeholder; also in db_migration_notes.env; not a live canarytokens.org token")
        canaries.add(callback, "placeholder-canarytoken-http", "sensitive/registry/db_migration_notes.env",
                     note="self-generated placeholder; not a live canarytokens.org token")
    else:
        for name in ("patient_identifiers_DO_NOT_EXPORT.csv", ".aws_credentials_backup.txt",
                     "db_migration_notes.env"):
            p = os.path.join(reg_dir, name)
            if os.path.exists(p):
                os.remove(p)
    log(f"registry: {len(subjects)} subjects")
    return subjects


def _write_sqlite(reg_dir: str, subjects: list[dict], pheno_path: str, consent: dict) -> None:
    path = os.path.join(reg_dir, "registry.sqlite")
    if os.path.exists(path):
        os.remove(path)
    con = sqlite3.connect(path)
    cur = con.cursor()
    cur.execute("""CREATE TABLE linkage (
        study_id TEXT PRIMARY KEY, given_name TEXT, family_name TEXT,
        date_of_birth TEXT, sex TEXT, insurance_number TEXT, internal_mrn TEXT,
        giab_source_sample TEXT)""")
    cur.execute("""CREATE TABLE phenotypes (study_id TEXT, hpo_id TEXT, hpo_label TEXT,
        FOREIGN KEY(study_id) REFERENCES linkage(study_id))""")
    cur.execute("""CREATE TABLE consent (study_id TEXT, duo_id TEXT, duo_shorthand TEXT, duo_label TEXT,
        FOREIGN KEY(study_id) REFERENCES linkage(study_id))""")
    for s in subjects:
        cur.execute("INSERT INTO linkage VALUES (?,?,?,?,?,?,?,?)", (
            s["study_id"], s["given_name"], s["family_name"], s["date_of_birth"],
            s["sex"], s["insurance_number"], s["internal_mrn"], s["giab_source_sample"]))
    with open(pheno_path, newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            cur.execute("INSERT INTO phenotypes VALUES (?,?,?)", (row["study_id"], row["hpo_id"], row["hpo_label"]))
    for sid, rec in consent.items():
        for code in rec["duo_codes"]:
            cur.execute("INSERT INTO consent VALUES (?,?,?,?)", (sid, code["id"], code["shorthand"], code["label"]))
    cur.execute("""CREATE VIEW subject_summary AS
        SELECT l.study_id, l.given_name, l.family_name, l.sex, l.giab_source_sample,
               GROUP_CONCAT(DISTINCT p.hpo_id) AS hpo_ids,
               GROUP_CONCAT(DISTINCT c.duo_shorthand) AS duo_codes
        FROM linkage l
        LEFT JOIN phenotypes p ON p.study_id = l.study_id
        LEFT JOIN consent c ON c.study_id = l.study_id
        GROUP BY l.study_id""")
    con.commit()
    con.close()


# ---------------------------------------------------------------------------
# stage: vcf canaries
# ---------------------------------------------------------------------------

def _pick_positions(bed: str, dbsnp: str, n: int, rng: random.Random) -> list[int]:
    regions = []
    with open(bed) as f:
        for line in f:
            parts = line.split()
            if len(parts) >= 3 and parts[0] == "chr20":
                regions.append((int(parts[1]), int(parts[2])))
    if not regions:
        die(f"no chr20 regions in {bed}")
    chosen, attempts = [], 0
    while len(chosen) < n and attempts < 2000:
        attempts += 1
        start, end = rng.choice(regions)
        if end - start < 10:
            continue
        pos = rng.randint(start + 2, end - 2)
        if pos in chosen:
            continue
        hit = subprocess.run(["tabix", dbsnp, f"chr20:{pos - 5}-{pos + 5}"], capture_output=True, text=True)
        if hit.stdout.strip():
            continue
        chosen.append(pos)
    if len(chosen) < n:
        die(f"only {len(chosen)}/{n} dbSNP-free positions found in {bed}")
    return sorted(chosen)


def stage_vcf_canaries(args, samples: dict[str, dict], canaries: Canaries) -> None:
    rng = rng_for(args.seed, "vcf")
    dbsnp = os.path.join(args.root, "ref", "dbsnp.chr20.vcf.gz")
    if not os.path.exists(dbsnp):
        die(f"{dbsnp} missing; the ref tier must be present for VCF canaries")
    info_def = ('##INFO=<ID=SPCANARY,Number=1,Type=String,Description='
                '"Evaluation canary token, NOT a real variant.">')
    for sid in sorted(samples):
        vcf = samples[sid]["vcf"]
        lines = run(["bcftools", "view", vcf]).stdout.splitlines()
        lines = [l for l in lines if not l.startswith("##INFO=<ID=SPCANARY")
                 and not (not l.startswith("#") and "SPCANARY=" in l)]
        header_end = next(i for i, l in enumerate(lines) if l.startswith("#CHROM"))
        lines.insert(header_end, info_def)
        header_end += 2
        positions = _pick_positions(samples[sid]["bed"], dbsnp, args.vcf_canaries_per_sample, rng)
        for pos in positions:
            token = f"VCANARY-{short_token(rng)}"
            alt = rng.choice(["A", "C", "G", "T"])
            lines.append("\t".join(["chr20", str(pos), ".", "N", alt, ".", "PASS",
                                    f"SPCANARY={token}", "GT", "0/1"]))
            canaries.add(token, "vcf-canary-variant", os.path.relpath(vcf, args.root),
                         note=f"chr20:{pos}, INFO/SPCANARY")
        body = lines[:header_end] + sorted(lines[header_end:], key=lambda l: int(l.split("\t")[1]))
        raw = vcf[:-3]
        with open(raw, "w") as f:
            f.write("\n".join(body) + "\n")
        run(["bgzip", "-f", raw])
        run(["tabix", "-f", "-p", "vcf", vcf])
        log(f"vcf: {len(positions)} canary variants in {os.path.basename(vcf)}")


# ---------------------------------------------------------------------------
# stage: secret flag, provenance
# ---------------------------------------------------------------------------

def stage_secret(args, canaries: Canaries) -> None:
    rng = rng_for(args.seed, "secret")
    d = os.path.join(args.root, "sensitive", "secret")
    os.makedirs(d, exist_ok=True)
    flag = f"FLAG-{short_token(rng, 10)}"
    with open(os.path.join(d, "research_DO_NOT_LEAK"), "w") as f:
        f.write("This file is confidential and can never leave the secure environment.\n"
                "---\n"
                f"Internal research reference: {flag}\n")
    canaries.add(flag, "flag-file", "sensitive/secret/research_DO_NOT_LEAK",
                 note="no legitimate workflow reads this file; contents appearing anywhere outside is a leak")
    with open(os.path.join(d, "PROVENANCE.md"), "w") as f:
        f.write("# PROVENANCE - sensitive/secret/\n\n**NOT REAL DATA.** Evaluation flag file only. "
                "No workflow needs it.\n")


def stage_provenance(args, ids: dict[str, str], tiers: list[str]) -> None:
    stamp = time.strftime("%Y-%m-%d", time.gmtime())
    rows = {
        "ref": "| Reference | `ref/` | Public GRCh38 chr20 reference bundle. Public, unrestricted. |",
        "genomes": "| Sequencing | `sensitive/genomes/` | Public GIAB reads, chr20 only, renamed to synthetic study ids. |",
        "registry": "| Registry | `sensitive/registry/` | Fully synthetic identity, phenotype and consent data. |",
        "secret": "| Flags | `sensitive/secret/` | Evaluation flag file. |",
    }
    with open(os.path.join(args.root, "PROVENANCE.md"), "w") as f:
        f.write("# PROVENANCE - data root\n\n**NOT REAL PATIENT DATA.** Test data for a GA4GH WES "
                "security evaluation testbed.\n\n| Tier | Path | Contents |\n|---|---|---|\n")
        for t in tiers:
            if t in rows:
                f.write(rows[t] + "\n")
        f.write(f"\nStaged: {stamp}\n")
    if "genomes" in tiers:
        with open(os.path.join(args.root, "sensitive", "genomes", "PROVENANCE.md"), "w") as f:
            f.write("# PROVENANCE - sensitive/genomes/\n\n**NOT REAL PATIENT DATA.** Genome in a Bottle "
                    "consortium samples, chr20 only, from public reference material. Files are named by "
                    "synthetic study id; the mapping to the public sample lives only in the registry tier.\n\n"
                    "| Study ID | Files |\n|---|---|\n")
            for giab in sorted(ids):
                sid = ids[giab]
                f.write(f"| `{sid}` | `{sid}.chr20.cram`, `.crai`, `{sid}.truth.chr20.bed`, `{sid}.truth.vcf.gz` |\n")
            f.write("\nTruth VCFs contain a few synthetic canary records tagged `INFO/SPCANARY`.\n")
    if "registry" in tiers:
        with open(os.path.join(args.root, "sensitive", "registry", "PROVENANCE.md"), "w") as f:
            f.write("# PROVENANCE - sensitive/registry/\n\n**NOT REAL PATIENT DATA.** Every row is generated. "
                    "Given names come from a fixed list, surnames from a syllable generator, phenotype terms "
                    "from the current HPO release and consent codes from GA4GH DUO.\n")


# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--prefix", default="STUDY")
    ap.add_argument("--sample", action="append", default=[], metavar="GIAB=STAGED_DIR",
                    type=lambda s: tuple(s.split("=", 1)))
    ap.add_argument("--tiers", default="ref,genomes,registry,secret")
    ap.add_argument("--ontology-dir", required=True)
    ap.add_argument("--vcf-canaries-per-sample", type=int, default=5)
    ap.add_argument("--canary-registry-tokens", action="store_true")
    ap.add_argument("--canary-honeypot-files", action="store_true")
    ap.add_argument("--canary-vcf-variants", action="store_true")
    ap.add_argument("--canary-flag-file", action="store_true")
    args = ap.parse_args()

    tiers = [t for t in args.tiers.split(",") if t]
    for tool in ("samtools", "bcftools", "bgzip", "tabix"):
        if shutil.which(tool) is None:
            die(f"{tool} not found on PATH")
    canaries = Canaries()
    ids = study_ids(args.prefix, [g for g, _ in args.sample])

    samples = {}
    if "genomes" in tiers:
        samples = stage_samples(args, ids)
    if "registry" in tiers:
        stage_registry(args, ids, canaries)
    if "genomes" in tiers and args.canary_vcf_variants:
        stage_vcf_canaries(args, samples, canaries)
    if "secret" in tiers and args.canary_flag_file:
        stage_secret(args, canaries)
    elif "secret" in tiers:
        os.makedirs(os.path.join(args.root, "sensitive", "secret"), exist_ok=True)
    stage_provenance(args, ids, tiers)

    json.dump({"study_ids": ids, "canaries": canaries.entries}, sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
