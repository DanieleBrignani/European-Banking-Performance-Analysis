"""
Automated tests for the aggregation and data-cleaning logic.

Run with: pytest tests/
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from aggregation import get_aggregation_rule, AGGREGATION_RULES
from data_cleaning import ExcelTool, BANK_COL, COUNTRY_COL


# ----------------------------------------------------------------------
# aggregation.py
# ----------------------------------------------------------------------
def test_absolute_variables_use_sum():
    for sheet in ["Tier 1 Capital", "NII", "Impaired loans"]:
        assert get_aggregation_rule(sheet) == "sum"


def test_ratio_variables_use_median():
    for sheet in ["Tier 1 Ratio", "Tot. cap. adequacy ratio", "ROAA",
                  "ROAE", "NII-RWAs", "Impaired loans-RWAs"]:
        assert get_aggregation_rule(sheet) == "median"


def test_unknown_sheet_raises_instead_of_guessing():
    with pytest.raises(KeyError):
        get_aggregation_rule("Some Indicator Nobody Reviewed")


def test_every_rule_is_sum_or_median():
    assert set(AGGREGATION_RULES.values()) <= {"sum", "median"}


# ----------------------------------------------------------------------
# data_cleaning.ExcelTool
# ----------------------------------------------------------------------
@pytest.fixture
def tool():
    return ExcelTool(input_file="unused.xlsx", output_file="unused.xlsx")


def _sample_df():
    return pd.DataFrame({
        BANK_COL: ["Bank A", "Bank B", "Bank C", "Bank D"],
        COUNTRY_COL: ["IT", "IT", "DE", "DE"],
        "2023": [100.0, np.nan, 500.0, 520.0],
    })


def test_sum_aggregation_ignores_nan_but_keeps_real_zero(tool):
    result = tool.process_sheet("Tier 1 Capital", _sample_df())
    it_val = result.loc[result[COUNTRY_COL] == "IT", "2023"].iloc[0]
    de_val = result.loc[result[COUNTRY_COL] == "DE", "2023"].iloc[0]
    assert it_val == 100.0        # NaN excluded, not treated as 0
    assert de_val == 1020.0       # 500 + 520


def test_median_aggregation_for_ratios(tool):
    df = pd.DataFrame({
        BANK_COL: ["Bank A", "Bank B", "Bank C", "Bank D"],
        COUNTRY_COL: ["IT", "IT", "DE", "DE"],
        "2023": [1.2, 1.5, 0.9, 50.0],  # 50.0 is a deliberate extreme value
    })
    result = tool.process_sheet("ROAA", df)
    it_val = result.loc[result[COUNTRY_COL] == "IT", "2023"].iloc[0]
    de_val = result.loc[result[COUNTRY_COL] == "DE", "2023"].iloc[0]
    assert it_val == pytest.approx(1.35)
    assert de_val == pytest.approx(25.45)  # median of [0.9, 50.0]


def test_all_nan_group_returns_nan_not_zero(tool):
    df = pd.DataFrame({
        BANK_COL: ["Bank A", "Bank B"],
        COUNTRY_COL: ["IT", "IT"],
        "2023": [np.nan, np.nan],
    })
    result = tool.process_sheet("Tier 1 Capital", df)
    assert pd.isna(result["2023"].iloc[0])


def test_outliers_are_flagged_per_country_not_globally(tool):
    """
    A bank that is merely bigger than the EU-wide average, but typical
    for ITS OWN country, must NOT be flagged -- only a bank that stands
    out from its own country's peers should be.
    """
    df = pd.DataFrame({
        BANK_COL: ["IT-A", "IT-B", "IT-C", "IT-D", "IT-E", "DE-A", "DE-B", "DE-C", "DE-D"],
        COUNTRY_COL: ["IT"] * 5 + ["DE"] * 4,
        # Italian banks cluster around ~1.0-1.2; German banks are all
        # much larger (~50) but consistent with EACH OTHER, so none of
        # them should be flagged despite being "outliers" relative to
        # the whole (mixed) sample.
        "2023": [1.0, 1.1, 0.9, 1.2, 1.05, 48.0, 50.0, 49.0, 51.0],
    })
    it_flagged, _, _ = tool.find_outliers_quartiles(df[df[COUNTRY_COL] == "IT"], "2023")
    de_flagged, _, _ = tool.find_outliers_quartiles(df[df[COUNTRY_COL] == "DE"], "2023")
    assert len(it_flagged) == 0
    assert len(de_flagged) == 0  # consistent within Germany -> not an outlier there


def test_outliers_are_traceable_to_a_bank_and_not_deleted(tool):
    df = pd.DataFrame({
        BANK_COL: ["A", "B", "C", "D", "Outlier Bank"],
        COUNTRY_COL: ["GR"] * 5,
        "2023": [1.0, 1.1, 0.9, 1.2, 50.0],
    })
    flagged, lower, upper = tool.find_outliers_quartiles(df, "2023")
    assert len(flagged) == 1
    assert flagged.iloc[0][BANK_COL] == "Outlier Bank"
    assert flagged.iloc[0]["2023"] == 50.0
    assert lower is not None and upper is not None
    assert len(df) == 5  # detection must not mutate/delete the input


def test_year_column_normalization():
    df = pd.DataFrame({
        COUNTRY_COL: ["IT"],
        BANK_COL: ["Bank A"],
        "Tier 1 Capital\nEUR 2023": [100.0],
        "Tier 1 Capital\nEUR 2022": [90.0],
    })
    normalized = ExcelTool._normalize_year_columns(df)
    assert set(normalized.columns) == {COUNTRY_COL, BANK_COL, "2023", "2022"}


def test_balanced_panel_subset_never_exceeds_full_sample(tool):
    tool.sheets = {
        "Tier 1 Capital": pd.DataFrame({
            BANK_COL: ["A", "B", "C"],
            COUNTRY_COL: ["IT", "IT", "IT"],
            "2023": [100.0, 110.0, np.nan],
            "2022": [90.0, np.nan, 80.0],
        })
    }
    tool.analyze_balanced_panel()
    rows = [r for r in tool.balanced_panel_log if r["country"] == "IT"]
    assert rows
    for r in rows:
        assert r["n_banks_balanced_panel"] <= r["n_banks_reporting_full_sample"]
