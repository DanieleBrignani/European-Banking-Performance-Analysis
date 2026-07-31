"""
data_cleaning.py
=================

Reads, cleans and aggregates the raw European banking Excel workbook.

Fixes applied in this version
------------------------------
1. AGGREGATION: each sheet uses the rule defined in src/aggregation.py
   (sum for absolute variables, median for ratios). See aggregation.py
   for the full rationale.

2. MISSING VALUES: kept as NaN by default (not imputed). Optional
   documented imputation via impute_missing=True, logged to
   missing_value_report.csv.

3. OUTLIERS -- now computed PER COUNTRY/YEAR, not globally across the
   whole European sample. An earlier version ran the IQR check on the
   entire column for all countries at once, which meant a large German
   or French bank could get flagged as an "outlier" simply for being
   bigger than most other European banks -- that mixes up size
   differences between countries with genuine within-country outliers.
   The bank name is also now kept through the pipeline (previously
   dropped immediately on read), so every flagged value in
   outlier_report.csv can be traced to an actual bank, not just a
   country -- and the report includes the IQR bounds that triggered
   the flag, not just the value.

4. COVERAGE: bank counts per country/year/indicator are exported to
   coverage_report.csv (see data/README.md).

5. BALANCED PANEL CHECK: for summed (absolute) variables, a change in
   the total can come from genuine growth OR from a different set of
   banks reporting that year. analyze_balanced_panel() identifies, per
   indicator, the banks that reported in ALL 5 years, re-aggregates
   using only that fixed subset, and exports both the full-sample and
   balanced-panel totals side by side so the two can be compared
   directly instead of leaving the concern undocumented.

6. Explicit pd.to_numeric conversion instead of df.replace('n.a.', nan)
   to avoid a pandas FutureWarning about implicit downcasting.

7. PATHS: resolved relative to this file's location via pathlib, not
   the current working directory.
"""

from pathlib import Path

import numpy as np
import pandas as pd

from aggregation import get_aggregation_rule

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

BANK_COL = "Company name Latin alphabet"
COUNTRY_COL = "Country ISO code"


class ExcelTool:
    def __init__(self, input_file, output_file):
        self.input_file = input_file
        self.output_file = output_file
        self.sheets = {}
        self.missing_value_log = []
        self.outlier_log = []
        self.coverage_log = []
        self.balanced_panel_log = []

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_year_columns(df: pd.DataFrame) -> pd.DataFrame:
        """Renames columns like 'Tier 1 Capital\\nEUR 2023' to '2023'."""
        import re
        rename_map = {}
        for col in df.columns:
            if col in (BANK_COL, COUNTRY_COL):
                continue
            match = re.search(r"(19|20)\d{2}", str(col))
            if match:
                rename_map[col] = match.group(0)
        return df.rename(columns=rename_map)

    def read_excel_file(self):
        """
        Reads all sheets, excluding the first 3 (export metadata). The
        bank name column is KEPT (not dropped) so outliers stay
        traceable to an individual bank, not just a country.
        """
        all_sheets = pd.read_excel(self.input_file, sheet_name=None)
        keys = list(all_sheets.keys())

        for i in range(3):
            all_sheets.pop(keys[i])

        for sheet_name in all_sheets.keys():
            all_sheets[sheet_name] = self._normalize_year_columns(all_sheets[sheet_name])

        self.sheets = all_sheets

    @staticmethod
    def _year_columns(df):
        return [c for c in df.columns if c not in (BANK_COL, COUNTRY_COL)]

    @staticmethod
    def _numeric(series):
        """
        Numeric coercion: pd.to_numeric(..., errors='coerce') already
        turns any unparseable value (including the literal string
        'n.a.') into NaN on its own -- an earlier version additionally
        called series.replace('n.a.', np.nan) first, which was both
        redundant and, in some pandas versions, a source of a
        FutureWarning about implicit downcasting. A single to_numeric
        call is simpler and avoids that entirely.
        """
        return pd.to_numeric(series, errors='coerce')

    # ------------------------------------------------------------------
    # Coverage (bank counts per country/year/indicator)
    # ------------------------------------------------------------------
    def analyze_coverage(self):
        for sheet_name, df in self.sheets.items():
            for year in self._year_columns(df):
                vals = self._numeric(df[year])
                counts = vals.groupby(df[COUNTRY_COL]).apply(lambda s: s.notna().sum())
                for country, n in counts.items():
                    self.coverage_log.append({
                        "sheet": sheet_name, "country": country,
                        "year": year, "n_banks_reporting": int(n),
                    })

    def export_coverage_report(self, path=None):
        path = path or (DATA_DIR / "coverage_report.csv")
        cov_df = pd.DataFrame(self.coverage_log)
        cov_df.to_csv(path, index=False)
        print(f"Coverage report written to {path} ({len(cov_df)} rows).")
        return cov_df

    # ------------------------------------------------------------------
    # Missing values
    # ------------------------------------------------------------------
    def _log_missing(self, sheet_name, df_before, df_after, numeric_cols):
        was_na = df_before[numeric_cols].isna()
        still_na = df_after[numeric_cols].isna()
        imputed_mask = was_na & ~still_na
        for col in numeric_cols:
            for idx in df_after.index[imputed_mask[col]]:
                self.missing_value_log.append({
                    "sheet": sheet_name,
                    "bank": df_after.loc[idx, BANK_COL] if BANK_COL in df_after.columns else None,
                    "column": col,
                    "imputed_value": df_after.loc[idx, col],
                })

    def process_sheet(self, sheet_name: str, df: pd.DataFrame,
                       impute_missing: bool = False) -> pd.DataFrame:
        """
        Cleans and aggregates a single sheet by COUNTRY_COL, dropping the
        bank-name column (only needed pre-aggregation, for outlier
        tracing).
        """
        df = df.copy()
        year_cols = self._year_columns(df)
        for col in year_cols:
            df[col] = self._numeric(df[col])

        if impute_missing:
            df_before = df.copy()

            def fill_missing_with_row_median(row):
                if np.all(np.isnan(row)):
                    return row
                with np.errstate(invalid="ignore"):
                    row_median = np.nanmedian(row)
                return row.fillna(row_median)

            df[year_cols] = df[year_cols].apply(fill_missing_with_row_median, axis=1)
            self._log_missing(sheet_name, df_before, df, year_cols)

        rule = get_aggregation_rule(sheet_name)

        def aggregate_column(series):
            if series.isna().all():
                return np.nan
            with np.errstate(invalid="ignore"):
                return series.sum() if rule == "sum" else series.median()

        agg_cols = [COUNTRY_COL] + year_cols
        aggregated_df = df[agg_cols].groupby(COUNTRY_COL, as_index=False).agg(aggregate_column)
        return aggregated_df

    def process_all_sheets(self, impute_missing: bool = False):
        for sheet_name, df in self.sheets.items():
            self.sheets[sheet_name] = self.process_sheet(
                sheet_name, df, impute_missing=impute_missing
            )
        print("EXCEL DATA HAS BEEN PROCESSED")
        if impute_missing and self.missing_value_log:
            print(f"{len(self.missing_value_log)} cells were imputed with the row median.")

    # ------------------------------------------------------------------
    # Outliers -- per country/year, reporting only, never auto-deleted
    # ------------------------------------------------------------------
    def find_outliers_quartiles(self, df, value_col, iqr_multiplier=1.5,
                                 lower_quantile=0.25, upper_quantile=0.75):
        """
        Flags candidate outliers within a single COUNTRY's values for one
        year/column (df must already be filtered to one country). Returns
        the flagged rows plus the IQR bounds used, so the report is
        self-explanatory. Comparing a bank only to peers in the SAME
        country avoids flagging, e.g., a large German bank as an outlier
        merely for being bigger than a typical Estonian bank.
        """
        s = pd.to_numeric(df[value_col], errors='coerce')
        valid = s.dropna()
        if len(valid) < 4:  # IQR is not meaningful with too few points
            return df.iloc[0:0], None, None

        q1 = valid.quantile(lower_quantile)
        q3 = valid.quantile(upper_quantile)
        iqr = q3 - q1
        lower_bound = q1 - iqr_multiplier * iqr
        upper_bound = q3 + iqr_multiplier * iqr

        mask = (s < lower_bound) | (s > upper_bound)
        return df.loc[mask], lower_bound, upper_bound

    def analyze_raw_outliers(self):
        """
        Detects outliers separately for every (sheet, country, year)
        combination. Logs sheet, bank, country, year, value and the IQR
        bounds that triggered the flag. Does NOT modify the data.
        """
        for sheet_name, df in self.sheets.items():
            year_cols = self._year_columns(df)
            n_flagged = 0
            for country, country_df in df.groupby(COUNTRY_COL):
                for year in year_cols:
                    flagged, lower, upper = self.find_outliers_quartiles(country_df, year)
                    for _, row in flagged.iterrows():
                        self.outlier_log.append({
                            "sheet": sheet_name,
                            "bank": row.get(BANK_COL),
                            "country": country,
                            "year": year,
                            "value": row[year],
                            "lower_bound": lower,
                            "upper_bound": upper,
                        })
                        n_flagged += 1
            if n_flagged:
                print(f"{n_flagged} candidate outliers flagged in '{sheet_name}' (per country/year)")
        return self.outlier_log

    def export_outlier_report(self, path=None):
        path = path or (DATA_DIR / "outlier_report.csv")
        report_df = pd.DataFrame(self.outlier_log)
        report_df.to_csv(path, index=False)
        print(f"Outlier report written to {path} ({len(report_df)} flagged values, "
              "with bank/country/year and IQR bounds).")
        return report_df

    def export_missing_value_report(self, path=None):
        path = path or (DATA_DIR / "missing_value_report.csv")
        log_df = pd.DataFrame(self.missing_value_log)
        log_df.to_csv(path, index=False)
        print(f"Missing value report written to {path} ({len(log_df)} imputed cells).")
        return log_df

    # ------------------------------------------------------------------
    # Balanced panel check (documents, and partly addresses, the
    # changing-sample-composition limitation for SUMMED variables)
    # ------------------------------------------------------------------
    def analyze_balanced_panel(self):
        """
        For every 'sum'-aggregated sheet, finds the subset of banks that
        report a value in ALL 5 years, re-aggregates using only that
        fixed subset, and records both the full-sample and
        balanced-panel country-year totals side by side. This isolates
        how much of a change in a summed total is driven by a changing
        number of reporting banks vs. the fixed subset alone -- it does
        not "solve" the limitation (the fixed subset is itself a
        selection), but makes its size visible instead of leaving it
        undocumented.

        n_banks_reporting_full_sample is the number of banks with a
        NON-MISSING value for that specific country/year -- NOT the
        total number of bank rows for that country in the sheet (an
        earlier version conflated the two, which meant this column was
        constant across all 5 years instead of tracking the actual,
        changing number of reporting banks).
        """
        from aggregation import AGGREGATION_RULES

        for sheet_name, df in self.sheets.items():
            if AGGREGATION_RULES.get(sheet_name) != "sum":
                continue

            year_cols = self._year_columns(df)
            numeric = df[year_cols].apply(self._numeric)
            balanced_mask = numeric.notna().all(axis=1)

            full_totals = numeric.groupby(df[COUNTRY_COL]).sum(min_count=1)
            full_reporting_counts = numeric.notna().groupby(df[COUNTRY_COL]).sum()

            balanced_numeric = numeric.loc[balanced_mask]
            balanced_countries = df.loc[balanced_mask, COUNTRY_COL]
            balanced_totals = balanced_numeric.groupby(balanced_countries).sum(min_count=1)
            n_banks_balanced = balanced_countries.value_counts()

            for country in full_totals.index:
                for year in year_cols:
                    self.balanced_panel_log.append({
                        "sheet": sheet_name,
                        "country": country,
                        "year": year,
                        "full_sample_total": full_totals.loc[country, year],
                        "balanced_panel_total": balanced_totals.loc[country, year]
                            if country in balanced_totals.index else np.nan,
                        "n_banks_reporting_full_sample": int(full_reporting_counts.loc[country, year]),
                        "n_banks_balanced_panel": int(n_banks_balanced.get(country, 0)),
                    })
        return self.balanced_panel_log

    def export_balanced_panel_report(self, path=None):
        path = path or (DATA_DIR / "balanced_panel_report.csv")
        df = pd.DataFrame(self.balanced_panel_log)
        df.to_csv(path, index=False)
        print(f"Balanced panel report written to {path} ({len(df)} rows).")
        return df

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------
    def write_excel_file(self):
        with pd.ExcelWriter(self.output_file) as writer:
            for sheet_name, df in self.sheets.items():
                df.to_excel(writer, sheet_name=sheet_name, index=False)
        print(f"Excel file '{self.output_file}' generated successfully!")

    # ------------------------------------------------------------------
    # Pipeline
    # ------------------------------------------------------------------
    def process(self, impute_missing: bool = False):
        """
        1. Read the raw workbook (bank name retained).
        2. Detect (not remove) outliers per country/year; export report
           with bank/country/year/IQR bounds.
        3. Export bank-coverage report.
        4. Export balanced-panel comparison for summed variables.
        5. Clean and aggregate every sheet per AGGREGATION_RULES.
        6. Export the missing-value imputation log (if any).
        7. Write the cleaned workbook.
        """
        self.read_excel_file()
        self.analyze_raw_outliers()
        self.export_outlier_report()
        self.analyze_coverage()
        self.export_coverage_report()
        self.analyze_balanced_panel()
        self.export_balanced_panel_report()
        self.process_all_sheets(impute_missing=impute_missing)
        if impute_missing:
            self.export_missing_value_report()
        self.write_excel_file()
        print("Processing completed!")


if __name__ == "__main__":
    tool = ExcelTool(
        input_file=str(DATA_DIR / "data.xlsx"),
        output_file=str(DATA_DIR / "output_clean.xlsx"),
    )
    tool.process(impute_missing=False)
