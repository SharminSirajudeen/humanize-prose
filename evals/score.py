#!/usr/bin/env python3
"""Score evals/raw/ into evals/results.md, evals/results.json, and evals/outputs.md.

  python3 evals/score.py [--detector PATH]

PATH is detector/patterns.js from https://github.com/conorbronsdon/avoid-ai-writing, an independent
scorer run with Node. Without it, only this repo's scripts/check.py scores the texts.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from statistics import mean

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import check  # noqa: E402

ARMS = ("blader", "humanize-prose")
COLUMNS = ("original", *ARMS)
HEADERS = ("Original", "blader/humanizer", "humanize-prose")
DETECT_JS = (
    "const D=require(process.argv[1]);const t=JSON.parse(require('fs').readFileSync(0,'utf8'));"
    "console.log(JSON.stringify(t.map(x=>{const r=D.analyzeText(x);return [r.score,r.issues.length]})))"
)


def load(name: str) -> dict | None:
    path = HERE / "raw" / f"{name}.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    return data if data and not data["is_error"] and data["result"].strip() else None


def measure(text: str, original: str | None) -> dict:
    findings = check.scan(text)
    strong = sum(f[1] == "strong" for f in findings)
    row = {"strong": strong, "weak": len(findings) - strong, "words": len(text.split())}
    if original is not None:
        row["dropped"] = len(check.verify(original, text))
    return row


def collect() -> list[dict]:
    rows = []
    for path in sorted((HERE / "raw").glob("sample-*.json")):
        n = path.stem.split("-")[1]
        records = {"original": load(f"sample-{n}"), **{arm: load(f"{arm}-{n}") for arm in ARMS}}
        if None in records.values():
            print(f"skipping sample {n}: a call failed or returned nothing", file=sys.stderr)
            continue
        original = records["original"]["result"]
        metrics = {k: measure(r["result"], None if k == "original" else original) for k, r in records.items()}
        for arm in ARMS:
            metrics[arm].update(input_tokens=records[arm]["input_tokens"], output_tokens=records[arm]["output_tokens"])
        rows.append({"sample": n, "model": records["original"]["model"],
                     "texts": {k: r["result"] for k, r in records.items()}, "metrics": metrics})
    return rows


def add_detector(rows: list[dict], detector: str) -> None:
    texts = [row["texts"][k] for row in rows for k in COLUMNS]
    out = subprocess.run(["node", "-e", DETECT_JS, detector], input=json.dumps(texts),
                         capture_output=True, text=True, check=True)
    scores = iter(json.loads(out.stdout))
    for row in rows:
        for k in COLUMNS:
            row["metrics"][k]["detector_score"], row["metrics"][k]["detector_findings"] = next(scores)


def summary(rows: list[dict], detected: bool) -> list[str]:
    def total(key, k): return f"{sum(r['metrics'][k][key] for r in rows):,}"
    def average(key, k): return f"{mean(r['metrics'][k][key] for r in rows):,.1f}"
    def tokens(key, k): return f"{mean(r['metrics'][k][key] for r in rows):,.0f}"
    def dropped_any(_, k): return str(sum(r["metrics"][k]["dropped"] > 0 for r in rows))
    measures = [("Strong tells (check.py), total", "strong", total, COLUMNS),
                ("Weak tells (check.py), total", "weak", total, COLUMNS)]
    if detected:
        measures += [("avoid-ai-writing findings, total", "detector_findings", total, COLUMNS),
                     ("avoid-ai-writing score, mean (0 is clean)", "detector_score", average, COLUMNS)]
    measures += [("Facts dropped (numbers, names, links, code), total", "dropped", total, ARMS),
                  ("Samples with at least one fact dropped", "dropped", dropped_any, ARMS),
                  ("Words, mean", "words", average, COLUMNS),
                  ("Input tokens per run, mean", "input_tokens", tokens, ARMS),
                  ("Output tokens per run, mean", "output_tokens", tokens, ARMS)]
    lines = ["| Measure | " + " | ".join(HEADERS) + " |", "| --- | ---: | ---: | ---: |"]
    for label, key, agg, cols in measures:
        lines.append(f"| {label} | " + " | ".join(agg(key, k) if k in cols else "n/a" for k in COLUMNS) + " |")
    return lines


def head_to_head(rows: list[dict], key: str) -> str:
    diffs = [r["metrics"]["humanize-prose"][key] - r["metrics"]["blader"][key] for r in rows]
    return (f"fewer in {sum(d < 0 for d in diffs)}, the same in {sum(d == 0 for d in diffs)}, "
            f"more in {sum(d > 0 for d in diffs)}")


def write_results(rows: list[dict], detected: bool) -> None:
    meta_path = HERE / "raw" / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    models = ", ".join(sorted({r["model"] for r in rows}))
    keys = [("Strong tells", "strong")] + ([("avoid-ai-writing findings", "detector_findings")] if detected else [])
    keys.append(("Facts dropped", "dropped"))
    lines = ["# Results", "",
             f"Generated by `evals/score.py` from `evals/raw/`. Model: {models} through "
             f"{meta.get('claude_code', 'Claude Code')}. Samples scored: {len(rows)}.", "",
             *summary(rows, detected), "",
             "Per sample, humanize-prose against blader/humanizer:", ""]
    lines += [f"- {label}: {head_to_head(rows, key)}." for label, key in keys]
    cols = "Strong tells" + (" | avoid-ai-writing findings" if detected else "")
    lines += ["", "## Per sample", "",
              "Tells show original / blader / humanize-prose. Facts dropped show blader / humanize-prose.", "",
              f"| Sample | {cols} | Facts dropped |", "| --- | --- |" + (" --- |" if detected else "") + " --- |"]
    for r in rows:
        m = r["metrics"]
        cells = [" / ".join(str(m[k]["strong"]) for k in COLUMNS)]
        if detected:
            cells.append(" / ".join(str(m[k]["detector_findings"]) for k in COLUMNS))
        cells.append(" / ".join(str(m[k]["dropped"]) for k in ARMS))
        lines.append(f"| {r['sample']} | " + " | ".join(cells) + " |")
    (HERE / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    slim = [{k: r[k] for k in ("sample", "model", "metrics")} for r in rows]
    (HERE / "results.json").write_text(json.dumps(slim, indent=1) + "\n", encoding="utf-8")
    prompts = (HERE / "prompts.txt").read_text(encoding="utf-8").splitlines()
    out = ["# Outputs", "", "Every sample and both rewrites, unedited. Prompts are in prompts.txt.", ""]
    for r in rows:
        out += [f"## Sample {r['sample']}", "", f"Prompt: {prompts[int(r['sample']) - 1]}", ""]
        for k, header in zip(COLUMNS, HEADERS):
            out += [f"### {header}", "", "````text", r["texts"][k].strip(), "````", ""]
    (HERE / "outputs.md").write_text("\n".join(out), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--detector", help="path to avoid-ai-writing's detector/patterns.js")
    args = parser.parse_args()
    rows = collect()
    if not rows:
        sys.exit("no complete samples in evals/raw/")
    if args.detector:
        add_detector(rows, args.detector)
    write_results(rows, bool(args.detector))
    print((HERE / "results.md").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
