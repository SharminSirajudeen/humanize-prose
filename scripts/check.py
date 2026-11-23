#!/usr/bin/env python3
"""Deterministic checks for the humanize-prose skill. Stdlib only.

  check.py scan [FILE]              flag mechanical AI-writing tells (reads stdin without FILE)
  check.py verify ORIGINAL REWRITE  list numbers, names, links, and code from ORIGINAL missing in REWRITE

Scan skips front matter, fenced code, inline code, URLs, blockquotes, and quoted spans.
Exit status is 1 when scan finds a strong tell or verify finds a missing item, 2 on bad usage.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_I = re.IGNORECASE
_M = re.IGNORECASE | re.MULTILINE

# (name, strength, pattern). A strong tell justifies an edit on one sighting; a weak one needs company.
RULES = [
    ("dash", "strong", re.compile(r"\u2014|(?<![\d%]) \u2013 (?![\d$\u00a3\u20ac])| -- ")),  # ranges like 3 \u2013 5 pass
    ("contrast", "strong", re.compile(
        r"\bnot (?:just|only|merely) [^.!?]{1,80}?\bbut\b"
        r"|\b(?:it's|it is|this is|that's|that is) not\b[^.!?]{1,60}?(?:[,;:.]| ?\u2014| \u2013| --) *(?:it's|it is|this is|that's|that is|but)\b"
        r"|\b(?:isn't|aren't|wasn't) [^.!?]{1,60}?(?:[,;:.]| ?\u2014| \u2013| --) *(?:it's|it is|this is|they're)\b"
        r"|\b(?:does not|doesn't) mean [^.!?]{1,80}[.!?] +(?:it|this) means\b", _I)),
    ("staged opener", "strong", re.compile(
        r"(?:^|[.!?] +)(?:here's (?:the thing|what you need to know|what nobody tells you)"
        r"|let's (?:dive|explore|break (?:this|it) down|be honest)|honestly\?|real talk|the thing is"
        r"|without further ado|what if i told you|plot twist|think about it:|what most people (?:get wrong|miss))", _M)),
    ("reader steering", "strong", re.compile(
        r"\b(?:let that sink in|read that again|this distinction matters|that's the real win|that is the real win"
        r"|the key (?:takeaway|point) (?:is|here)|as you can see|it's (?:worth|important to) not(?:e|ing))\b", _I)),
    ("inflated significance", "strong", re.compile(
        r"\b(?:stands as a testament|a testament to|pivotal (?:moment|role)|plays? an? (?:key|vital|crucial|pivotal) role"
        r"|setting the stage|evolving landscape|indelible mark|the future looks bright|exciting times (?:lie )?ahead)\b", _I)),
    ("stock word", "strong", re.compile(
        r"\b(?:delv(?:e|es|ed|ing)|tapestry|multifaceted|realm|paramount|meticulous(?:ly)?|intricate|intricacies"
        r"|vibrant|embark(?:s|ed|ing)?|ever-evolving|game[- ]changer|cutting-edge|seamless(?:ly)?"
        r"|leverag(?:e|es|ed|ing)|utiliz(?:e|es|ed|ing)|foster(?:s|ed|ing)?|underscor(?:e|es|ed|ing)"
        r"|showcas(?:e|es|ed|ing)|transformative|bolster(?:s|ed|ing)?|garner(?:s|ed|ing)?|interplay)\b", _I)),
    ("chatbot residue", "strong", re.compile(
        r"\b(?:great question|i hope this helps|let me know if you(?:'d| would)? like|happy to help"
        r"|would you like me to|feel free to (?:ask|reach out)|as an ai)\b|^(?:certainly|of course|absolutely)!", _M)),
    ("knowledge-limit hedge", "strong", re.compile(
        r"\b(?:as of my (?:last|latest) (?:update|training)|my (?:knowledge|training) cutoff"
        r"|not (?:widely|publicly|extensively) (?:documented|available|disclosed)|based on (?:the )?available information)\b", _I)),
    ("recap opener", "weak", re.compile(r"^(?:in conclusion|ultimately|overall|in summary|to sum up)\b", _M)),
    ("borrowed authority", "weak", re.compile(
        r"\b(?:experts (?:say|agree|argue|believe)|studies (?:show|suggest)|industry reports|widely regarded"
        r"|many (?:argue|believe))\b", _I)),
    ("sales language", "weak", re.compile(
        r"\b(?:nestled|in the heart of|breathtaking|must-visit|rich (?:cultural )?heritage|stunning)\b", _I)),
    ("verb avoidance", "weak", re.compile(r"\b(?:serves as|stands as|functions as|boasts)\b", _I)),
]
CURLY_QUOTES = re.compile("[\u201c\u201d]")
HEADING = re.compile(r"^#{1,6}\s+(.+)$")
BOLD_LABEL = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+\*\*[^*]{1,60}?(?::\*\*|\*\*\s*:)")
DECORATION = re.compile("[\u2192\u2600-\u27bf\U0001f300-\U0001faff]")
FENCE = re.compile(r"^\s*(?:```|~~~)")
INLINE_CODE = re.compile(r"`[^`\n]+`")
URL = re.compile(r"https?://[^\s)>\]]+")
QUOTED = re.compile("\"[^\"\n]*\"|\u201c[^\u201d\n]*\u201d")


def prose_lines(text: str):
    """Yield (line number, line without code and URLs) for lines that are prose."""
    skip_until = None  # "fence" inside a code block, "---" inside front matter
    for number, line in enumerate(text.splitlines(), 1):
        if skip_until:
            if FENCE.match(line) if skip_until == "fence" else line.strip() == "---":
                skip_until = None
        elif number == 1 and line.strip() == "---":
            skip_until = "---"
        elif FENCE.match(line):
            skip_until = "fence"
        elif not line.lstrip().startswith(">"):
            yield number, URL.sub(" ", INLINE_CODE.sub(" ", line))


def scan(text: str) -> list[tuple[int, str, str, str]]:
    findings = []
    for number, line in prose_lines(text):
        prose = QUOTED.sub(" ", line.replace("\u2019", "'"))
        for name, strength, pattern in RULES:
            findings += [(number, strength, name, m.group(0).strip().lstrip(".!? ")) for m in pattern.finditer(prose)]
        findings += [(number, "weak", "curly quotes", m.group(0)) for m in CURLY_QUOTES.finditer(line)]
        heading = HEADING.match(prose)
        if heading and DECORATION.search(heading.group(1)):
            findings.append((number, "strong", "decorated heading", heading.group(1).strip()))
        elif heading and _title_case(heading.group(1)):
            findings.append((number, "weak", "title-case heading", heading.group(1).strip()))
        if BOLD_LABEL.match(prose):
            findings.append((number, "weak", "bold label", prose.strip()[:60]))
    return findings


def _title_case(heading: str) -> bool:
    long_words = [w for w in re.findall(r"[A-Za-z]+", heading) if len(w) > 3]
    return len(long_words) >= 2 and all(w[0].isupper() for w in long_words)


def facts(text: str) -> set[tuple[str, str]]:
    """Numbers, names, links, and inline code a rewrite must keep."""
    items = {("link", u.rstrip(".,;:")) for u in URL.findall(text)}
    items |= {("code", c) for c in INLINE_CODE.findall(text)}
    plain = URL.sub(" ", INLINE_CODE.sub(" ", text)).replace("*", "")
    items |= {("number", n.rstrip(",").replace(",", "")) for n in re.findall(r"\d[\d,]*(?:\.\d+)?", plain)}
    for line in plain.splitlines():
        if HEADING.match(line):  # Title Case headings would read as names
            continue
        for m in re.finditer(r"\b[A-Z][\w'-]+", line):
            word = m.group(0).removesuffix("'s")
            prefix = DECORATION.sub("", line[: m.start()])
            starts_sentence = not prefix.strip(" \t-+>0123456789.()\"\u201c") or prefix.rstrip()[-1:] in ".!?:"
            if not starts_sentence or re.search(r"[A-Z0-9]", word[1:]):  # acronyms and CamelCase anywhere
                items.add(("name", word))
    return items


def verify(original: str, rewrite: str) -> list[tuple[str, str]]:
    """Items from ORIGINAL absent in REWRITE. Numbers ignore thousands separators; names ignore case."""
    numbers = {value for kind, value in facts(rewrite) if kind == "number"}
    lowered = rewrite.lower()

    def kept(kind: str, value: str) -> bool:
        if kind == "number":
            return value in numbers
        return value.lower() in lowered if kind == "name" else value in rewrite

    return sorted(item for item in facts(original) if not kept(*item))


def main(argv: list[str]) -> int:
    if argv[:1] == ["scan"] and len(argv) <= 2:
        text = Path(argv[1]).read_text(encoding="utf-8") if len(argv) == 2 else sys.stdin.read()
        findings = scan(text)
        for number, strength, name, match in findings:
            print(f"{number}: {strength} {name}: {match}")
        strong = sum(f[1] == "strong" for f in findings)
        print(f"{strong} strong, {len(findings) - strong} weak")
        return 1 if strong else 0
    if argv[:1] == ["verify"] and len(argv) == 3:
        missing = verify(*(Path(path).read_text(encoding="utf-8") for path in argv[1:]))
        for kind, value in missing:
            print(f"missing {kind}: {value}")
        print(f"{len(missing)} missing" if missing else "all numbers, names, links, and code kept")
        return 1 if missing else 0
    print(__doc__.strip(), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
