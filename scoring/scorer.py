"""
Scoring Engine
Based on:
  - IPU Indicators for Democratic Parliaments (SDG 16.6/16.7)
  - Sansad Ratna Awards methodology
  - B.PAC MLA Rating Framework
  - PRS Legislative Research metrics

Dimensions:
  1. Participation (30%) — Attendance at assembly sessions
  2. Accountability (35%) — Questions raised (oversight function)
  3. Legislative Initiative (15%) — Private bills + committee roles
  4. Probity (20%) — Criminal record (fewer/no cases = better)
"""

import numpy as np

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import (
    SERIOUS_CRIME_MULTIPLIER,
    LEGISLATIVE_BILLS_WEIGHT, LEGISLATIVE_COMMITTEE_WEIGHT,
)


def percentile_rank(value, all_values):
    """
    Compute percentile rank of a value in a distribution.
    Returns 0-100 where 100 = best performer.
    """
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    valid = [v for v in all_values if v is not None and not (isinstance(v, float) and np.isnan(v))]
    if not valid:
        return None
    count_below = sum(1 for v in valid if v < value)
    count_equal = sum(1 for v in valid if v == value)
    rank = (count_below + 0.5 * count_equal) / len(valid) * 100
    return round(rank, 1)


def inverse_percentile_rank(value, all_values):
    """
    Inverse percentile rank: lower values score higher.
    Used for criminal cases (0 cases = best).
    """
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    valid = [v for v in all_values if v is not None and not (isinstance(v, float) and np.isnan(v))]
    if not valid:
        return None
    count_above = sum(1 for v in valid if v > value)
    count_equal = sum(1 for v in valid if v == value)
    rank = (count_above + 0.5 * count_equal) / len(valid) * 100
    return round(rank, 1)


def _is_valid(val):
    """Check if a value is usable (not None, not NaN)."""
    if val is None:
        return False
    if isinstance(val, float) and np.isnan(val):
        return False
    return True


def score_participation(records):
    """
    PARTICIPATION (30%) — Assembly attendance.
    Maps to IPU Target 1 (Effective) and Target 6 (Participatory).
    Attendance is the most fundamental duty of a legislator.
    """
    non_minister_att = [r["attendance_pct"] for r in records
                        if not r["is_minister"] and _is_valid(r.get("attendance_pct"))]

    for r in records:
        if r["is_minister"]:
            r["participation_score"] = None
        elif _is_valid(r.get("attendance_pct")):
            r["participation_score"] = percentile_rank(r["attendance_pct"], non_minister_att)
        else:
            r["participation_score"] = None

    return records


def score_accountability(records):
    """
    ACCOUNTABILITY (35%) — Questions raised.
    Maps to IPU Target 2 (Accountable) and Target 4 (Responsive).
    Questions are the primary tool for legislative oversight of the executive.
    Both starred and unstarred questions demonstrate active scrutiny.
    """
    non_minister_q = [r["questions_asked"] for r in records
                      if not r["is_minister"] and _is_valid(r.get("questions_asked"))]

    for r in records:
        if r["is_minister"]:
            r["accountability_score"] = None
        elif _is_valid(r.get("questions_asked")):
            r["accountability_score"] = percentile_rank(r["questions_asked"], non_minister_q)
        else:
            r["accountability_score"] = None

    return records


def score_legislative(records):
    """
    LEGISLATIVE INITIATIVE (15%) — Private member bills + committee roles.
    Maps to IPU Target 1 (Effective) — lawmaking function.
    Private member bills show initiative beyond party mandate.
    Committee participation reflects depth of engagement.
    """
    all_bills = [r["private_bills_count"] for r in records if not r["is_minister"]]
    all_committee_points = [r["committee_points"] for r in records if not r["is_minister"]]

    has_bills_data = any(b > 0 for b in all_bills)
    has_committee_data = any(c > 0 for c in all_committee_points)

    for r in records:
        if r["is_minister"]:
            r["legislative_score"] = None
            continue

        bills_score = None
        committee_score = None

        if has_bills_data:
            bills_score = percentile_rank(r["private_bills_count"], all_bills)
        if has_committee_data:
            committee_score = percentile_rank(r["committee_points"], all_committee_points)

        if bills_score is not None and committee_score is not None:
            r["legislative_score"] = round(
                bills_score * LEGISLATIVE_BILLS_WEIGHT +
                committee_score * LEGISLATIVE_COMMITTEE_WEIGHT, 1)
        elif bills_score is not None:
            r["legislative_score"] = bills_score
        elif committee_score is not None:
            r["legislative_score"] = committee_score
        else:
            r["legislative_score"] = 50.0  # Default when no data available

    return records


def score_probity(records):
    """
    PROBITY (20%) — Criminal record.
    Maps to IPU Target 2 (Accountable) — parliamentary ethics.
    Measures only criminal cases declared in election affidavits.
    Education deliberately excluded — it reflects background, not performance.
    Fewer/no cases = higher score. Serious IPC sections incur a penalty.
    """
    all_criminal = [r["criminal_cases_count"] for r in records]

    for r in records:
        score = inverse_percentile_rank(r["criminal_cases_count"], all_criminal)

        # Apply severity penalty for serious criminal charges
        if score is not None and r.get("serious_criminal_cases", False):
            score = round(score * SERIOUS_CRIME_MULTIPLIER, 1)

        r["probity_score"] = score

    return records


def score_all(records):
    """Apply all scoring dimensions."""
    print("\n[SCORER] Computing scores...")

    records = score_participation(records)
    print("  [SCORER] Participation scores computed (IPU: Effective + Participatory)")

    records = score_accountability(records)
    print("  [SCORER] Accountability scores computed (IPU: Accountable + Responsive)")

    records = score_legislative(records)
    print("  [SCORER] Legislative Initiative scores computed (IPU: Effective — Lawmaking)")

    records = score_probity(records)
    print("  [SCORER] Probity scores computed (IPU: Accountable — Ethics)")

    scored = sum(1 for r in records if not r["is_minister"])
    ministers = sum(1 for r in records if r["is_minister"])
    print(f"  [SCORER] Scored {scored} MLAs, {ministers} ministers (separate track)")
    print("[SCORER] Done.\n")

    return records
