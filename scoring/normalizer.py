"""
Data Normalizer and Merger
Merges data from PRS, MyNeta, and Niyamasabha into a unified MLA record.
Uses fuzzy name matching with constituency confirmation.
"""

import json
import os
import re
from difflib import SequenceMatcher

import pandas as pd

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import PROCESSED_DIR, NAME_OVERRIDES


def normalize_name(name):
    """Canonical name: strip honorifics, periods, lowercase."""
    if not name or not isinstance(name, str):
        return ""
    honorifics = [
        "Adv.", "Adv ", "Dr.", "Dr ", "Prof.", "Prof ",
        "Shri ", "Smt.", "Smt ", "Sri ", "Advocate ",
    ]
    n = name.strip()
    for h in honorifics:
        if n.lower().startswith(h.lower()):
            n = n[len(h):]
    n = re.sub(r'\.', ' ', n)
    n = re.sub(r'\s+', ' ', n).strip().lower()
    return n


def normalize_constituency(name):
    """Normalize constituency name for matching."""
    if not name or not isinstance(name, str):
        return ""
    n = re.sub(r'\(.*?\)', '', name)  # Remove (SC), (ST) etc
    n = re.sub(r'[^a-zA-Z\s]', '', n)
    n = re.sub(r'\s+', ' ', n).strip().lower()
    return n


def fuzzy_match_score(name1, name2):
    """Compute similarity between two names."""
    if not name1 or not name2:
        return 0.0
    return SequenceMatcher(None, name1, name2).ratio()


def fuzzy_match_name(target_name, candidates, threshold=0.75):
    """
    Find the best matching name from a list of candidates.
    Returns (best_match_index, score) or (None, 0) if no match above threshold.
    """
    target_norm = normalize_name(target_name)

    # Check overrides first
    if target_norm in NAME_OVERRIDES:
        override_name = NAME_OVERRIDES[target_norm]
        for i, c in enumerate(candidates):
            c_norm = normalize_name(c) if isinstance(c, str) else c.get("name_normalized", "")
            if c_norm == override_name:
                return i, 1.0

    best_idx = None
    best_score = 0.0

    for i, candidate in enumerate(candidates):
        c_norm = normalize_name(candidate) if isinstance(candidate, str) else candidate.get("name_normalized", "")

        # Exact match
        if target_norm == c_norm:
            return i, 1.0

        # Fuzzy match
        score = fuzzy_match_score(target_norm, c_norm)

        # Boost if one name contains the other
        if target_norm in c_norm or c_norm in target_norm:
            score = max(score, 0.85)

        if score > best_score:
            best_score = score
            best_idx = i

    if best_score >= threshold:
        return best_idx, best_score
    return None, 0.0


def merge_data(prs_df, myneta_data, niyamasabha_data):
    """
    Merge all data sources into a single list of MLA records.
    PRS is the master list (140 MLAs).
    """
    print("\n[MERGER] Starting data merge...")

    myneta_profiles = myneta_data.get("profiles", [])
    myneta_winners = myneta_data.get("winners_summary", [])
    bills_data = niyamasabha_data.get("bills", {}).get("bills_by_member", {})
    committee_data = niyamasabha_data.get("committees", {}).get("memberships", {})

    merged_records = []
    match_stats = {"myneta_matched": 0, "myneta_unmatched": 0,
                   "bills_matched": 0, "committees_matched": 0}

    for _, row in prs_df.iterrows():
        record = {
            # PRS data
            "name": row.get("name", ""),
            "name_normalized": normalize_name(row.get("name", "")),
            "constituency": row.get("constituency", ""),
            "constituency_normalized": normalize_constituency(row.get("constituency", "")),
            "party": row.get("party", ""),
            "age": row.get("age"),
            "gender": row.get("gender", ""),
            "education_prs": row.get("education", ""),
            "attendance_pct": row.get("attendance_pct"),
            "questions_asked": row.get("questions_asked"),
            "num_debates": row.get("num_debates"),
            "is_minister": row.get("is_minister", False),
            "note": row.get("note", ""),
            "state_avg_attendance": row.get("state_avg_attendance"),
            "state_avg_questions": row.get("state_avg_questions"),
            "state_avg_debates": row.get("state_avg_debates"),
            "image_url": row.get("image_url", ""),

            # MyNeta data (to be filled)
            "criminal_cases_count": 0,
            "serious_criminal_cases": False,
            "total_assets": 0.0,
            "movable_assets": 0.0,
            "immovable_assets": 0.0,
            "total_liabilities": 0.0,
            "education_myneta": "",
            "profession": "",

            # Niyamasabha data (to be filled)
            "private_bills_count": 0,
            "private_bills": [],
            "committee_memberships": [],
            "committee_points": 0,
        }

        mla_norm = record["name_normalized"]
        const_norm = record["constituency_normalized"]

        # === Match with MyNeta ===
        # Primary source: winners summary (reliable tabular data)
        # Secondary source: individual profiles (for criminal case detail)
        matched_myneta = False

        # Try winners list first (constituency matching for accuracy)
        best_winner_idx = None
        best_winner_score = 0.0

        for i, winner in enumerate(myneta_winners):
            w_name = winner.get("name_normalized", normalize_name(winner.get("name", "")))
            w_const = normalize_constituency(winner.get("constituency", ""))

            name_score = fuzzy_match_score(mla_norm, w_name)
            const_score = fuzzy_match_score(const_norm, w_const) if const_norm and w_const else 0

            # Combined score with constituency bonus
            combined = name_score * 0.6 + const_score * 0.4 if const_score > 0.5 else name_score

            if combined > best_winner_score:
                best_winner_score = combined
                best_winner_idx = i

        if best_winner_idx is not None and best_winner_score >= 0.60:
            winner = myneta_winners[best_winner_idx]
            record["criminal_cases_count"] = winner.get("criminal_cases_count", 0)
            record["total_assets"] = winner.get("total_assets", 0.0)
            record["total_liabilities"] = winner.get("liabilities", 0.0)
            record["education_myneta"] = winner.get("education", "")
            matched_myneta = True
            match_stats["myneta_matched"] += 1

        # Supplement with profile data if available (for serious crime flag)
        for profile in myneta_profiles:
            p_name = profile.get("name_normalized", normalize_name(profile.get("name", "")))
            if fuzzy_match_score(mla_norm, p_name) >= 0.75:
                # Only take fields that are non-empty and better than what we have
                if profile.get("serious_criminal_cases"):
                    record["serious_criminal_cases"] = True
                if profile.get("total_criminal_cases", 0) > 0 and record["criminal_cases_count"] == 0:
                    record["criminal_cases_count"] = profile["total_criminal_cases"]
                if profile.get("movable_assets", 0) > 0:
                    record["movable_assets"] = profile["movable_assets"]
                if profile.get("immovable_assets", 0) > 0:
                    record["immovable_assets"] = profile["immovable_assets"]
                if profile.get("profession"):
                    record["profession"] = profile["profession"]
                if not matched_myneta:
                    matched_myneta = True
                    match_stats["myneta_matched"] += 1
                break

        if not matched_myneta:
            match_stats["myneta_unmatched"] += 1

        # === Match with Niyamasabha Bills ===
        best_bill_key = None
        best_bill_score = 0.0
        for key in bills_data:
            score = fuzzy_match_score(mla_norm, key)
            if score > best_bill_score:
                best_bill_score = score
                best_bill_key = key

        if best_bill_key and best_bill_score >= 0.75:
            bills = bills_data[best_bill_key]
            if bills and isinstance(bills[0], dict) and "count" in bills[0]:
                record["private_bills_count"] = bills[0]["count"]
            else:
                record["private_bills_count"] = len(bills)
                record["private_bills"] = bills
            match_stats["bills_matched"] += 1

        # === Match with Niyamasabha Committees ===
        best_comm_key = None
        best_comm_score = 0.0
        for key in committee_data:
            score = fuzzy_match_score(mla_norm, key)
            if score > best_comm_score:
                best_comm_score = score
                best_comm_key = key

        if best_comm_key and best_comm_score >= 0.75:
            memberships = committee_data[best_comm_key]
            record["committee_memberships"] = memberships
            # Calculate committee points
            from config import COMMITTEE_ROLE_POINTS
            points = 0
            for m in memberships:
                role = m.get("role", "member").lower()
                for role_key, role_points in COMMITTEE_ROLE_POINTS.items():
                    if role_key in role:
                        points += role_points
                        break
                else:
                    points += COMMITTEE_ROLE_POINTS["member"]
            record["committee_points"] = points
            match_stats["committees_matched"] += 1

        merged_records.append(record)

    # Print merge statistics
    total = len(merged_records)
    print(f"  [MERGER] Total MLAs: {total}")
    print(f"  [MERGER] MyNeta matched: {match_stats['myneta_matched']}/{total}")
    print(f"  [MERGER] MyNeta unmatched: {match_stats['myneta_unmatched']}")
    print(f"  [MERGER] Bills data matched: {match_stats['bills_matched']}/{total}")
    print(f"  [MERGER] Committee data matched: {match_stats['committees_matched']}/{total}")

    # Save merged data
    output_path = os.path.join(PROCESSED_DIR, "merged_mla_data.json")
    with open(output_path, "w") as f:
        json.dump(merged_records, f, indent=2, default=str)
    print(f"  [MERGER] Saved to {output_path}")
    print("[MERGER] Done.\n")

    return merged_records
