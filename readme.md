<div align="center">
	<h1 align="center">dcupl-demos/lotto-euromillionen-austria</h1>
	<p align="center">Lotto 6 aus 45 (1986-2026) and EuroMillionen (2004-2026) draws of the Austrian Lotteries<br />Demo project for <a href="http://www.dcupl.com?utm_source=github.com&utm_medium=readme&utm_campaign=lotto-euromillionen-austria" target="_blank">dcupl</a>, the Front-end First Data Integration Layer.</p> <br />
</div>

<p align="center">
<strong>@dcupl/cli</strong><br/>
  <a href="https://npmjs.com/package/@dcupl/cli">
    <img src="https://img.shields.io/npm/v/@dcupl/cli/latest.svg?style=flat-square" alt="dcupl CLI" />
  </a>
  <a href="https://npmjs.com/package/@dcupl/cli" rel="nofollow">
    <img src="https://img.shields.io/npm/dt/@dcupl/cli.svg?style=flat-square" alt="dcupl CLI">
  </a>
</p>

<p align="center">
<strong>@dcupl/core</strong><br/>
  <a href="https://npmjs.com/package/@dcupl/core">
    <img src="https://img.shields.io/npm/v/@dcupl/core/latest.svg?style=flat-square" alt="dcupl CLI" />
  </a>
  <a href="https://npmjs.com/package/@dcupl/core" rel="nofollow">
    <img src="https://img.shields.io/npm/dt/@dcupl/core.svg?style=flat-square" alt="dcupl Core">
  </a>
</p>

<hr>

# Lotto AUT 1986-2026 + EuroMillionen 2004-2026

Two models, 5,665 draws, one dcupl workspace:

| Model | Draws | Period | Source files |
|---|---|---|---|
| `lotto` | 3,684 | 07.09.1986 - 20.09.2026 | `dcupl/data/lotto-ziehungen-*.csv` |
| `euromillionen` | 1,981 | 13.02.2004 - 18.09.2026 | `dcupl/data/euromillionen-*.csv` |

The analysis of the most drawn numbers and number combinations lives in [`analysis/README.md`](analysis/README.md).

## Data source: win2day

All data is published by win2day, the online gaming platform of the Austrian Lotteries:

- Lotto: https://www.win2day.at/lotterie/lotto/lotto-statistik-zahlen-ergebnisse-download
- EuroMillionen: https://www.win2day.at/lotterie/euromillionen/euromillionen-statistik-zahlen-ergebnisse-download

The original exports are kept unchanged in `_raw/` (`legacy-data/` holds the revised 1986-2022 Lotto files of the first project version). `scripts/build-data.py` transforms them deterministically into the uniform files in `dcupl/data/`: one row per draw, `;`-separated, UTF-8, decimal point, no thousand separators. Every deviation from the source is a rule in the script and is logged when it applies (a duplicate line, a typo in the year, drawn orders that do not match the ascending numbers, mislabelled prize tiers, and the numbers of 03.01.1995, which the source copied from 03.01.1993: that draw keeps its date, winners and prize rates, without numbers).

```
python3 scripts/build-data.py   # _raw/  ->  dcupl/data/
python3 scripts/analyze.py      # dcupl/data/  ->  analysis/
```

To add a new year, download the `NN_W2D_STAT_Lotto_<year>.csv` / `NN_W2D_STAT_EUML_<year>.csv` file into `_raw/`, add the resource to `dcupl/dcupl.lc.json` and rebuild.

An earlier version of the Lotto data is published as a Kaggle dataset:
[lottery-austria-1986-til-2022](https://www.kaggle.com/datasets/gernotbernkopf/lottery-austria-1986-til-2022).
It reflects the state of 2022 and has not been updated since; the files in `dcupl/data/` supersede it and
can be uploaded there to refresh it.

## Model notes

**lotto**
- Prize rates are in ATS until 2000 and in EUR since 2001 (column `currency`). The applications `lotto-ATS` and `lotto-EUR` load only one currency.
- `six` keeps the published value (`1`, `JP`, `DJP`, `3JP`...). `sixWinners` is the numeric count (0 when the jackpot rolled over) and `jackpotStreak` the number of consecutive rollovers.
- The drawn order (`nr1`..`nr6`) was published until 2016 only; the ascending order (`nr1asc`..`nr6asc`) is complete.
- The prize tiers 4+ZZ, 3+ZZ and ZZ exist since September 2010.
- Besides Sunday and Wednesday there are Friday draws (`weekday`): monthly since 2023 (2nd Friday, skipping June and December), every two weeks since 25.07.2025 - 10 per year in 2023/2024, 19 in 2025.

**euromillionen**
- Prize tiers are keyed by hit combination (`winnersEU_5_2`, `winnersAT_5_2`, `rate_5_2`, ... `rate_1_2`), not by rank number: the ranking order changed twice over the years and the 2+0 tier was introduced in May 2011.
- Austrian winners per tier are published since 2011.
- The star pool grew from 9 (2004) to 11 (May 2011) to 12 stars (September 2016). Star frequencies are only comparable within one format.
- The drawn order was published 2004-2016 only.

Both models use `autoGenerateKey`; the date is unique per model and is the natural key for queries.
The `date` property sets `"UTC": true`, so a draw is parsed as UTC midnight (`20.09.2026` ->
`2026-09-20T00:00:00.000Z`) instead of local midnight in Europe/Vienna, which would shift the calendar day.

## dcupl expressions

`numbersAsc`, `numbersAscWithAdditional` and `numbersDrawn` (lotto) as well as `numbersAsc`, `starsAsc` and `combinationAsc` (euromillionen) are string expressions that concatenate the drawn numbers, so a full combination can be filtered and faceted like any other attribute.

### 1) Setup

```
nvm use          # Node 24, see .nvmrc
npm install
```

The CLI is pinned in `devDependencies` (`@dcupl/cli` 1.4.0-beta.5, `@dcupl/*` 2.0.0-beta.18) and Node >= 22
is required - the daemon uses `require(esm)` and dies with `ERR_REQUIRE_ESM` on Node 20. Use `npx dcupl`
(or the `npm run` scripts) so the pinned CLI is used rather than a possibly older global install; check with
`npx dcupl --version`.

### 2) Validate and explore locally

```
npm run validate
npx dcupl app create --load --auto-serve --json
npx dcupl app fn facets --model lotto --attribute weekday --sort size-desc --json
npx dcupl app fn facets --model euromillionen --attribute star1asc --sort size-desc --json
npx dcupl app fn aggregate --model lotto --attribute rateSix --types max,avg --json
npx dcupl app destroy --app <appId> --json
```

The current verification run - commands and actual values - is recorded in [`docs/verification.md`](docs/verification.md).

### 3) Connect your local project with the dcupl Console

- Go to [https://console.dcupl.com](https://console.dcupl.com) and create your **free** account.
- Set your `projectId` in the dcupl.config.json
- Set your `apiKey` in the dcupl.secrets.json
- Push your local workspace to the dcupl Console using the CLI `dcupl files push`

### 4) Start your development server

```
dcupl serve
```

Switch to "Local Dev Server" in the dcupl Console and open one of the predefined applications (`default`, `lotto`, `lotto-ATS`, `lotto-EUR`, `euromillionen`).
