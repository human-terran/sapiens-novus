#!/usr/bin/env python3
"""Checks for draft v1.1 after the diction pass.

Compares the working sapiens-novus.md to public v1.1 (merge cede880)
for headings, per-room number multisets, and per-room formula multisets.
Compares the axiom block byte-for-byte to public v1.02.

Axiom block: the characters from "Axiom 1 —" through the character
before "**LEX 1PR:** Axioms 1–12 bind all departments." That span is
Axiom 1 through Axiom 12, including the continuation paragraphs of
Axioms 8 and 9 and the "Only two sexes exist" paragraph that closes
the axiom codex. It does not include the Pactum, the one-line codex
intro, or the Lex lines of that room.
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NEW = (ROOT / "sapiens-novus.md").read_text()

V102_PATH = Path("/tmp/sapiens-v102.md")
PRE_COMMIT = "cede880a20828f5e58135a8a9a18d422599895ca"
V102_COMMIT = "4425d45691bf1dfbfc3d3f578507510054e83111"

NUM = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?%?")
# An equality or approximation that is a formula, not a prose "is".
FORMULA = re.compile(
    r"(?:[A-ZΩΨε][A-Za-z0-9\\_ΩΨ*]{0,24}|Ω\\\*)\s*[=≈]\s*[^.\n]{1,240}"
)
# Room cite: chapter 1–9, room id, not a longer decimal and not a percent.
CITE = re.compile(r"(?<![\w.])([1-9])\.(\d{1,2})(?:\.(\d{1,2}))?(?![\d.%])")
ROMAN_CITE = re.compile(
    r"\b(VIII|VII|VI|IV|IX|V|III|II|I)\.(\d{1,2})(?:\.(\d{1,2}))?\b"
)
ROMAN = {
    "1": "I",
    "2": "II",
    "3": "III",
    "4": "IV",
    "5": "V",
    "6": "VI",
    "7": "VII",
    "8": "VIII",
    "9": "IX",
}


def git_show(rev: str) -> str:
    return subprocess.check_output(
        ["git", "show", f"{rev}:sapiens-novus.md"],
        cwd=ROOT,
        text=True,
    )


def load_pre() -> str:
    return git_show(PRE_COMMIT)


def load_v102() -> str:
    if V102_PATH.exists():
        return V102_PATH.read_text()
    return git_show(V102_COMMIT)


def rooms(text: str) -> list[tuple[str, str]]:
    lines = text.splitlines()
    heads = []
    for i, line in enumerate(lines):
        if not (line.startswith("**") and line.endswith("**") and line.count("**") == 2):
            continue
        j = i + 1
        while j < len(lines) and lines[j].strip() == "":
            j += 1
        if j < len(lines) and lines[j].startswith("###### RADIX"):
            heads.append(i)
    out = []
    for n, i in enumerate(heads):
        end = heads[n + 1] if n + 1 < len(heads) else len(lines)
        chunk = lines[i:end]
        status_at = next((k for k, ln in enumerate(chunk) if ln.startswith("Status:")), None)
        if status_at is not None:
            chunk = chunk[: status_at + 1]
        while chunk and chunk[-1].strip() == "":
            chunk.pop()
        out.append((lines[i], "\n".join(chunk)))
    return out


def norm_num(tok: str) -> str:
    """A trailing comma is punctuation. A thousands comma stays."""
    if re.fullmatch(r"\d+,", tok):
        return tok[:-1]
    return tok


def numeric_tokens(body: str) -> Counter:
    return Counter(norm_num(t) for t in NUM.findall(body))


def formulas(body: str) -> Counter:
    return Counter(FORMULA.findall(body))


def axiom_block(text: str) -> str:
    start = text.find("Axiom 1 —")
    end = text.find("**LEX 1PR:** Axioms 1–12 bind all departments.")
    if start < 0 or end < 0 or end <= start:
        raise SystemExit("axiom block markers missing")
    return text[start:end]


def headings(text: str) -> list[str]:
    found = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if not (line.startswith("**") and line.endswith("**") and line.count("**") == 2):
            continue
        j = i + 1
        while j < len(lines) and lines[j].strip() == "":
            j += 1
        if j < len(lines) and lines[j].startswith("###### RADIX"):
            found.append(line[2:-2])
    return found


def cite_resolves(ch: str, minor: str, sub: str, heads: list[str]) -> bool:
    pref = f"{ROMAN[ch]}.{minor}" + (f".{sub}" if sub else "")
    if any(h.startswith(pref) for h in heads):
        return True
    # Chapter I writes its rooms as Roman headings: 1.5 is V. Modularity,
    # 1.7 is VII. Entityhood, 1.8 is VIII. Holographic Root, 1.6 is I.6
    # (and is also the ambiguous cite of VI. Terminology).
    if ch == "1":
        aliases = {
            "2": "II. ",
            "3": "III. ",
            "4": "IV. ",
            "5": "V. ",
            "6": "I.6",
            "7": "VII. ",
            "8": "VIII. ",
            "9": "I.9",
            "10": "I.10",
        }
        alias = aliases.get(minor)
        if alias and any(h.startswith(alias) for h in heads):
            return True
        if minor == "6" and any(h.startswith("VI. ") for h in heads):
            return True
    return False


def roman_resolves(rom: str, minor: str, sub: str, heads: list[str]) -> bool:
    pref = f"{rom}.{minor}" + (f".{sub}" if sub else "")
    if any(h.startswith(pref) for h in heads):
        return True
    # "I.8" in the new rooms means chapter I, room VIII (Holographic Root).
    if rom == "I" and minor == "8" and any(h.startswith("VIII. ") for h in heads):
        return True
    if rom == "I" and minor == "7" and any(h.startswith("VII. ") for h in heads):
        return True
    if rom == "I" and minor == "5" and any(h.startswith("V. ") for h in heads):
        return True
    if rom == "I" and minor == "6" and any(h.startswith("I.6") or h.startswith("VI. ") for h in heads):
        return True
    return False


def is_scalar(ch: str, minor: str, text_has: str) -> bool:
    """Frequencies and bounds that look like cites: 7.83 Hz, 2.0."""
    token = f"{ch}.{minor}"
    if token == "2.0":
        return True
    if token == "7.83" or (ch == "7" and minor == "83"):
        return True
    return False


def main() -> int:
    pre = load_pre()
    v102 = load_v102()
    report: list[str] = []
    fail = 0

    old_rooms = rooms(pre)
    new_rooms = rooms(NEW)
    old_map = {h: b for h, b in old_rooms}
    new_map = {h: b for h, b in new_rooms}

    missing = [h for h in old_map if h not in new_map]
    extra = [h for h in new_map if h not in old_map]
    report.append(f"rooms_before {len(old_map)}")
    report.append(f"rooms_after {len(new_map)}")
    report.append(f"missing_headings {len(missing)}")
    report.append(f"extra_headings {len(extra)}")
    for h in missing:
        report.append(f"MISSING {h}")
    for h in extra:
        report.append(f"EXTRA {h}")
    if missing or extra:
        fail += 1

    num_bad = []
    form_bad = []
    for h, body in old_rooms:
        if h not in new_map:
            continue
        nb = new_map[h]
        if numeric_tokens(body) != numeric_tokens(nb):
            num_bad.append(h)
            report.append(f"NUM {h}")
            report.append(f"  only_before {numeric_tokens(body) - numeric_tokens(nb)}")
            report.append(f"  only_after {numeric_tokens(nb) - numeric_tokens(body)}")
        if formulas(body) != formulas(nb):
            # Require every old formula string to survive. A new wording
            # may split a line; it may not drop or alter a formula.
            lost = formulas(body) - formulas(nb)
            if lost:
                form_bad.append(h)
                report.append(f"FORMULA {h} lost {list(lost.elements())[:4]}")
    report.append(f"numeric_mismatch_rooms {len(num_bad)}")
    report.append(f"formula_mismatch_rooms {len(form_bad)}")
    if num_bad or form_bad:
        fail += 1

    ax_new = axiom_block(NEW)
    ax_old = axiom_block(v102)
    ax_pre = axiom_block(pre)
    report.append("axiom_block_vs_v102 " + ("MATCH" if ax_new == ax_old else "DIFFER"))
    report.append("axiom_block_vs_predication " + ("MATCH" if ax_new == ax_pre else "DIFFER"))
    report.append(f"axiom_block_bytes {len(ax_new)}")
    if ax_new != ax_old or ax_new != ax_pre:
        fail += 1

    report.append(
        f"status_locked_before {pre.count('Status: **LOCKED**')} after {NEW.count('Status: **LOCKED**')}"
    )
    report.append(
        f"status_proposed_before {pre.count('Status: **PROPOSED**')} after {NEW.count('Status: **PROPOSED**')}"
    )
    if pre.count("Status: **LOCKED**") != NEW.count("Status: **LOCKED**"):
        fail += 1
        report.append("LOCKED COUNT CHANGED")
    if pre.count("Status: **PROPOSED**") != NEW.count("Status: **PROPOSED**"):
        fail += 1
        report.append("PROPOSED COUNT CHANGED")

    heads = headings(NEW)
    unresolved = []
    scalars = []
    for ch, minor, sub in set(CITE.findall(NEW)):
        if is_scalar(ch, minor, NEW):
            scalars.append(f"{ch}.{minor}")
            continue
        if not cite_resolves(ch, minor, sub, heads):
            unresolved.append(f"{ch}.{minor}" + (f".{sub}" if sub else ""))
    for rom, minor, sub in set(ROMAN_CITE.findall(NEW)):
        if not roman_resolves(rom, minor, sub, heads):
            unresolved.append(f"{rom}.{minor}" + (f".{sub}" if sub else ""))
    report.append(f"cross_references_unresolved {len(unresolved)}")
    for item in sorted(set(unresolved)):
        report.append(f"UNRESOLVED {item}")
    report.append("scalars_not_cites " + ", ".join(sorted(set(scalars))))
    if unresolved:
        fail += 1

    # Markdown structure.
    lines = NEW.splitlines()
    swallowed = []
    merged = []
    for i, line in enumerate(lines):
        if line.startswith("Status:") and i > 0 and lines[i - 1].startswith("|"):
            swallowed.append(i + 1)
        if line.startswith("Status:") and i + 1 < len(lines) and lines[i + 1].startswith("#"):
            merged.append(i + 1)
    table_err = 0
    i = 0
    while i < len(lines):
        if lines[i].startswith("|"):
            block = []
            while i < len(lines) and lines[i].startswith("|"):
                block.append(lines[i])
                i += 1
            counts = [ln.count("|") for ln in block]
            if len(set(counts)) != 1:
                table_err += 1
                report.append(f"TABLE cols {counts[:6]} :: {block[0][:60]}")
            if not any("---" in ln for ln in block):
                table_err += 1
                report.append(f"TABLE no separator {block[0][:60]}")
        else:
            i += 1
    report.append(f"status_swallowed_by_table {len(swallowed)}")
    report.append(f"status_then_heading {len(merged)}")
    report.append(f"table_errors {table_err}")
    if swallowed or merged or table_err:
        fail += 1

    try:
        import markdown

        html = markdown.markdown(NEW, extensions=["tables", "sane_lists"])
        report.append(
            f"markdown_render html_chars={len(html)} h1={html.count('<h1')} tables={html.count('<table')}"
        )
        if html.count("<h1") != 14 or html.count("<table") != 2:
            report.append("MARKDOWN SHAPE UNEXPECTED")
            fail += 1
    except ImportError:
        report.append("markdown_render SKIPPED (package missing)")

    if lines[1] != "**Public Release v1.11**":
        report.append(f"VERSION {lines[1]!r}")
        fail += 1
    else:
        report.append("version_line ok")

    # VCI weights still the locked string.
    weight = "0.40 E\\_net + 0.25 B\\_success + 0.20 T\\_value + 0.15 I\\_built"
    report.append("vci_weights " + ("present" if weight in NEW else "MISSING"))
    if weight not in NEW:
        fail += 1

    report.append(f"fail {fail}")
    out = Path("/tmp/sapiens-v11-diction-audit.txt")
    out.write_text("\n".join(report) + "\n")
    print("\n".join(report))
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
