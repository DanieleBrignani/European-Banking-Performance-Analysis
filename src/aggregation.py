"""
aggregation.py
==============

Defines the economically correct aggregation rule for each banking indicator.

Rationale
---------
The sheets in the source workbook mix two different kinds of variables:

1. ABSOLUTE / MONETARY variables (Tier 1 Capital, NII, Impaired loans):
   these are stock or flow amounts expressed in EUR (verified against the
   raw column headers, e.g. "Tier 1 Capital\nEUR 2023" -- not thousands
   of EUR, despite an earlier version of this project mislabeling them
   as "th EUR"). Taking a
   mean or median of these across banks answers "how large is a typical
   bank?", which is NOT what we want when describing a national banking
   system. To describe the SYSTEM (all banks together), the economically
   correct aggregation is a SUM across banks within a country/year.

2. RATIO variables (Tier 1 Ratio, Total Capital Adequacy Ratio, ROAA, ROAE,
   NII/RWA, Impaired loans/RWA -- note: "Impaired loans-RWAs" is impaired
   loans over risk-weighted assets, as labeled by BankFocus; it is NOT the
   standard NPL ratio, which is conventionally non-performing loans over
   gross loans -- see data/README.md): these are already normalized (percentages).
   A simple mean is sensitive to extreme bank-level observations -- one
   bank with an unusually high or low ratio can pull a country's mean far
   from what most banks in that country actually look like (this is
   distinct from a raw size difference between banks, which a ratio has
   already normalized away). The defensible choices are:
     - MEDIAN, which is less sensitive to those extreme observations, if we
       want to describe the "representative" (typical) bank and are
       transparent about that interpretation, or
     - a WEIGHTED mean / recomputing the ratio from aggregated numerators
       and denominators, if we want to describe the system as a whole and
       have the weights (RWA, total assets, equity, etc.) available.

   This project does not have reliable weights for every ratio, so we use
   MEDIAN for ratios and explicitly document, in the README, that this
   describes the "typical bank", not the aggregate national system.

AGGREGATION_RULES therefore maps each sheet/indicator name (as it appears in
the source Excel workbook) to the aggregation function that should be used
when collapsing multiple banks into one country-year observation.
"""

# Sheet name -> aggregation rule ("sum" or "median")
AGGREGATION_RULES = {
    # Absolute / monetary variables -> sum describes the national system
    "Tier 1 Capital": "sum",
    "NII": "sum",
    "Impaired loans": "sum",

    # Ratio variables -> median describes the representative (typical) bank
    "Tier 1 Ratio": "median",
    "Tot. cap. adequacy ratio": "median",
    "ROAA": "median",
    "ROAE": "median",
    "NII-RWAs": "median",
    "Impaired loans-RWAs": "median",
}

# Human-readable description of what each rule means, used to build the
# README / data dictionary automatically.
AGGREGATION_DESCRIPTIONS = {
    "sum": (
        "Summed across all reporting banks in the country-year. "
        "Represents the aggregate value for the national banking system."
    ),
    "median": (
        "Median across all reporting banks in the country-year. "
        "Represents the typical/representative bank, NOT the national "
        "system total, since no reliable weights (RWA, total assets) "
        "were available to compute a weighted average or to recompute "
        "the ratio from aggregated numerator/denominator."
    ),
}


def get_aggregation_rule(sheet_name: str) -> str:
    """
    Returns the aggregation rule ('sum' or 'median') for a given sheet name.

    Raises a KeyError with a clear message if the sheet is not recognized,
    instead of silently defaulting -- an unrecognized indicator should be
    reviewed and added to AGGREGATION_RULES explicitly rather than
    aggregated with a guessed rule.
    """
    try:
        return AGGREGATION_RULES[sheet_name]
    except KeyError as exc:
        raise KeyError(
            f"No aggregation rule defined for sheet '{sheet_name}'. "
            "Add it to AGGREGATION_RULES in src/aggregation.py before "
            "processing this sheet -- do not guess."
        ) from exc
