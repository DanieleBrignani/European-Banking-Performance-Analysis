"""
visualization.py
=================

Generates one bar chart per indicator (sheet) from the cleaned workbook
produced by data_cleaning.py.

Fixes applied vs. earlier versions
-----------------------------------
1. UNITS: the raw BankFocus columns are labeled in plain EUR (e.g.
   "Tier 1 Capital\\nEUR 2023"), NOT thousands of EUR. An earlier version
   of this module mislabeled monetary indicators as "th EUR" (copied
   from the original notebook without checking the source headers),
   which understated the true scale by 1000x when read at face value.
   Monetary values are now converted to EUR BILLIONS for the charts
   (dividing the underlying EUR figures by 1e9) and labeled "EUR bn",
   which is also far more readable than raw EUR amounts.

2. COUNTRIES: the country list is no longer a fixed dictionary assumed
   to cover "22 EU countries". It is now built dynamically from
   whichever countries actually appear in the cleaned data -- this
   sample covers 19 countries (Bulgaria, Croatia and Hungary never
   appear, despite being listed in an earlier hardcoded dictionary).

3. x_positions: fixed the undefined-variable bug from the original
   notebook (see data_cleaning history) by building it explicitly from
   range(len(df_plot.index)).

4. PATHS: default paths resolved relative to this file's location via
   pathlib, not the current working directory.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.lines as mlines
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
FIGURES_DIR = BASE_DIR / "outputs" / "figures"

# ISO code -> full country name, for readable x-axis labels. This is a
# lookup table only -- it does NOT imply every country in it is present
# in the data. Which countries actually appear is determined at runtime
# from the cleaned workbook itself.
COUNTRY_NAMES = {
    "AT": "Austria", "BE": "Belgium", "BG": "Bulgaria", "CY": "Cyprus", "DE": "Germany",
    "EE": "Estonia", "ES": "Spain", "FI": "Finland", "FR": "France", "GR": "Greece",
    "HR": "Croatia", "HU": "Hungary", "IE": "Ireland", "IT": "Italy", "LT": "Lithuania",
    "LV": "Latvia", "LU": "Luxembourg", "MT": "Malta", "NL": "Netherlands", "PT": "Portugal",
    "SI": "Slovenia", "SK": "Slovakia",
}

# Sheets whose values are absolute monetary amounts (reported in the raw
# data in plain EUR) rather than ratios/percentages. These are converted
# to EUR billions for charting.
MONETARY_SHEETS = {"Tier 1 Capital", "NII", "Impaired loans"}

UNITS = {
    "Impaired loans-RWAs": "%",
    "Impaired loans": "EUR bn",
    "NII-RWAs": "%",
    "NII": "EUR bn",
    "ROAE": "%",
    "ROAA": "%",
    "Tot. cap. adequacy ratio": "%",
    "Tier 1 Ratio": "%",
    "Tier 1 Capital": "EUR bn",
}

YEAR_ORDER = ["2019", "2020", "2021", "2022", "2023"]

BLUES = [
    "#D0E7F9",  # Light Sky Blue
    "#73B3E7",  # Sky Blue
    "#0056A6",  # Dark Blue
    "#003F7F",  # Navy Blue
    "#002855",  # Midnight Blue
]


def plot_all_sheets(cleaned_file=None, output_dir=None):
    """
    Reads every sheet of the cleaned workbook and produces one bar chart
    per indicator, saved as a PNG in output_dir. Filenames are snake_case
    (no spaces/periods) so they render reliably as relative image links
    in Markdown/GitHub.
    """
    cleaned_file = cleaned_file or (DATA_DIR / "output_clean.xlsx")
    output_dir = Path(output_dir) if output_dir else FIGURES_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    excel = pd.ExcelFile(cleaned_file)

    for sheet in excel.sheet_names:
        df = excel.parse(sheet)

        if "Country ISO code" not in df.columns:
            print(f"Sheet '{sheet}' does not contain 'Country ISO code'. Skipping.")
            continue

        df_plot = df.set_index("Country ISO code")

        # Only keep year columns actually present, in a consistent order.
        year_cols = [c for c in YEAR_ORDER if c in df_plot.columns]
        df_plot = df_plot[year_cols]

        if sheet in MONETARY_SHEETS:
            df_plot = df_plot / 1e9  # EUR -> EUR billions

        # Country names built dynamically from whichever codes are
        # actually present -- falls back to the raw code if a country
        # isn't in the lookup table.
        df_plot.index = df_plot.index.map(lambda code: COUNTRY_NAMES.get(code, code))
        df_plot = df_plot.iloc[:, ::-1].sort_index()  # newest year first (2023 -> 2019), alphabetical countries

        fig, ax = plt.subplots(figsize=(12, 8))
        df_plot.plot(kind="bar", ax=ax, color=BLUES)

        x_positions = range(len(df_plot.index))

        if sheet == "Impaired loans-RWAs":
            ax.set_title(sheet, fontsize=14, fontweight="bold")
            ax.set_xlabel("Country", fontsize=12)
            ax.set_ylabel(UNITS[sheet], fontsize=12)

            avg_values = df_plot.mean(axis=1)

            for i, country in zip(x_positions, df_plot.index):
                ax.plot(
                    [i - 0.4, i + 0.4],
                    [avg_values[country], avg_values[country]],
                    color="red", linestyle="-", linewidth=2,
                )

            legend_patches = [
                mpatches.Patch(color=BLUES[i], label=year_cols[::-1][i])
                for i in range(len(year_cols))
            ]
            mean_line = mlines.Line2D(
                [], [], color="red", linestyle="-", linewidth=2, label="2019\u20132023 country mean"
            )
            ax.legend(handles=legend_patches + [mean_line], title="Legend")
        else:
            ax.set_title(sheet, fontsize=14, fontweight="bold")
            ax.set_xlabel("Country", fontsize=12)
            ax.set_ylabel(UNITS[sheet], fontsize=12)
            ax.legend(year_cols[::-1], title="Legend")

        ax.tick_params(axis="x", rotation=45)
        fig.tight_layout()

        filename = (
            sheet.lower()
            .replace(" ", "_")
            .replace(".", "")
            .replace("-", "_")
            .replace("__", "_")
        )
        output_chart_file = output_dir / f"{filename}.png"
        fig.savefig(output_chart_file, dpi=300)
        print(f"Chart saved as {output_chart_file}")
        plt.close(fig)


if __name__ == "__main__":
    plot_all_sheets()
