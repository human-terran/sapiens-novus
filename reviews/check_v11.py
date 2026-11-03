#!/usr/bin/env python3
"""Meaning-preservation checks: v1.02 baseline vs draft v1.1.

Baseline is /tmp/sapiens-v102.md when present, else git show of v1.02.
Writes a machine-readable summary to reviews/_audit.txt
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NEW = (ROOT / "sapiens-novus.md").read_text()
base_path = Path("/tmp/sapiens-v102.md")
if base_path.exists():
    OLD = base_path.read_text()
else:
    OLD = subprocess.check_output(
        ["git", "show", "4425d45691bf1dfbfc3d3f578507510054e83111:sapiens-novus.md"],
        cwd=ROOT,
        text=True,
    )

NUM = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?%?")
FORMULA_MARK = ("=", "∫", "Ω", "Ψ", "ε", "κ", "λ", "Φ")


def rooms(text: str) -> list[tuple[str, str]]:
    """Return (heading, body through Status line) for each room.

    A room heading is a bold line whose next non-empty line is a RADIX breadcrumb.
    """
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
        # A room's operative text ends at its Status line. Chapter leads
        # and later rooms are not part of the byte-compare.
        status_at = None
        for k, ln in enumerate(chunk):
            if ln.startswith("Status:"):
                status_at = k
                break
        if status_at is not None:
            chunk = chunk[: status_at + 1]
        while chunk and chunk[-1].strip() == "":
            chunk.pop()
        body = "\n".join(chunk)
        out.append((lines[i], body))
    return out


def numeric_tokens(body: str) -> Counter:
    return Counter(NUM.findall(body))


def formula_lines(body: str) -> list[str]:
    return [ln for ln in body.splitlines() if any(m in ln for m in FORMULA_MARK)]


def main() -> int:
    old_rooms = rooms(OLD)
    new_rooms = rooms(NEW)
    old_map = {h: b for h, b in old_rooms}
    new_map = {h: b for h, b in new_rooms}

    report: list[str] = []
    fail = 0

    missing = [h for h in old_map if h not in new_map]
    report.append(f"old_rooms {len(old_map)}")
    report.append(f"new_rooms {len(new_map)}")
    report.append(f"missing_old_headings {len(missing)}")
    for h in missing:
        report.append(f"MISSING {h}")
        fail += 1

    added = [h for h in new_map if h not in old_map]
    report.append(f"added_headings {len(added)}")
    for h in added:
        report.append(f"ADDED {h}")

    # Order of old headings preserved (IX.2 and IX.3 may swap).
    old_heads = [h for h, _ in old_rooms]
    new_heads = [h for h, _ in new_rooms if h in old_map]
    # Expected: IX.2 before IX.3, otherwise same relative order.
    def norm_order(hs: list[str]) -> list[str]:
        return hs

    # Compare pairwise order ignoring the IX.2/IX.3 swap.
    def strip_ix(hs: list[str]) -> list[str]:
        return [h for h in hs if h not in ("**IX.2 QAT**", "**IX.3 Cycle**")]

    if strip_ix(old_heads) != strip_ix(new_heads):
        report.append("ORDER DRIFT (excluding IX.2/IX.3)")
        fail += 1
        for a, b in zip(strip_ix(old_heads), strip_ix(new_heads)):
            if a != b:
                report.append(f"  first {a} vs {b}")
                break
    else:
        report.append("order_preserved_except_IX2_IX3 yes")

    ix_new = [h for h, _ in new_rooms if h.startswith("**IX.")]
    report.append("ix_order " + " | ".join(ix_new))
    if ix_new[:3] != ["**IX.1 Master Formula**", "**IX.2 QAT**", "**IX.3 Cycle**"]:
        report.append("IX ORDER FAIL")
        fail += 1

    num_mismatch = []
    formula_mismatch = []
    byte_diff = []
    allowed_heading_prefix = None

    for h, ob in old_map.items():
        nb = new_map.get(h)
        if nb is None:
            continue
        if numeric_tokens(ob) != numeric_tokens(nb):
            num_mismatch.append(h)
            oc, nc = numeric_tokens(ob), numeric_tokens(nb)
            report.append(f"NUM {h}")
            report.append(f"  only_old {oc - nc}")
            report.append(f"  only_new {nc - oc}")
        if formula_lines(ob) != formula_lines(nb):
            formula_mismatch.append(h)
            report.append(f"FORMULA {h}")
        if ob != nb:
            byte_diff.append(h)

    report.append(f"numeric_mismatch_rooms {len(num_mismatch)}")
    report.append(f"formula_mismatch_rooms {len(formula_mismatch)}")
    report.append(f"byte_diff_rooms {len(byte_diff)}")
    for h in byte_diff:
        report.append(f"BYTE {h}")

    # Expected byte diffs only.
    expected = {
        "**B. Glossary**": "JI escape",  # glossary is one room? check
    }
    # Identify which old room contains the JI line and the pactum fixes.
    report.append("--- byte diff detail (first differing line) ---")
    for h in byte_diff:
        ob = old_map[h].splitlines()
        nb = new_map[h].splitlines()
        # align short
        n = max(len(ob), len(nb))
        shown = 0
        for i in range(n):
            a = ob[i] if i < len(ob) else "<missing>"
            b = nb[i] if i < len(nb) else "<missing>"
            if a != b:
                report.append(f"  {h} L{i+1}")
                report.append(f"    OLD {a[:220]}")
                report.append(f"    NEW {b[:220]}")
                shown += 1
                if shown >= 6:
                    report.append("    ...")
                    break

    # Markdown structure
    lines = NEW.splitlines()
    swallowed = []
    merged = []
    for i, line in enumerate(lines):
        if line.startswith("Status:") and i > 0 and lines[i - 1].startswith("|"):
            swallowed.append(i + 1)
        if line.startswith("Status:") and i + 1 < len(lines) and lines[i + 1].startswith("#"):
            merged.append(i + 1)
    report.append(f"status_swallowed_by_table {len(swallowed)} {swallowed}")
    report.append(f"status_then_heading {len(merged)} {merged}")
    if swallowed or merged:
        fail += 1

    # Tables: every line of pipes has a separator somewhere near — crude check that header rows with |---| exist
    # and column counts match within a table.
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
                report.append(f"TABLE cols {counts} :: {block[0][:80]}")
            if not any(re.search(r"\|?\s*:?-{3,}", ln) for ln in block):
                # separator may be :---: 
                if not any("---" in ln for ln in block):
                    table_err += 1
                    report.append(f"TABLE no separator {block[0][:80]}")
        else:
            i += 1
    report.append(f"table_errors {table_err}")
    if table_err:
        fail += 1

    # Version line
    if lines[1] != "**Draft Proposal v1.1**":
        report.append(f"VERSION LINE {lines[1]!r}")
        fail += 1
    else:
        report.append("version_line ok")

    # Locked status count
    report.append(f"old_locked {OLD.count('Status: **LOCKED**')}")
    report.append(f"new_locked {NEW.count('Status: **LOCKED**')}")
    report.append(f"new_proposed {NEW.count('Status: **PROPOSED**')}")
    if NEW.count("Status: **LOCKED**") != OLD.count("Status: **LOCKED**"):
        report.append("LOCKED COUNT CHANGED")
        fail += 1

    # No personal-name injection heuristic: flag rare capitalized full names in ADDED rooms only.
    # Skip. Instead ensure 'human-terran' and common founder names are absent from new text.
    for banned in ("human-terran", "Giardani"):
        if banned.lower() in NEW.lower() and banned.lower() not in OLD.lower():
            report.append(f"BANNED NAME introduced {banned}")
            fail += 1

    # Cross-ref style in new rooms: count arabic room cites like 7.53 inside proposed rooms only.
    # Not a failure; informational.
    proposed_bodies = []
    for h, bdy in new_rooms:
        if h not in old_map:
            proposed_bodies.append(bdy)
    arab = re.findall(r"(?<![A-Z0-9])\d+\.\d+", "\n".join(proposed_bodies))
    # filter years/none. Report count.
    report.append(f"arabic_dot_tokens_in_new_rooms {len(arab)} sample={arab[:20]}")

    # Numbers introduced in new rooms (informational)
    new_nums = Counter()
    for h, bdy in new_rooms:
        if h not in old_map:
            new_nums.update(numeric_tokens(bdy))
    report.append("new_room_number_tokens " + ", ".join(f"{k}:{v}" for k, v in sorted(new_nums.items(), key=lambda kv: kv[0])))

    if num_mismatch or formula_mismatch:
        fail += 1

    # Unexpected byte diffs. Expected headings:
    # The glossary room heading might be the first bold inside glossary? 
    # We print them; caller decides. Fail if a byte diff is not in the allow list
    # after we know the headings. Allow list by substring of the heading.
    allow_sub = (
        "Glossary",
        "III.17 Rate Chain",
        "V.35 Limen Scholae",
        "V.37 Pinna",
        "VIII.10 Prioritas",
        "IX.1 Master Formula",
    )
    unexpected = []
    for h in byte_diff:
        if not any(s in h for s in allow_sub):
            unexpected.append(h)
    report.append(f"unexpected_byte_diffs {len(unexpected)}")
    for h in unexpected:
        report.append(f"UNEXPECTED {h}")
    if unexpected:
        fail += 1

    # Confirm each expected diff is ONLY the intended lines, by checking the rest equal.
    def glossary_slice(src: str) -> str:
        a = src.find("# B. Glossary\n")
        b = src.find("**B.1 Usus**")
        if b < 0:
            b = src.find("# I. PRIMA\n")
        if a < 0 or b < 0 or b < a:
            return ""
        return src[a:b].strip("\n")

    g_old = glossary_slice(OLD if "**B.1 Usus**" in OLD else OLD)
    # Old file has no B.1; slice from glossary heading to I. PRIMA.
    def glossary_old(src: str) -> str:
        a = src.find("# B. Glossary\n")
        b = src.find("# I. PRIMA\n")
        return src[a:b].strip("\n")

    go = glossary_old(OLD)
    gn = glossary_slice(NEW)
    # Expected difference is only the JI escape.
    go_n = go.replace("E\\\\\\_net.", "E\\_net.")
    if go_n == gn:
        report.append("glossary_bytes MATCH except authorized JI escape")
    else:
        report.append("glossary_bytes DIFFER beyond JI")
        fail += 1
        # show a short diff
        import difflib
        diff = list(difflib.unified_diff(go_n.splitlines(), gn.splitlines(), lineterm="", n=1))
        report.extend(diff[:40])

    # Axiom block byte identity: from "**III. The 12 Foundational Axioms**" through its Status.
    def grab(src: str, start: str, end: str) -> str:
        a = src.find(start)
        b = src.find(end, a + 1)
        return src[a:b]

    ax_o = grab(OLD, "**III. The 12 Foundational Axioms**", "**IV. Master Objective Function**")
    ax_n = grab(NEW, "**III. The 12 Foundational Axioms**", "**IV. Master Objective Function**")
    report.append("axioms_byte " + ("MATCH" if ax_o == ax_n else "DIFFER"))
    if ax_o != ax_n:
        fail += 1

    vci_o = "VCI\\_t = 0.40 E\\_net + 0.25 B\\_success + 0.20 T\\_value + 0.15 I\\_built − P."
    report.append("vci_weights_present_old " + str(vci_o in OLD))
    report.append("vci_weights_present_new " + str(vci_o in NEW))
    if vci_o not in NEW:
        fail += 1

    report.append(f"fail {fail}")
    out = Path("/tmp/sapiens-v11-audit.txt")
    out.write_text("\n".join(report) + "\n")
    print("\n".join(report))
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
