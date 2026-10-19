#!/usr/bin/env python3
"""Generate a tiny synthetic base dataset in the layout spe_data expects.

Stands in for /data-share (GIAB genomes) on machines that do not have it.
Everything derives from --seed. Needs samtools, bgzip and tabix on PATH.

Layout written under --out (mirrors spe_source_samples in group_vars):
  ref/dummy.chr20.fa(.fai)            a random 1.2 Mb "chr20"
  ref/dbsnp.chr20.vcf.gz(.tbi)        sparse known sites
  sensitive/genomes/BIH-SPE-000n/<GIAB>.chr20.cram(.crai)   reads, reference embedded
  sensitive/genomes/BIH-SPE-000n/<GIAB>.truth.chr20.bed     regions inside 1.0-1.1 Mb
  sensitive/genomes/BIH-SPE-000n/<GIAB>.truth.vcf.gz        a few variants
Prints a JSON summary on stdout.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import subprocess
import sys

SAMPLES = {
    "HG002": "sensitive/genomes/BIH-SPE-0001",
    "HG003": "sensitive/genomes/BIH-SPE-0002",
    "HG004": "sensitive/genomes/BIH-SPE-0003",
    "HG005": "sensitive/genomes/BIH-SPE-0004",
}
CHROM = "chr20"
CHR_LEN = 1_200_000
REGION = (1_000_000, 1_100_000)  # spe_seed.py counts reads in chr20:1000000-1100000
READ_LEN = 100
READS_PER_SAMPLE = 400
BED_INTERVALS = 20
BED_WIDTH = 1_000
DBSNP_SITES = 30
TRUTH_VARIANTS = 10
BASES = "ACGT"


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def vcf_header(sample: str | None) -> list[str]:
    lines = ["##fileformat=VCFv4.2", f"##contig=<ID={CHROM},length={CHR_LEN}>"]
    cols = ["#CHROM", "POS", "ID", "REF", "ALT", "QUAL", "FILTER", "INFO"]
    if sample:
        lines.append('##FORMAT=<ID=GT,Number=1,Type=String,Description="Genotype">')
        cols += ["FORMAT", sample]
    return lines + ["\t".join(cols)]


def write_bgzip_vcf(path: str, lines: list[str], index: bool) -> None:
    raw = path[:-3]
    with open(raw, "w") as f:
        f.write("\n".join(lines) + "\n")
    run(["bgzip", "-f", raw])
    if index:
        run(["tabix", "-f", "-p", "vcf", path])


def make_reference(rng: random.Random, ref_dir: str) -> tuple[str, str]:
    seq = "".join(rng.choice(BASES) for _ in range(CHR_LEN))
    fa = os.path.join(ref_dir, "dummy.chr20.fa")
    with open(fa, "w") as f:
        f.write(f">{CHROM}\n")
        for i in range(0, CHR_LEN, 60):
            f.write(seq[i:i + 60] + "\n")
    run(["samtools", "faidx", fa])
    return fa, seq


def alt_for(rng: random.Random, ref_base: str) -> str:
    return rng.choice([b for b in BASES if b != ref_base])


def make_dbsnp(rng: random.Random, seq: str, ref_dir: str) -> None:
    sites = sorted(rng.sample(range(REGION[0], REGION[1]), DBSNP_SITES))
    body = [f"{CHROM}\t{p}\trs{900000 + i}\t{seq[p - 1]}\t{alt_for(rng, seq[p - 1])}\t.\tPASS\t."
            for i, p in enumerate(sites)]
    write_bgzip_vcf(os.path.join(ref_dir, "dbsnp.chr20.vcf.gz"), vcf_header(None) + body, index=True)


def make_sample(rng: random.Random, seq: str, fa: str, giab: str, out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    starts = sorted(rng.sample(range(REGION[0], REGION[1] - BED_WIDTH, BED_WIDTH), BED_INTERVALS))
    with open(os.path.join(out_dir, f"{giab}.truth.chr20.bed"), "w") as f:
        for s in starts:
            f.write(f"{CHROM}\t{s}\t{s + BED_WIDTH}\n")

    positions = sorted(rng.sample([s + o for s in starts for o in range(10, BED_WIDTH - 10, 97)], TRUTH_VARIANTS))
    body = [f"{CHROM}\t{p}\t.\t{seq[p - 1]}\t{alt_for(rng, seq[p - 1])}\t50\tPASS\t.\tGT\t0/1" for p in positions]
    write_bgzip_vcf(os.path.join(out_dir, f"{giab}.truth.vcf.gz"), vcf_header(giab) + body, index=False)

    sam = os.path.join(out_dir, f"{giab}.sam")
    read_starts = sorted(rng.randint(REGION[0], REGION[1] - READ_LEN) for _ in range(READS_PER_SAMPLE))
    with open(sam, "w") as f:
        f.write("@HD\tVN:1.6\tSO:coordinate\n")
        f.write(f"@SQ\tSN:{CHROM}\tLN:{CHR_LEN}\n")
        f.write(f"@RG\tID:rg1\tSM:{giab}\n")
        f.write("@PG\tID:dummy\tPN:make_dummy_dataset\n")
        for i, pos in enumerate(read_starts):
            read = seq[pos - 1:pos - 1 + READ_LEN]
            f.write(f"{giab}.r{i}\t0\t{CHROM}\t{pos}\t60\t{READ_LEN}M\t*\t0\t0\t{read}\t{'I' * READ_LEN}\tRG:Z:rg1\n")
    cram = os.path.join(out_dir, f"{giab}.chr20.cram")
    run(["samtools", "view", "-C", "-T", fa, "--output-fmt-option", "embed_ref=1", "-o", cram, sam])
    run(["samtools", "index", cram])
    os.remove(sam)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, help="directory to write (spe_source_data_root)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--force", action="store_true", help="replace an existing --out")
    args = ap.parse_args()

    for tool in ("samtools", "bgzip", "tabix"):
        if shutil.which(tool) is None:
            print(f"{tool} not found on PATH", file=sys.stderr)
            return 2
    if os.path.exists(args.out) and os.listdir(args.out):
        if not args.force:
            print(f"{args.out} exists and is not empty; pass --force to replace it", file=sys.stderr)
            return 1
        shutil.rmtree(args.out)

    rng = random.Random(f"dummy-dataset:{args.seed}")
    ref_dir = os.path.join(args.out, "ref")
    os.makedirs(ref_dir)
    fa, seq = make_reference(rng, ref_dir)
    make_dbsnp(rng, seq, ref_dir)
    for giab, rel in SAMPLES.items():
        make_sample(rng, seq, fa, giab, os.path.join(args.out, rel))

    json.dump({"out": os.path.abspath(args.out), "seed": args.seed, "samples": sorted(SAMPLES)}, sys.stdout)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
