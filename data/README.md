# Data Dictionary

## Source

Bank-level financial data exported from **BankFocus** (Moody's/Bureau van
Dijk), covering **436 banks across 19 EU/EEA countries**, for the years
**2019-2023**.

**Data license:** BankFocus is a proprietary, subscription-based database.
`data.xlsx`, `output_clean.xlsx`, `outlier_report.csv` and
`balanced_panel_report.csv` are all excluded from version control by
default (see `.gitignore` and the "Data license note" in the main README)
pending verification of your institution's redistribution terms — the
derived files are excluded too because `outlier_report.csv` alone contains
1,506 individually identified bank names and values taken directly from
the licensed data.

Raw file: `data.xlsx`
- First 3 sheets (`Search summary`, `Results`, `C2`) are export metadata,
  not used in the analysis.
- 9 remaining sheets, one per indicator, each with 436 rows: `Company name
  Latin alphabet`, `Country ISO code`, and one column per year, labeled e.g.
  `"Tier 1 Capital\nEUR 2023"`.

Cleaned/aggregated file: `output_clean.xlsx` (produced by
`src/data_cleaning.py`)
- One row per **country**, one column per **year** (2019-2023).
- **19 countries**: AT, BE, CY, DE, EE, ES, FI, FR, GR, IE, IT, LT, LU, LV,
  MT, NL, PT, SI, SK.

## Units

The raw column headers are labeled in plain **EUR**, not thousands of EUR
(e.g. `"Tier 1 Capital\nEUR 2023"`). `output_clean.xlsx` keeps the raw EUR
scale; the charts in `outputs/figures/` convert monetary indicators to
**EUR billions** for readability (see `src/visualization.py`).

## Indicators

| Sheet / indicator | Unit (raw data) | Unit (charts) | Type | Aggregation rule | What it measures |
|---|---|---|---|---|---|
| Tier 1 Capital | EUR | EUR bn | absolute | **sum** | Total Tier 1 capital held by the sampled banks in a country |
| NII | EUR | EUR bn | absolute | **sum** | Total net interest income of the sampled banks in a country |
| Impaired loans | EUR | EUR bn | absolute | **sum** | Total impaired loans of the sampled banks in a country |
| Tier 1 Ratio | % | % | ratio | **median** | Capital strength of the representative bank in the sample |
| Tot. cap. adequacy ratio | % | % | ratio | **median** | Overall solvency of the representative bank in the sample |
| ROAA | % | % | ratio | **median** | Profitability (return on average assets) of the representative bank |
| ROAE | % | % | ratio | **median** | Profitability (return on average equity) of the representative bank |
| NII-RWAs | % | % | ratio | **median** | Net interest margin relative to risk, representative bank |
| Impaired loans-RWAs | % | % | ratio | **median** | Impaired loans as a % of risk-weighted assets, representative bank |

**A note on "Impaired loans-RWAs"**: this is impaired loans divided by
risk-weighted assets, as labeled by BankFocus. It is **not** the standard
NPL ratio, which is conventionally non-performing loans over *gross loans*.
The two move similarly (both are asset-quality indicators) but are not
numerically interchangeable — this project keeps the source's own label and
definition rather than presenting it as the standard NPL ratio.

**Why sum vs. median, and why "representative bank" rather than "national
banking system"?** See `src/aggregation.py`. In short: absolute/monetary
variables are summed to describe the sampled banks' combined size; ratio
variables are aggregated as a **median** because no reliable weights (RWA,
total assets) were available for a weighted average. The ratio columns
therefore describe the **representative bank in the sample**, not a
system-wide weighted average.

## Coverage: bank counts per country

Two distinct counts matter here, and they are NOT the same number:
- **Total bank rows per country per sheet** — e.g. France has 107 bank rows
  in the "Tier 1 Capital" sheet — the total number of distinct banks that
  appear at all, across any year.
- **Banks actually reporting a non-missing value in a specific year** — this
  is smaller and varies by year, since not every bank reports every year.
  For France/Tier 1 Capital this ranges from 77 to 88 across 2019-2023; the
  single highest figure anywhere in the whole dataset is **106** (France,
  ROAA, 2019).

`coverage_report.csv` records the second (year-specific) count for every
sheet/country/year — that is the number that actually backs each cell in
`output_clean.xlsx`, and the one to check before trusting a comparison.
Maximum banks reporting in a single year, per country (any indicator):

| Country | Max banks reporting (single year) | Country | Max banks reporting (single year) |
|---|---|---|---|
| FR | 106 | LU | 9 |
| DE | 61 | LV | 9 |
| IT | 48 | CY | 8 |
| ES | 46 | GR | 7 |
| AT | 26 | SI | 6 |
| FI | 17 | MT | 6 |
| PT | 17 | SK | 5 |
| BE | 16 | LT | 4 |
| NL | 10 | EE | 3 |
| IE | 10 | | |

Full per-country/year/indicator counts in
[`coverage_report.csv`](coverage_report.csv). **Treat any comparison
involving Estonia, Lithuania or Slovakia (a handful of banks) with more
caution than one involving France, Germany, Italy or Spain** (dozens to over
a hundred banks) — their medians are not equally reliable.

## Missing values

Missing values (`n.a.` in the source) are **not imputed by default**.
Their prevalence varies a lot by indicator:

| Indicator | % missing (bank-year cells) |
|---|---|
| Tier 1 Capital | 30.9% |
| Tier 1 Ratio | 28.8% |
| Tot. cap. adequacy ratio | 25.5% |
| ROAA | 11.1% |
| ROAE | 11.4% |
| NII | 11.4% |
| NII-RWAs | 38.0% |
| Impaired loans | 26.1% |
| Impaired loans-RWAs | 38.0% |

Given these levels, filling gaps with an in-row median would fabricate a
large share of the dataset. Country-year aggregates in `output_clean.xlsx`
are computed from whichever banks reported that year/indicator (see
Coverage above). Optional documented imputation is available via
`ExcelTool.process(impute_missing=True)`, which writes
`missing_value_report.csv` logging every filled cell.

## Outliers

Outliers are **flagged, not removed**, using the IQR method (1.5x
multiplier) applied **separately to each country and year** — a bank is
only compared to its peers within the same country, never to the whole
European sample. This matters: a large German or French bank being simply
bigger than a typical Estonian bank is not a data quality issue, and an
earlier version of this project's global (cross-country) IQR check flagged
exactly that kind of false positive.

`outlier_report.csv` columns:

```
sheet, bank, country, year, value, lower_bound, upper_bound
```

The bank name is retained through the pipeline specifically so every
flagged value can be traced to an actual institution (an earlier version
dropped the bank name on read and only recorded `sheet, column, value`,
making the flagged values impossible to verify individually). The
`lower_bound`/`upper_bound` columns record the exact IQR thresholds that
triggered the flag for that country/year, so the report is self-contained.

On the real dataset, 1,506 bank-year values were flagged. Because detection
is now per-country, this number and its composition differ from a global
check: e.g. Cyprus and Greece show comparatively few flagged individual
banks (18 and 17 respectively) despite their very high country-level
impaired-loans-to-RWA ratios in 2019-2020 — that's expected, since the elevated level was shared
across most banks in those countries rather than driven by one deviant
bank. **Per-country/year outlier detection surfaces individual banks that
stand out from their national peers; it does not, and is not meant to,
surface an entire country standing out from the rest of Europe** — that
pattern is only visible in the aggregated country-level charts.

## Balanced-panel check (changing sample composition)

The number of banks reporting a given indicator changes from year to year
within a country (see Coverage above). This means a change in a **summed**
total (Tier 1 Capital, NII, Impaired loans) can partly reflect more or
fewer banks reporting that year, not only genuine growth or decline.

`balanced_panel_report.csv` addresses this directly for every summed
indicator: it identifies, per country, the subset of banks that report a
value in **all 5 years**, re-aggregates using only that fixed subset, and
records both totals side by side, along with the bank counts behind each
(`n_banks_reporting_full_sample` — the number of banks with a non-missing
value in that specific country/year — vs. `n_banks_balanced_panel`, the
fixed subset size, constant across years by construction). This lets you
compare the trend under the full (changing) sample against the trend
under a fixed set of banks — e.g. for France's Tier 1 Capital, between 85
and 88 banks report a value in any single year (2019-2023), but only 77 of
them report a value in every single year.

This is a **partial check, not a full fix**: the balanced subset is itself
a selection (banks that report consistently tend to be larger, more
established institutions), so it can bias the "fixed panel" view toward
bigger banks. A more complete treatment would model this selection
explicitly; for now, the two totals are simply presented side by side so
the reader can judge how much of a trend survives the restriction.
