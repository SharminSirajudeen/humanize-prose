# Evaluation

A head-to-head test of humanize-prose against blader/humanizer 4.0.0 (commit `a32f244`, copied unchanged into `skills/`).

## Method

1. `prompts.txt` holds 20 neutral writing prompts across genres: LinkedIn posts, product copy, cold email, a cover letter, a README, release notes, a support reply, and others. Each names facts a rewrite must keep (people, places, numbers, dates) and asks for a length. None asks for a style.
2. `run.py` has Claude Code write one sample per prompt with the system prompt "You are a helpful assistant.", then rewrite each sample once with each skill.
3. Each call uses the same model and the same wrapper message. The skill file is the entire system prompt. Tools, skills, slash commands, MCP servers, saved sessions, and user settings are all off. Both skills are asked for embedded mode, where each returns only the final text. With no tools, humanize-prose's `scripts/check.py` steps cannot run, so this tests the instructions alone.
4. `score.py` counts tells with this repo's `scripts/check.py` and again with the detector from [avoid-ai-writing](https://github.com/conorbronsdon/avoid-ai-writing). The second count matters because check.py was written alongside humanize-prose. It also counts numbers, names, links, and code from each sample that a rewrite dropped, and records the tokens each run used.

One rewrite per sample per skill, so expect some run-to-run variation.

## Files

- `results.md`: the summary and per-sample tables.
- `outputs.md`: every sample and both rewrites, unedited, to judge by reading.
- `results.json`: per-sample measurements.
- `raw/`: one trimmed JSON record per call.

## Rerun

```bash
python3 evals/run.py --model sonnet          # needs Claude Code; skips calls already in raw/
python3 evals/score.py --detector ../avoid-ai-writing/detector/patterns.js
```
