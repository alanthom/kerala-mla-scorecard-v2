"""
Dashboard Renderer
Generates self-contained HTML dashboard from scored MLA data.
"""

import json
import os
from collections import Counter, defaultdict
from datetime import date

from jinja2 import Environment, FileSystemLoader

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import TEMPLATE_DIR, OUTPUT_DIR, PARTY_COLORS


def prepare_chart_data(records):
    """Prepare data structures for Chart.js visualizations."""

    regular = [r for r in records if r["scoring_track"] == "regular"]
    ministers = [r for r in records if r["scoring_track"] == "minister"]

    # Grade distribution
    grade_dist = Counter()
    for r in records:
        if r.get("composite_score") is not None:
            grade_dist[r["grade"]] += 1
    # Ensure all grades present in order
    ordered_grades = ["A+", "A", "B+", "B", "C", "D"]
    grade_distribution = {g: grade_dist.get(g, 0) for g in ordered_grades}

    # Party-wise average composite score (only parties with 3+ MLAs)
    party_scores_list = defaultdict(list)
    for r in regular:
        if r.get("composite_score") is not None:
            party_scores_list[r["party"]].append(r["composite_score"])

    party_scores = {}
    for party, scores in sorted(party_scores_list.items(), key=lambda x: -sum(x[1])/len(x[1])):
        if len(scores) >= 3:
            party_scores[party] = round(sum(scores) / len(scores), 1)

    # Scatter data: attendance vs questions
    scatter_data = []
    for r in regular:
        att = r.get("attendance_pct")
        q = r.get("questions_asked")
        if att is not None and q is not None:
            try:
                scatter_data.append({
                    "x": round(float(att), 1),
                    "y": int(float(q)),
                    "name": r["name"],
                    "composite": r.get("composite_score"),
                })
            except (ValueError, TypeError):
                pass

    # Alliance comparison (radar chart)
    alliance_dims = defaultdict(lambda: defaultdict(list))
    for r in regular:
        alliance = r.get("alliance", "Other")
        for dim in ["participation", "accountability", "legislative", "probity"]:
            score = r.get(f"{dim}_score")
            if score is not None:
                alliance_dims[alliance][dim].append(score)

    alliance_scores = {}
    for alliance, dims in alliance_dims.items():
        alliance_scores[alliance] = {
            dim: round(sum(scores) / len(scores), 1) if scores else 0
            for dim, scores in dims.items()
        }

    return {
        "grade_distribution": grade_distribution,
        "party_scores": party_scores,
        "scatter_data": scatter_data,
        "alliance_scores": alliance_scores,
    }


def prepare_table_data(records):
    """Prepare data for Tabulator tables."""

    # Fields to include in JSON (avoid large nested objects)
    table_fields = [
        "name", "constituency", "party", "alliance", "age", "gender",
        "attendance_pct", "questions_asked",
        "participation_score", "accountability_score",
        "legislative_score", "probity_score", "composite_score",
        "grade", "rank", "total_ranked", "scoring_track",
        "criminal_cases_count", "total_assets", "education_myneta",
        "private_bills_count", "committee_points", "note",
        "is_minister",
    ]

    def clean_record(r):
        """Clean record for JSON serialization."""
        cleaned = {}
        for field in table_fields:
            val = r.get(field)
            if val is None:
                cleaned[field] = None
            elif isinstance(val, float):
                if val != val:  # NaN check
                    cleaned[field] = None
                else:
                    cleaned[field] = round(val, 1)
            elif isinstance(val, bool):
                cleaned[field] = val
            else:
                cleaned[field] = val
        return cleaned

    regular = [clean_record(r) for r in records if r["scoring_track"] == "regular"]
    ministers = [clean_record(r) for r in records if r["scoring_track"] == "minister"]

    return regular, ministers


def compute_summary_stats(records):
    """Compute summary statistics for the header."""
    regular = [r for r in records if r["scoring_track"] == "regular"]
    ministers = [r for r in records if r["scoring_track"] == "minister"]

    scored = [r for r in records if r.get("composite_score") is not None]
    composites = [r["composite_score"] for r in regular if r.get("composite_score") is not None]
    attendances = [r["attendance_pct"] for r in regular
                   if r.get("attendance_pct") is not None
                   and not (isinstance(r["attendance_pct"], float) and r["attendance_pct"] != r["attendance_pct"])]
    questions = [r["questions_asked"] for r in regular
                 if r.get("questions_asked") is not None
                 and not (isinstance(r["questions_asked"], float) and r["questions_asked"] != r["questions_asked"])]

    return {
        "total_mlas": len(records),
        "total_scored": len(scored),
        "avg_composite": round(sum(composites) / len(composites), 1) if composites else 0,
        "avg_attendance": round(sum(attendances) / len(attendances), 1) if attendances else 0,
        "avg_questions": int(sum(questions) / len(questions)) if questions else 0,
        "ministers_count": len(ministers),
    }


def get_parties(records):
    """Get sorted list of unique parties."""
    return sorted(set(r["party"] for r in records if r.get("party")))


def render(records):
    """Generate the HTML dashboard."""
    print("\n[RENDERER] Generating dashboard...")

    # Prepare data
    chart_data = prepare_chart_data(records)
    regular_data, minister_data = prepare_table_data(records)
    stats = compute_summary_stats(records)
    parties = get_parties(records)

    # Setup Jinja2
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
    template = env.get_template("index.html")

    # Render
    html = template.render(
        # Summary stats
        total_mlas=stats["total_mlas"],
        total_scored=stats["total_scored"],
        avg_composite=stats["avg_composite"],
        avg_attendance=stats["avg_attendance"],
        avg_questions=stats["avg_questions"],
        ministers_count=stats["ministers_count"],
        data_date="Feb 2026",
        generated_date=date.today().isoformat(),

        # Table data (as JSON)
        mla_data_json=json.dumps(regular_data, default=str),
        minister_data_json=json.dumps(minister_data, default=str),

        # Chart data (as JSON)
        grade_distribution_json=json.dumps(chart_data["grade_distribution"]),
        party_scores_json=json.dumps(chart_data["party_scores"]),
        scatter_data_json=json.dumps(chart_data["scatter_data"]),
        alliance_scores_json=json.dumps(chart_data["alliance_scores"]),

        # Filters
        parties=parties,
        party_colors_json=json.dumps(PARTY_COLORS),
    )

    # Write output
    output_path = os.path.join(OUTPUT_DIR, "dashboard.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"  [RENDERER] Dashboard saved to {output_path}")
    print(f"  [RENDERER] File size: {os.path.getsize(output_path) / 1024:.0f} KB")
    print("[RENDERER] Done.\n")

    return output_path
