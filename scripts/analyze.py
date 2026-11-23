#!/usr/bin/env python3
"""
Frequency analysis of the drawn numbers (Lotto 6 aus 45 and EuroMillionen).

Reads dcupl/data/*.csv, writes analysis/*.csv and analysis/README.md.
Run from the project root:  python3 scripts/analyze.py
"""
import csv
import datetime as dt
import glob
import math
import os
from collections import Counter
from itertools import combinations

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "dcupl", "data")
OUT = os.path.join(ROOT, "analysis")
os.makedirs(OUT, exist_ok=True)


WITHOUT_NUMBERS = []  # draws whose numbers build-data.py dropped (copied in the source)


def load(pattern, nums, extra=()):
    rows = []
    for f in sorted(glob.glob(os.path.join(DATA, pattern))):
        for r in csv.DictReader(open(f, encoding="utf-8"), delimiter=";"):
            d = dt.datetime.strptime(r["date"], "%d.%m.%Y").date()
            if any(r[k] == "" for k in nums):
                WITHOUT_NUMBERS.append((pattern, d))
                continue
            rows.append({"date": d, "nums": tuple(int(r[k]) for k in nums),
                         **{k: (int(r[k]) if r[k] != "" else None) for k in extra}})
    rows.sort(key=lambda x: x["date"])
    return rows


def chi_square_p(counts, expected):
    """Pearson chi-square against a uniform expectation; p-value via the regularized
    upper incomplete gamma function (Wilson-Hilferty approximation is enough here)."""
    k = len(counts)
    chi2 = sum((c - expected) ** 2 / expected for c in counts)
    df = k - 1
    # Wilson-Hilferty normal approximation of the chi-square CDF
    z = ((chi2 / df) ** (1 / 3) - (1 - 2 / (9 * df))) / math.sqrt(2 / (9 * df))
    p = 0.5 * math.erfc(z / math.sqrt(2))
    return chi2, df, p


def freq_table(rows, universe, label):
    c = Counter(n for r in rows for n in r["nums"])
    last = {}
    for i, r in enumerate(rows):
        for n in r["nums"]:
            last[n] = i
    n_draws = len(rows)
    per_draw = len(rows[0]["nums"])
    expected = n_draws * per_draw / len(universe)
    table = []
    for n in universe:
        gap = n_draws - 1 - last[n] if n in last else n_draws
        table.append((n, c[n], round(c[n] / expected, 3), gap))
    chi2, df, p = chi_square_p([c[n] for n in universe], expected)
    return table, expected, (chi2, df, p)


def combos_table(rows, k, top=15):
    c = Counter()
    for r in rows:
        for comb in combinations(sorted(r["nums"]), k):
            c[comb] += 1
    return c.most_common(top), len(c)


def write_table(name, header, rows):
    with open(os.path.join(OUT, name), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";", lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def md_table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(str(x) for x in r) + " |" for r in rows]
    return "\n".join(out)


def fmt_combo(c):
    return ", ".join(str(x) for x in c)


md = []


def section(title, rows, universe, k_list, per_draw_label, add_cols=None, extra_note=""):
    n = len(rows)
    md.append(f"## {title}\n")
    md.append(f"{n} draws from {rows[0]['date']:%d.%m.%Y} to {rows[-1]['date']:%d.%m.%Y}.{extra_note}\n")
    table, expected, (chi2, df, p) = freq_table(rows, universe, title)
    by_count = sorted(table, key=lambda t: (-t[1], t[0]))
    md.append(f"Expected frequency per number: {expected:.1f}. Chi-square test against a uniform "
              f"distribution: χ² = {chi2:.1f}, df = {df}, p ≈ {p:.2f} "
              f"({'no' if p > 0.05 else 'a'} statistically significant deviation from chance).\n")
    md.append("**Most drawn numbers**\n")
    md.append(md_table(["Number", "Drawn", "vs. expected", "Draws since last"], by_count[:10]) + "\n")
    md.append("**Least drawn numbers**\n")
    md.append(md_table(["Number", "Drawn", "vs. expected", "Draws since last"], by_count[-10:][::-1]) + "\n")
    overdue = sorted(table, key=lambda t: -t[3])[:5]
    md.append("**Longest absent right now**\n")
    md.append(md_table(["Number", "Drawn", "vs. expected", "Draws since last"], overdue) + "\n")
    slug = title.lower().replace(" ", "-").replace("(", "").replace(")", "").replace(",", "")
    write_table(f"{slug}-frequency.csv", ["number", "drawn", "vsExpected", "drawsSinceLast"], table)
    for k in k_list:
        top, distinct = combos_table(rows, k)
        possible = math.comb(len(universe), k)
        md.append(f"**Most frequent {k}-number combinations** ({distinct} of {possible} possible seen)\n")
        md.append(md_table([f"{k} numbers", "Drawn together"], [(fmt_combo(c), v) for c, v in top]) + "\n")
        write_table(f"{slug}-combos-{k}.csv", ["numbers", "drawnTogether"], [(fmt_combo(c), v) for c, v in top])
    full = Counter(tuple(sorted(r["nums"])) for r in rows)
    rep = [(fmt_combo(c), v) for c, v in full.most_common() if v > 1]
    if rep:
        md.append(f"**Full {per_draw_label} drawn more than once**\n")
        md.append(md_table([per_draw_label, "Times"], rep[:10]) + "\n")
    else:
        md.append(f"No full {per_draw_label} has ever been drawn twice.\n")
    if add_cols:
        add_cols(rows)


# --------------------------------------------------------------------------- Data
lotto = load("lotto-ziehungen-*.csv", [f"nr{i}asc" for i in range(1, 7)], extra=("additionalNr",))
euml = load("euromillionen-*.csv", [f"nr{i}asc" for i in range(1, 6)])
stars = load("euromillionen-*.csv", ["star1asc", "star2asc"])

# The report is anchored to the data, not to the day it runs: LATEST is the most
# recent draw in dcupl/data/ and "last three years" is the window ending there.
LATEST = max(lotto[-1]["date"], euml[-1]["date"])
THREE_YEARS = LATEST - dt.timedelta(days=3 * 365)

# --------------------------------------------------------------------------- Lotto
md.append("# Most drawn numbers and combinations\n")
md.append(f"Generated by `scripts/analyze.py` from the files in `dcupl/data/` "
          f"(latest draw: {LATEST:%d.%m.%Y}). "
          "All figures are descriptive; every draw is independent and past frequencies carry no "
          "predictive value, which the chi-square results below confirm.\n")


def lotto_additional(rows):
    c = Counter(r["additionalNr"] for r in rows)
    expected = len(rows) / 45
    top = sorted(c.items(), key=lambda t: (-t[1], t[0]))[:10]
    md.append(f"**Most frequent additional number (Zusatzzahl)**, expected {expected:.1f} each\n")
    md.append(md_table(["Number", "Drawn as Zusatzzahl"], top) + "\n")


lotto_without = sorted(d for p, d in WITHOUT_NUMBERS if p.startswith("lotto"))
section("Lotto 6 aus 45, all draws 1986-2026", lotto, range(1, 46), (2, 3, 4), "6-number combination", lotto_additional,
        extra_note="".join(f" The draw of {d:%d.%m.%Y} is left out: its numbers were copied from an earlier draw "
                           "in the source, so the build drops them." for d in lotto_without))
section("Lotto 6 aus 45, last three years", [r for r in lotto if r["date"] >= THREE_YEARS], range(1, 46), (2, 3),
        "6-number combination", lotto_additional,
        extra_note=" Includes the Friday draws (monthly since 2023, every two weeks since 25.07.2025).")

# --------------------------------------------------------------------------- EuroMillionen
FORMAT_12 = dt.date(2016, 9, 27)  # 12 stars since 27.09.2016


def euml_stars(rows):
    sub = [s for s in stars if s["date"] >= rows[0]["date"]]
    universe = range(1, 13)  # callers only pass draws of the 12-star format
    table, expected, (chi2, df, p) = freq_table(sub, universe, "stars")
    by_count = sorted(table, key=lambda t: (-t[1], t[0]))
    md.append(f"**Star numbers** (expected {expected:.1f} each; χ² = {chi2:.1f}, p ≈ {p:.2f})\n")
    md.append(md_table(["Star", "Drawn", "vs. expected", "Draws since last"], by_count) + "\n")
    pairs, _ = combos_table(sub, 2, top=8)
    md.append("**Most frequent star pairs**\n")
    md.append(md_table(["Stars", "Drawn together"], [(fmt_combo(c), v) for c, v in pairs]) + "\n")


section("EuroMillionen, all draws 2004-2026", euml, range(1, 51), (2, 3), "5-number combination")
md.append("Star numbers are not compared across the whole period: the pool changed from 9 (2004-2011) "
          "to 11 (2011-2016) to 12 stars (since 27.09.2016).\n")
section("EuroMillionen, current format since Sept 2016 (12 stars)", [r for r in euml if r["date"] >= FORMAT_12],
        range(1, 51), (2, 3), "5-number combination", euml_stars)
section("EuroMillionen, last three years", [r for r in euml if r["date"] >= THREE_YEARS], range(1, 51), (2,),
        "5-number combination", euml_stars)

with open(os.path.join(OUT, "README.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(md))
print("wrote analysis/README.md")
