#!/usr/bin/env python3
"""
Deterministic data build for dcupl-demos/lotto.

Inputs  (_raw/):
  legacy-data/lotto-ziehungen-*.csv   revised win2day exports 1986-2022 (old project files)
  lotto_<year>.csv                    win2day "NN_W2D_STAT_Lotto_<year>.csv" (2023+)
  euml_2004-2017.csv                  win2day "euromillionen-ergebnisse-2004-2017.csv" (used for 2004-2016)
  euml_<year>.csv                     win2day "NN_W2D_STAT_EUML_<year>.csv" (2017+)

Outputs (dcupl/data/):
  lotto-ziehungen-<range>_<CUR>.csv   one uniform schema, decimal point, no thousand separators
  euromillionen-<range>.csv           one uniform schema keyed by hit combination (5+2 ... 2+0)

Run from the project root:  python3 scripts/build-data.py
Every transformation is rule based; deviations from the source are logged to stderr.
"""
import csv
import datetime as dt
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "_raw")
OUT = os.path.join(ROOT, "dcupl", "data")

WARN = []


def warn(msg):
    WARN.append(msg)
    print("WARN " + msg, file=sys.stderr)


# --------------------------------------------------------------------------- helpers
def read_latin1(path):
    with open(path, encoding="latin1", newline="") as f:
        return list(csv.reader(f, delimiter=";"))


def to_int(s):
    """'3.027' -> 3027, '' -> '', 'JP' -> None (caller decides)."""
    s = (s or "").strip()
    if s == "":
        return ""
    if re.fullmatch(r"[0-9.]+", s):
        return int(s.replace(".", ""))
    return None


def to_float(s):
    """'1.200.000,00' -> '1200000.00', '6542159,00' -> '6542159.00'."""
    s = (s or "").strip()
    if s == "":
        return ""
    if re.fullmatch(r"[0-9.]*,[0-9]+|[0-9.]+", s):
        return s.replace(".", "").replace(",", ".")
    return None


def norm_date(s):
    """'5.9.2010' -> '05.09.2010'."""
    parts = [p for p in s.strip().split(".") if p != ""]  # tolerates '25.10..2000'
    if len(parts) != 3:
        raise ValueError(f"bad date {s!r}")
    d, m, y = parts
    return f"{int(d):02d}.{int(m):02d}.{int(y)}"


def weekday(date_str):
    d, m, y = date_str.split(".")
    return dt.date(int(y), int(m), int(d)).strftime("%A")


def jackpot_streak(s):
    """'JP' -> 1, 'DJP' -> 2, '3JP' -> 3, '4JP' -> 4, otherwise 0."""
    s = (s or "").strip()
    if s == "JP":
        return 1
    if s == "DJP":
        return 2
    m = re.fullmatch(r"([0-9]+)JP", s)
    return int(m.group(1)) if m else 0


def write_csv(path, header, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";", lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)
    print(f"wrote {os.path.relpath(path, ROOT)}: {len(rows)} rows")


# --------------------------------------------------------------------------- LOTTO
LOTTO_HEADER = [
    "weekday", "date", "year", "currency",
    "nr1asc", "nr2asc", "nr3asc", "nr4asc", "nr5asc", "nr6asc", "additionalNr",
    "nr1", "nr2", "nr3", "nr4", "nr5", "nr6",
    "six", "sixWinners", "jackpotStreak", "rateSix",
    "fiveAddNr", "fiveAddNrJackpot", "rateFiveAddNr",
    "five", "rateFive",
    "fourAddNr", "rateFourAddNr",
    "four", "rateFour",
    "threeAddNr", "rateThreeAddNr",
    "three", "rateThree",
    "nrOfAddNr", "rateAddNr",
]


def lotto_row(date, currency, asc, drawn, add, six, rate_six, tiers):
    """tiers: dict tierKey -> (count_raw, rate_raw)."""
    six = (six or "").strip()
    six_winners = to_int(six)
    streak = jackpot_streak(six)
    if six_winners is None:  # JP / DJP / 3JP ...
        six_winners = 0
    five_add_raw, five_add_rate = tiers.get("fiveAddNr", ("", ""))
    five_add = to_int(five_add_raw)
    five_add_jp = ""
    if five_add is None:
        five_add_jp = five_add_raw.strip()
        five_add = ""

    def cnt(k):
        v = to_int(tiers.get(k, ("", ""))[0])
        if v is None:
            warn(f"lotto {date}: non-numeric count '{tiers[k][0]}' for {k} -> empty")
            return ""
        return v

    def rate(k):
        v = to_float(tiers.get(k, ("", ""))[1])
        if v is None:
            warn(f"lotto {date}: non-numeric rate '{tiers[k][1]}' for {k} -> empty")
            return ""
        return v

    rs = to_float(rate_six)
    if rs is None:
        warn(f"lotto {date}: non-numeric rateSix '{rate_six}' -> empty")
        rs = ""
    return [
        weekday(date), date, int(date[-4:]), currency,
        *asc, add,
        *drawn,
        six, six_winners, streak, rs,
        five_add, five_add_jp, rate("fiveAddNr"),
        cnt("five"), rate("five"),
        cnt("fourAddNr"), rate("fourAddNr"),
        cnt("four"), rate("four"),
        cnt("threeAddNr"), rate("threeAddNr"),
        cnt("three"), rate("three"),
        cnt("nrOfAddNr"), rate("nrOfAddNr"),
    ]


def build_lotto_legacy(path, default_currency):
    rows = read_latin1(path)
    header = [h.strip() for h in rows[0]]
    idx = {}
    for i, h in enumerate(header):
        idx.setdefault(h, i)  # first occurrence wins (additionalNr appears twice)

    def get(r, k):
        i = idx.get(k)
        return r[i].strip() if i is not None and i < len(r) else ""

    out = []
    prev = None
    seen_numbers = {}  # (asc, drawn, add) -> date of the first draw with exactly these numbers
    for r in rows[1:]:
        if not any(c.strip() for c in r):
            continue
        if r == prev:
            warn(f"{os.path.basename(path)}: identical duplicate line for {get(r, 'date')} skipped")
            continue
        prev = r
        date = norm_date(get(r, "date"))
        # weekday is recomputed from the date: the legacy files label holiday draws as 'Sunday'
        currency = get(r, "currency1") or get(r, "currency3") or default_currency
        asc = [to_int(get(r, f"nr{i}asc")) for i in range(1, 7)]
        drawn = [to_int(get(r, f"nr{i}")) if f"nr{i}" in idx else "" for i in range(1, 7)]
        if asc != sorted(asc) and drawn == sorted(drawn) and sorted(asc) == drawn:
            warn(f"lotto {date}: ascending/drawn columns swapped in source -> swapped back")
            asc, drawn = drawn, asc
        if drawn[0] != "" and sorted(drawn) != asc:
            warn(f"lotto {date}: drawn order {drawn} does not match ascending numbers {asc} -> drawn order dropped")
            drawn = [""] * 6
        add = to_int(get(r, "additionalNr"))
        # The same six numbers in the same drawn order with the same additional number do not repeat by
        # chance: such a row carries numbers copied from the earlier draw. Its date, winners and prize
        # rates differ and are kept; the numbers are dropped because the real ones are unknown.
        numbers = (tuple(asc), tuple(drawn), add)
        if drawn[0] != "" and numbers in seen_numbers:
            warn(f"lotto {date}: numbers, drawn order and additional number identical to "
                 f"{seen_numbers[numbers]} -> copied in source, numbers dropped")
            asc, drawn, add = [""] * 6, [""] * 6, ""
        else:
            seen_numbers.setdefault(numbers, date)
        tiers = {}
        for k in ("fiveAddNr", "five", "fourAddNr", "four", "threeAddNr", "three", "nrOfAddNr"):
            if k in idx:
                rate_key = "rate" + k[0].upper() + k[1:]
                tiers[k] = (get(r, k), get(r, rate_key))
        out.append(lotto_row(date, currency, asc, drawn, add,
                             get(r, "six"), get(r, "rateSix"), tiers))
    return out


TIER_LABELS = {
    "6er": "six", "5er + ZZ": "fiveAddNr", "5er": "five", "4er + ZZ": "fourAddNr",
    "4er": "four", "3er + ZZ": "threeAddNr", "3er": "three", "ZZ": "nrOfAddNr",
}


def build_lotto_win2day(path, year):
    """New win2day layout (2023+): two lines per draw, four prize tiers per line,
    dates without year, ascending order only."""
    rows = read_latin1(path)
    out = []
    pending = None
    for r in rows[1:]:
        if len(r) < 26 or not r[0].strip():
            continue
        date = norm_date(r[0].strip() + str(year))
        tiers = {}
        for j in range(4):
            label = r[10 + j * 4].strip()
            if label:
                tiers[TIER_LABELS[label]] = (r[11 + j * 4], r[13 + j * 4])
        if r[1].strip():  # first line of a draw
            if pending:
                warn(f"lotto {pending['date']}: second line missing")
                out.append(finish_win2day(pending))
            if r[1].strip() != "aufsteigend":
                warn(f"lotto {date}: unexpected order label '{r[1]}'")
            pending = {"date": date, "asc": [to_int(x) for x in r[2:8]], "add": to_int(r[9]), "tiers": tiers}
        else:
            if not pending or pending["date"] != date:
                warn(f"lotto {date}: orphan second line")
                continue
            pending["tiers"].update(tiers)
            out.append(finish_win2day(pending))
            pending = None
    if pending:
        warn(f"lotto {pending['date']}: second line missing")
        out.append(finish_win2day(pending))
    return out


def finish_win2day(p):
    six_raw, rate_six = p["tiers"].pop("six", ("", ""))
    return lotto_row(p["date"], "EUR", p["asc"], [""] * 6, p["add"], six_raw, rate_six, p["tiers"])


# --------------------------------------------------------------------------- EUROMILLIONEN
COMBOS = ["5_2", "5_1", "5_0", "4_2", "4_1", "4_0", "3_2", "3_1", "3_0", "2_2", "2_1", "2_0", "1_2"]
# rank -> combo, current (13-tier) layout; used only to resolve mislabelled tiers in the source
RANK_LAYOUT_13 = {1: "5_2", 2: "5_1", 3: "5_0", 4: "4_2", 5: "4_1", 6: "3_2", 7: "4_0",
                  8: "2_2", 9: "3_1", 10: "3_0", 11: "1_2", 12: "2_1", 13: "2_0"}

EUML_HEADER = (
    ["weekday", "date", "year", "drawNoInYear",
     "nr1asc", "nr2asc", "nr3asc", "nr4asc", "nr5asc", "star1asc", "star2asc",
     "nr1", "nr2", "nr3", "nr4", "nr5", "star1", "star2",
     "jackpot", "jackpotStreak"]
    + [f"{p}_{c}" for c in COMBOS for p in ("winnersEU", "winnersAT", "rate")]
)


def euml_row(date, draw_no, asc, stars_asc, drawn, stars_drawn, tiers):
    """tiers: list of (rank, combo_label, eu_raw, at_raw, rate_raw)."""
    by_combo = {}
    seen = set()
    for rank, combo, eu, at, rate in tiers:
        if combo in seen:
            fixed = RANK_LAYOUT_13.get(rank)
            warn(f"euml {date}: tier {rank} labelled {combo} twice -> using {fixed}")
            combo = fixed
        seen.add(combo)
        by_combo[combo] = (eu, at, rate)
    jp_raw = (by_combo.get("5_2", ("", "", ""))[0] or "").strip()
    jackpot = jp_raw if to_int(jp_raw) is None else ""
    row = [weekday(date), date, int(date[-4:]), draw_no, *asc, *stars_asc, *drawn, *stars_drawn, jackpot, jackpot_streak(jackpot)]
    for c in COMBOS:
        eu, at, rate = by_combo.get(c, ("", "", ""))
        eu_i, at_i, rate_f = to_int(eu), to_int(at), to_float(rate)
        if eu_i is None:  # 'JP'
            eu_i = 0
        if at_i is None:
            at_i = 0
        if rate_f is None:  # 'wird dem Rang 5+0 zugeschlagen'
            rate_f = ""
        row += [eu_i, at_i, rate_f]
    return row


DATE_RE = re.compile(r"^\d{1,2}\.\d{1,2}\.\d{4}$")


def build_euml_combined(path, years):
    """2004-2017 layout: two draws side by side (cols 1-12 / 13-24), blocks of
    header / ascending / drawn / tier lines."""
    rows = read_latin1(path)
    draws = []
    i = 0
    while i < len(rows):
        r = rows[i]
        nxt = rows[i + 1] if i + 1 < len(rows) else []
        # a draw header is the line right above 'aufsteigende Reihenfolge:'; the
        # 'Ergebnisse:' label is missing for some draws in the source
        if any("aufsteigende Reihenfolge" in c for c in nxt) and any(DATE_RE.match(c.strip()) for c in r):
            blocks = []
            for off in (0, 12):
                cells = r[off:off + 12]
                dates = [c for c in cells if DATE_RE.match(c.strip())]
                if not dates:
                    continue
                date = norm_date(dates[0])
                if date.endswith(".2099"):  # single typo in the source (Runde 47/2009)
                    warn(f"euml: source date {date} -> {date[:-4]}2009")
                    date = date[:-4] + "2009"
                blocks.append({"off": off, "date": date, "tiers": []})
            asc_line = rows[i + 2]
            drawn_line = rows[i + 4] if any("gezogene Reihenfolge" in c for c in rows[i + 3]) else None
            j = i + 5 if drawn_line else i + 3
            def is_tier(t):
                # rank may be missing in the source; identify a tier line by its hits/stars cells
                return any(o + 11 < len(t) and t[o + 3].strip().isdigit() and t[o + 5].strip().isdigit()
                           for o in (0, 12))

            # skip the two tier header lines
            while j < len(rows) and not is_tier(rows[j]):
                j += 1
            while j < len(rows) and is_tier(rows[j]):
                for b in blocks:
                    o = b["off"]
                    t = rows[j]
                    if o + 11 < len(t) and t[o + 3].strip().isdigit() and t[o + 5].strip().isdigit():
                        rank = int(t[o + 1]) if t[o + 1].strip().isdigit() else len(b["tiers"]) + 1
                        b["tiers"].append((rank, f"{t[o + 3].strip()}_{t[o + 5].strip()}",
                                           t[o + 7], t[o + 9], t[o + 11]))
                j += 1
            for b in blocks:
                o = b["off"]
                asc = [to_int(x) for x in asc_line[o + 1:o + 6]]
                st = [to_int(x) for x in asc_line[o + 6:o + 8]]
                drawn, sd = [""] * 5, [""] * 2
                if drawn_line and any(x.strip() for x in drawn_line[o + 1:o + 8]):
                    drawn = [to_int(x) for x in drawn_line[o + 1:o + 6]]
                    sd = [to_int(x) for x in drawn_line[o + 6:o + 8]]
                    if sorted(drawn) != asc or sorted(sd) != st:
                        warn(f"euml {b['date']}: drawn order {drawn}/{sd} does not match ascending "
                             f"numbers {asc}/{st} -> drawn order dropped")
                        drawn, sd = [""] * 5, [""] * 2
                draws.append((b["date"], asc, st, drawn, sd, b["tiers"]))
            i = j
        else:
            i += 1
    draws = [d for d in draws if int(d[0][-4:]) in years]
    draws.sort(key=lambda d: dt.datetime.strptime(d[0], "%d.%m.%Y"))
    return draws_to_rows(draws)


def build_euml_win2day(path):
    """2017+ layout: one line with numbers + 13 tier lines per draw."""
    rows = read_latin1(path)
    draws = []
    cur = None
    for r in rows[1:]:
        if len(r) < 14:
            continue
        if r[0].strip():
            date = norm_date(r[0].strip().split()[-1])
            cur = (date, [to_int(x) for x in r[1:6]], [to_int(x) for x in r[6:8]], [""] * 5, [""] * 2, [])
            draws.append(cur)
        elif cur is None:
            continue
        if r[8].strip().isdigit():
            cur[5].append((int(r[8]), f"{r[9].strip()}_{r[10].strip()}", r[11], r[12], r[13]))
    return draws_to_rows(draws)


def draws_to_rows(draws):
    out, counter = [], {}
    for date, asc, st, drawn, sd, tiers in draws:
        y = date[-4:]
        counter[y] = counter.get(y, 0) + 1
        if len(tiers) not in (12, 13):
            warn(f"euml {date}: {len(tiers)} prize tiers")
        out.append(euml_row(date, counter[y], asc, st, drawn, sd, tiers))
    return out


# --------------------------------------------------------------------------- main
def main():
    os.makedirs(OUT, exist_ok=True)
    # Lotto 1986-2022 from the revised legacy files (2017 file skipped: contained in 2010-2017)
    legacy = {
        "lotto-ziehungen-1986-2000_ATS.csv": "ATS",
        "lotto-ziehungen-2001-2010_EUR.csv": "EUR",
        "lotto-ziehungen-2010-2017_EUR.csv": "EUR",
        "lotto-ziehungen-2018_EUR.csv": "EUR",
        "lotto-ziehungen-2019_EUR.csv": "EUR",
        "lotto-ziehungen-2020_EUR.csv": "EUR",
        "lotto-ziehungen-2021_EUR.csv": "EUR",
        "lotto-ziehungen-2022_EUR.csv": "EUR",
    }
    seen_dates = set()
    for name, cur in legacy.items():
        rows = build_lotto_legacy(os.path.join(RAW, "legacy-data", name), cur)
        check_dupes(rows, seen_dates, name)
        write_csv(os.path.join(OUT, name), LOTTO_HEADER, rows)
    for path in sorted(glob.glob(os.path.join(RAW, "lotto_*.csv"))):
        year = int(re.search(r"lotto_(\d{4})", path).group(1))
        rows = build_lotto_win2day(path, year)
        check_dupes(rows, seen_dates, path)
        write_csv(os.path.join(OUT, f"lotto-ziehungen-{year}_EUR.csv"), LOTTO_HEADER, rows)

    # EuroMillionen
    seen_dates = set()
    rows = build_euml_combined(os.path.join(RAW, "euml_2004-2017.csv"), set(range(2004, 2017)))
    check_dupes(rows, seen_dates, "euml_2004-2017")
    write_csv(os.path.join(OUT, "euromillionen-2004-2016.csv"), EUML_HEADER, rows)
    for path in sorted(glob.glob(os.path.join(RAW, "euml_[0-9][0-9][0-9][0-9].csv"))):
        year = int(re.search(r"euml_(\d{4})", path).group(1))
        rows = build_euml_win2day(path)
        check_dupes(rows, seen_dates, path)
        write_csv(os.path.join(OUT, f"euromillionen-{year}.csv"), EUML_HEADER, rows)

    print(f"{len(WARN)} warnings", file=sys.stderr)


def check_dupes(rows, seen, src):
    for r in rows:
        if r[1] in seen:
            warn(f"{os.path.basename(src)}: duplicate draw date {r[1]}")
        seen.add(r[1])


if __name__ == "__main__":
    main()
