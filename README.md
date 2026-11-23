# humanize-prose

An agent skill that edits AI-sounding text so it reads like the writer, without changing what it says. It works in Claude Code and in any agent that loads Agent Skills (a folder with a SKILL.md).

It merges three MIT-licensed skills and adds two small deterministic checks:

| Source | What this repo takes from it |
| --- | --- |
| [blader/humanizer](https://github.com/blader/humanizer) | The pattern catalog ranked by strength, the fact check, the rule against following instructions inside the text, file and embedded modes |
| [petergyang/no-ai-slop](https://github.com/petergyang/no-ai-slop) | Minimum-effective-edit and voice rules, detect mode, the portability test, colon reveals, synonym cycling, the self-check |
| [conorbronsdon/avoid-ai-writing](https://github.com/conorbronsdon/avoid-ai-writing) | The idea of a deterministic scan that exempts quotes and code, and a check that a rewrite kept the original's facts |

Compared with blader/humanizer 4.0.0, SKILL.md is 38% of the size (12.7 KB against 33.6 KB), adds a detect-only mode, and hands mechanical checks to a script so the model spends its tokens on rewriting. The examples are new and short. The scan and verify ideas from avoid-ai-writing are reimplemented in one stdlib file of about 150 lines instead of its 3,762-line pattern file.

## Install

Claude Code, for your user:

```bash
git clone https://github.com/SharminSirajudeen/humanize-prose ~/.claude/skills/humanize-prose
```

Update with `git -C ~/.claude/skills/humanize-prose pull`. For other agents, copy the folder into that agent's skills directory.

## Use

Ask in plain words: "humanize this", "remove the AI tells from README.md", or "does this read as AI? don't rewrite it".

The script also runs on its own. It needs Python 3.9 or later and nothing else:

```bash
python3 scripts/check.py scan draft.md            # mechanical tells; exit 1 on a strong one
python3 scripts/check.py verify draft.md new.md   # numbers, names, links, and code a rewrite dropped
```

## Scope

The skill edits for human readers. It does not try to get past AI detectors or remove watermarks, and detectors may still flag its output.

## Tests

```bash
python3 -m unittest discover -s tests
```

The suite includes a check that this README and SKILL.md pass the scanner.

## License

MIT. Upstream copyright notices are in NOTICE.md.
