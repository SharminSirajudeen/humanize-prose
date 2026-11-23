import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import check  # noqa: E402


def names(text):
    return {(strength, name) for _, strength, name, _ in check.scan(text)}


def run(*argv):
    with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()):
        code = check.main(list(argv))
    return code, out.getvalue()


class ScanFlags(unittest.TestCase):
    def test_strong_tells(self):
        cases = {
            "The plan \u2014 announced today \u2014 is late.": "dash",
            "The changes -- long overdue -- start now.": "dash",
            "It's not just about speed, it's about trust.": "contrast",
            "This is not a tool. It's a mirror.": "contrast",
            "We want not only speed but also accuracy.": "contrast",
            "This does not mean every choice is equal. It means no one checks.": "contrast",
            "Caching isn't just a trick \u2014 it's a strategy.": "contrast",
            "Here's the thing: caching is hard.": "staged opener",
            "Is it worth it? Honestly? It depends.": "staged opener",
            "That is the real win.": "reader steering",
            "Let's delve into the data.": "stock word",
            "The town has a rich tapestry of cultures.": "stock word",
            "It plays a key role in the region.": "inflated significance",
            "Great question! The answer is 4.": "chatbot residue",
            "Certainly! Here it is.": "chatbot residue",
            "Her early life is not publicly documented.": "knowledge-limit hedge",
            "## \U0001f680 Launch Plan": "decorated heading",
        }
        for text, rule in cases.items():
            with self.subTest(text=text):
                self.assertIn(("strong", rule), names(text))

    def test_weak_tells(self):
        cases = {
            "In conclusion, the team shipped.": "recap opener",
            "Experts say the river matters.": "borrowed authority",
            "The hotel is nestled in the hills.": "sales language",
            "The gallery serves as a hub.": "verb avoidance",
            "He said \u201cyes\u201d twice.": "curly quotes",
            "## Strategic Negotiations And Partnerships": "title-case heading",
            "- **Speed:** faster builds": "bold label",
        }
        for text, rule in cases.items():
            with self.subTest(text=text):
                self.assertIn(("weak", rule), names(text))

    def test_curly_apostrophe_is_normalized_for_rules(self):
        self.assertIn(("strong", "contrast"), names("It\u2019s not a bug, it\u2019s a feature."))


class ScanExemptions(unittest.TestCase):
    def test_exempt_regions(self):
        text = "\n".join([
            "---",
            "description: delve into the tapestry \u2014 fast",
            "---",
            "Use `--delve` with care.",
            "See https://example.com/delve--tapestry for details.",
            "> Let's delve into it \u2014 a quoted example.",
            'He wrote "a rich tapestry" in the draft.',
            "```",
            "x = 1  # not just code -- but it's code",
            "```",
            "The build takes four minutes.",
        ])
        self.assertEqual(check.scan(text), [])

    def test_clean_human_text_exits_zero(self):
        text = "I moved the cache in front of the database. Reads dropped from 40 ms to 4 ms.\n"
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write(text)
        code, out = run("scan", f.name)
        self.assertEqual(code, 0)
        self.assertIn("0 strong, 0 weak", out)

    def test_strong_tell_exits_one(self):
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write("I hope this helps!\n")
        self.assertEqual(run("scan", f.name)[0], 1)


class Verify(unittest.TestCase):
    ORIGINAL = (
        "The institute was founded in 1989 by Maria Lopez in Barcelona.\n"
        "It has 3,000 square feet and runs `make test` nightly. Docs: https://example.com/docs.\n"
    )

    def test_reports_missing_items(self):
        rewrite = "The institute opened in Barcelona. It runs nightly tests."
        missing = set(check.verify(self.ORIGINAL, rewrite))
        self.assertTrue({("number", "1989"), ("name", "Maria"), ("name", "Lopez"), ("number", "3000"),
                         ("code", "`make test`"), ("link", "https://example.com/docs")} <= missing)
        self.assertNotIn(("name", "Barcelona"), missing)

    def test_faithful_rewrite_passes(self):
        rewrite = (
            "Maria Lopez founded the institute in Barcelona in 1989. It has 3000 square feet "
            "and runs `make test` every night (docs: https://example.com/docs)."
        )
        self.assertEqual(check.verify(self.ORIGINAL, rewrite), [])

    def test_sentence_start_words_are_not_names(self):
        original = "## Setup\nFirst install it. Then run it.\n- Next step here."
        self.assertEqual(check.verify(original, "Install it, then run it."), [])

    def test_headings_and_bold_labels_are_not_names(self):
        original = "# Unlocking The Power Of Caching\n- **Reliability:** Fewer outages at Northwind.\n"
        self.assertEqual(check.verify(original, "Caching gave fewer outages."), [("name", "Northwind")])

    def test_acronyms_count_anywhere(self):
        self.assertIn(("name", "SynthID"), check.verify("SynthID marks images.", "The marks stay."))

    def test_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d, "a.md"), Path(d, "b.md")
            a.write_text("Paid 250 dollars to Acme Corp.", encoding="utf-8")
            b.write_text("Paid 250 dollars to Acme Corp.", encoding="utf-8")
            self.assertEqual(run("verify", str(a), str(b))[0], 0)
            b.write_text("Paid the vendor.", encoding="utf-8")
            self.assertEqual(run("verify", str(a), str(b))[0], 1)
        self.assertEqual(run("bogus")[0], 2)


class Dogfood(unittest.TestCase):
    def test_own_docs_have_no_strong_tells(self):
        for name in ("SKILL.md", "README.md"):
            with self.subTest(file=name):
                strong = [f for f in check.scan((ROOT / name).read_text(encoding="utf-8")) if f[1] == "strong"]
                self.assertEqual(strong, [])


if __name__ == "__main__":
    unittest.main()
