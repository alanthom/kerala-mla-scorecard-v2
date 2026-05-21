"""
Composite Score Calculator
Computes weighted composite scores based on IPU-aligned dimensions.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import ACTIVE_WEIGHTS, get_grade, get_alliance


DIMENSION_KEYS = {
    "participation": "participation_score",
    "accountability": "accountability_score",
    "legislative": "legislative_score",
    "probity": "probity_score",
}


def compute_composite(record, weights=None):
    """
    Compute weighted composite score for a single MLA.
    Dynamically redistributes weight for missing dimensions.
    """
    if weights is None:
        weights = ACTIVE_WEIGHTS

    weighted_sum = 0.0
    active_weight = 0.0

    for dim_name, weight in weights.items():
        score_key = DIMENSION_KEYS.get(dim_name)
        if not score_key:
            continue
        score = record.get(score_key)
        if score is not None:
            weighted_sum += score * weight
            active_weight += weight

    if active_weight > 0:
        composite = weighted_sum / active_weight
        return round(composite, 1)
    return None


def compute_minister_composite(record):
    """
    Compute a separate composite for ministers.
    Ministers only scored on probity and legislative activity.
    """
    minister_weights = {
        "probity": 0.6,
        "legislative": 0.4,
    }

    weighted_sum = 0.0
    active_weight = 0.0

    for dim_name, weight in minister_weights.items():
        score_key = DIMENSION_KEYS.get(dim_name)
        if not score_key:
            continue
        score = record.get(score_key)
        if score is not None:
            weighted_sum += score * weight
            active_weight += weight

    if active_weight > 0:
        return round(weighted_sum / active_weight, 1)
    return None


def compute_all_composites(records):
    """Compute composite scores for all MLAs."""
    print("\n[COMPOSITE] Computing composite scores...")
    print(f"  [COMPOSITE] Weights: {ACTIVE_WEIGHTS}")

    for record in records:
        if record["is_minister"]:
            record["composite_score"] = compute_minister_composite(record)
            record["scoring_track"] = "minister"
        else:
            record["composite_score"] = compute_composite(record)
            record["scoring_track"] = "regular"

        record["grade"] = get_grade(record["composite_score"])
        record["alliance"] = get_alliance(record.get("party", ""))

    # Compute ranks within each track
    regular_mlas = [r for r in records if r["scoring_track"] == "regular" and r["composite_score"] is not None]
    regular_mlas.sort(key=lambda r: r["composite_score"], reverse=True)
    for i, r in enumerate(regular_mlas):
        r["rank"] = i + 1
        r["total_ranked"] = len(regular_mlas)

    minister_mlas = [r for r in records if r["scoring_track"] == "minister" and r["composite_score"] is not None]
    minister_mlas.sort(key=lambda r: r["composite_score"], reverse=True)
    for i, r in enumerate(minister_mlas):
        r["rank"] = i + 1
        r["total_ranked"] = len(minister_mlas)

    for r in records:
        if "rank" not in r:
            r["rank"] = None
            r["total_ranked"] = None

    # Print summary
    scored_regular = len(regular_mlas)
    scored_minister = len(minister_mlas)
    avg_regular = sum(r["composite_score"] for r in regular_mlas) / scored_regular if scored_regular else 0
    avg_minister = sum(r["composite_score"] for r in minister_mlas) / scored_minister if scored_minister else 0

    print(f"  [COMPOSITE] Regular MLAs scored: {scored_regular}, avg: {avg_regular:.1f}")
    print(f"  [COMPOSITE] Ministers scored: {scored_minister}, avg: {avg_minister:.1f}")

    from collections import Counter
    grades = Counter(r["grade"] for r in records if r["composite_score"] is not None)
    print(f"  [COMPOSITE] Grade distribution: {dict(sorted(grades.items()))}")
    print("[COMPOSITE] Done.\n")

    return records
