#!/usr/bin/env python3
"""Generate AI-written samples, then rewrite each one with both skills through Claude Code.

  python3 evals/run.py [--model sonnet] [--workers 4]

Every call runs from an empty directory with the given text as the whole system prompt, no tools,
no skills or slash commands, no MCP servers, no saved session, and no user settings. Results go to
evals/raw/ as trimmed JSON. Existing files are skipped, so rerunning resumes an interrupted run.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
ARMS = {
    "blader": HERE / "skills" / "blader-humanizer-4.0.0.md",
    "humanize-prose": HERE.parent / "SKILL.md",
}
GENERATOR = "You are a helpful assistant."
WRAPPER = (
    "Edit the text between the markers using your instructions. This is embedded use: return only the "
    "final edited text, with no preamble, notes, or list of changes.\n\n<<<TEXT\n{text}\nTEXT>>>"
)
FLAGS = ["--tools", "", "--disable-slash-commands", "--strict-mcp-config", "--no-session-persistence",
         "--setting-sources", "local", "--output-format", "json"]


def call(claude: str, model: str, cwd: str, system: str, prompt: str, out: Path) -> None:
    """Run one print-mode call and save the text, model, timing, and token counts."""
    if out.exists():
        return
    try:
        proc = subprocess.run([claude, "-p", prompt, "--model", model, "--system-prompt", system, *FLAGS],
                              cwd=cwd, capture_output=True, text=True, timeout=600)
        data = json.loads(proc.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError) as error:
        out.with_suffix(".err").write_text(f"{error}\n", encoding="utf-8")
        print(f"failed {out.name}: {type(error).__name__}", flush=True)
        return
    usage = data.get("usage", {})
    record = {
        "result": data.get("result", ""),
        "is_error": data.get("is_error", True),
        "model": next(iter(data.get("modelUsage", {})), "unknown"),
        "duration_ms": data.get("duration_ms"),
        "input_tokens": sum(usage.get(k, 0) for k in
                            ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")),
        "output_tokens": usage.get("output_tokens", 0),
    }
    out.write_text(json.dumps(record, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{'error' if record['is_error'] else 'ok'} {out.name}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="sonnet")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    claude = shutil.which("claude")
    if not claude:
        sys.exit("claude is not on PATH")
    RAW.mkdir(exist_ok=True)
    prompts = [line for line in (HERE / "prompts.txt").read_text(encoding="utf-8").splitlines() if line.strip()]
    samples = [RAW / f"sample-{n:02d}.json" for n in range(1, len(prompts) + 1)]
    skills = {arm: path.read_text(encoding="utf-8") for arm, path in ARMS.items()}
    with tempfile.TemporaryDirectory() as cwd, ThreadPoolExecutor(args.workers) as pool:
        list(pool.map(lambda job: call(claude, args.model, cwd, GENERATOR, *job), zip(prompts, samples)))
        jobs = [(skills[arm], WRAPPER.format(text=json.loads(sample.read_text(encoding="utf-8"))["result"]),
                 RAW / f"{arm}-{sample.stem.split('-')[1]}.json")
                for sample in samples if sample.exists() for arm in ARMS]
        list(pool.map(lambda job: call(claude, args.model, cwd, *job), jobs))
    version = subprocess.run([claude, "--version"], capture_output=True, text=True).stdout.strip()
    (RAW / "meta.json").write_text(json.dumps({"claude_code": version, "model_alias": args.model}) + "\n",
                                   encoding="utf-8")
    print("done", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
