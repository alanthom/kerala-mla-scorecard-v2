#!/usr/bin/env python3
"""
Kerala MLA Performance Scorecard
Main orchestrator: scrape -> merge -> score -> render

Usage:
    python main.py                  # Full pipeline
    python main.py --scrape-only    # Only scrape data
    python main.py --score-only     # Only score (use cached data)
    python main.py --render-only    # Only render dashboard (use cached scores)
    python main.py --skip-niyamasabha  # Skip niyamasabha scraper
    python main.py --skip-myneta    # Skip MyNeta scraper (use cached/empty)
"""

import argparse
import json
import os
import sys
import time

import pandas as pd

from config import PROCESSED_DIR, OUTPUT_DIR, RAW_DIR


def run_scrape(skip_myneta=False, skip_niyamasabha=False):
    """Run all scrapers and return raw data."""
    from scrapers.prs_scraper import scrape as scrape_prs
    from scrapers.myneta_scraper import scrape as scrape_myneta
    from scrapers.niyamasabha_scraper import scrape as scrape_niyamasabha

    print("=" * 60)
    print("PHASE 1: DATA COLLECTION")
    print("=" * 60)

    # PRS (always runs - it's the master list)
    prs_df = scrape_prs()

    # MyNeta
    if skip_myneta:
        print("\n[MYNETA] Skipped (--skip-myneta)")
        myneta_data = {"winners_summary": [], "profiles": []}
        # Try to load cached data
        cached = os.path.join(RAW_DIR, "myneta_all_data.json")
        if os.path.exists(cached):
            print("  [MYNETA] Using cached data")
            with open(cached) as f:
                myneta_data = json.load(f)
    else:
        myneta_data = scrape_myneta()

    # Niyamasabha
    if skip_niyamasabha:
        print("\n[NIYAMASABHA] Skipped (--skip-niyamasabha)")
        niyamasabha_data = {"bills": {"bills_by_member": {}}, "committees": {"memberships": {}}}
        # Try to load cached data
        bills_cache = os.path.join(RAW_DIR, "bills.json")
        comm_cache = os.path.join(RAW_DIR, "committees.json")
        if os.path.exists(bills_cache):
            with open(bills_cache) as f:
                niyamasabha_data["bills"] = json.load(f)
        if os.path.exists(comm_cache):
            with open(comm_cache) as f:
                niyamasabha_data["committees"] = json.load(f)
    else:
        niyamasabha_data = scrape_niyamasabha()

    return prs_df, myneta_data, niyamasabha_data


def run_merge(prs_df, myneta_data, niyamasabha_data):
    """Merge data from all sources."""
    from scoring.normalizer import merge_data

    print("=" * 60)
    print("PHASE 2: DATA MERGING")
    print("=" * 60)

    records = merge_data(prs_df, myneta_data, niyamasabha_data)
    return records


def run_score(records):
    """Score all MLAs."""
    from scoring.scorer import score_all
    from scoring.composite import compute_all_composites

    print("=" * 60)
    print("PHASE 3: SCORING")
    print("=" * 60)

    records = score_all(records)
    records = compute_all_composites(records)
    return records


def run_render(records):
    """Render the dashboard."""
    from dashboard.renderer import render

    print("=" * 60)
    print("PHASE 4: DASHBOARD RENDERING")
    print("=" * 60)

    dashboard_path = render(records)
    return dashboard_path


def export_csv(records):
    """Export scored data to CSV."""
    csv_fields = [
        "rank", "name", "constituency", "party", "alliance",
        "age", "gender", "is_minister", "scoring_track",
        "attendance_pct", "participation_score",
        "questions_asked", "accountability_score",
        "private_bills_count", "committee_points", "legislative_score",
        "criminal_cases_count", "serious_criminal_cases", "probity_score",
        "composite_score", "grade",
        "total_assets", "total_liabilities",
    ]

    rows = []
    for r in records:
        row = {}
        for field in csv_fields:
            val = r.get(field)
            if isinstance(val, float) and val != val:  # NaN
                row[field] = ""
            else:
                row[field] = val
        rows.append(row)

    df = pd.DataFrame(rows)
    # Sort by scoring track then rank
    df = df.sort_values(["scoring_track", "rank"], ascending=[False, True])

    csv_path = os.path.join(OUTPUT_DIR, "mla_scores.csv")
    df.to_csv(csv_path, index=False)
    print(f"\n[EXPORT] CSV saved to {csv_path}")
    return csv_path


def main():
    parser = argparse.ArgumentParser(description="Kerala MLA Performance Scorecard")
    parser.add_argument("--scrape-only", action="store_true", help="Only scrape data")
    parser.add_argument("--score-only", action="store_true", help="Only score (use cached data)")
    parser.add_argument("--render-only", action="store_true", help="Only render (use cached scores)")
    parser.add_argument("--skip-niyamasabha", action="store_true", help="Skip Niyamasabha scraper")
    parser.add_argument("--skip-myneta", action="store_true", help="Skip MyNeta scraper")
    args = parser.parse_args()

    start_time = time.time()

    print("\n" + "=" * 60)
    print("  KERALA MLA PERFORMANCE SCORECARD")
    print("  15th Legislative Assembly (2021-2026)")
    print("=" * 60)

    if args.render_only:
        # Load cached scored data
        scored_path = os.path.join(PROCESSED_DIR, "scored_mla_data.json")
        if not os.path.exists(scored_path):
            print("ERROR: No cached scored data found. Run full pipeline first.")
            sys.exit(1)
        with open(scored_path) as f:
            records = json.load(f)
        dashboard_path = run_render(records)
        export_csv(records)

    elif args.score_only:
        # Load cached merged data
        merged_path = os.path.join(PROCESSED_DIR, "merged_mla_data.json")
        if not os.path.exists(merged_path):
            print("ERROR: No cached merged data found. Run scrape first.")
            sys.exit(1)
        with open(merged_path) as f:
            records = json.load(f)
        records = run_score(records)
        # Save scored data
        scored_path = os.path.join(PROCESSED_DIR, "scored_mla_data.json")
        with open(scored_path, "w") as f:
            json.dump(records, f, indent=2, default=str)
        dashboard_path = run_render(records)
        export_csv(records)

    else:
        # Full pipeline
        prs_df, myneta_data, niyamasabha_data = run_scrape(
            skip_myneta=args.skip_myneta,
            skip_niyamasabha=args.skip_niyamasabha,
        )

        if args.scrape_only:
            print("\n[DONE] Scraping complete. Run without --scrape-only to score and render.")
            return

        records = run_merge(prs_df, myneta_data, niyamasabha_data)
        records = run_score(records)

        # Save scored data
        scored_path = os.path.join(PROCESSED_DIR, "scored_mla_data.json")
        with open(scored_path, "w") as f:
            json.dump(records, f, indent=2, default=str)

        dashboard_path = run_render(records)
        csv_path = export_csv(records)

    elapsed = time.time() - start_time
    print("\n" + "=" * 60)
    print(f"  COMPLETE! ({elapsed:.1f} seconds)")
    print(f"  Dashboard: {os.path.join(OUTPUT_DIR, 'dashboard.html')}")
    print(f"  CSV Export: {os.path.join(OUTPUT_DIR, 'mla_scores.csv')}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
