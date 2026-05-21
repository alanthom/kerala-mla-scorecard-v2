"""
PRS India MLA Track CSV Scraper
Downloads and parses the CSV with attendance, questions, and debate data.
"""

import os
import re
import pandas as pd
import requests

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import PRS_CSV_URL, RAW_DIR, REQUEST_HEADERS


def normalize_name(name):
    """Create a canonical name for cross-source matching."""
    if not name or not isinstance(name, str):
        return ""
    # Remove honorifics
    honorifics = [
        "Adv.", "Adv ", "Dr.", "Dr ", "Prof.", "Prof ",
        "Shri ", "Smt.", "Smt ", "Sri ", "Advocate ",
    ]
    n = name.strip()
    for h in honorifics:
        if n.startswith(h):
            n = n[len(h):]
    # Remove periods, extra spaces, lowercase
    n = re.sub(r'\.', ' ', n)
    n = re.sub(r'\s+', ' ', n).strip().lower()
    return n


def download_csv():
    """Download PRS CSV to local cache. Returns file path."""
    filepath = os.path.join(RAW_DIR, "prs_kerala_15.csv")
    if os.path.exists(filepath):
        print(f"  [PRS] Using cached CSV: {filepath}")
        return filepath

    print(f"  [PRS] Downloading CSV from PRS India...")
    resp = requests.get(PRS_CSV_URL, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()

    with open(filepath, "wb") as f:
        f.write(resp.content)
    print(f"  [PRS] Saved to {filepath} ({len(resp.content)} bytes)")
    return filepath


def parse_csv(filepath):
    """Parse the PRS CSV into a clean DataFrame."""
    df = pd.read_csv(filepath)

    # Standardize column names
    df.columns = [c.strip() for c in df.columns]

    # Rename columns for consistency
    col_map = {}
    for c in df.columns:
        cl = c.lower()
        if "mla" in cl and "name" in cl:
            col_map[c] = "name"
        elif cl == "age":
            col_map[c] = "age"
        elif "constituency" in cl:
            col_map[c] = "constituency"
        elif "gender" in cl:
            col_map[c] = "gender"
        elif "party" in cl:
            col_map[c] = "party"
        elif "membership" in cl:
            col_map[c] = "membership"
        elif "education" in cl:
            col_map[c] = "education"
        elif "start" in cl and "term" in cl:
            col_map[c] = "term_start"
        elif "end" in cl and "term" in cl:
            col_map[c] = "term_end"
        elif cl == "attendance" or (cl.startswith("attendance") and "state" not in cl and "average" not in cl):
            col_map[c] = "attendance_pct"
        elif "attendance" in cl and ("state" in cl or "average" in cl):
            col_map[c] = "state_avg_attendance"
        elif "question" in cl and ("state" not in cl and "average" not in cl):
            col_map[c] = "questions_asked"
        elif "question" in cl and ("state" in cl or "average" in cl):
            col_map[c] = "state_avg_questions"
        elif "debate" in cl and ("state" not in cl and "average" not in cl):
            col_map[c] = "num_debates"
        elif "debate" in cl and ("state" in cl or "average" in cl):
            col_map[c] = "state_avg_debates"
        elif "note" in cl:
            col_map[c] = "note"
        elif "term" in cl and "state" not in cl:
            col_map[c] = "term"
        elif "state" == cl:
            col_map[c] = "state"
        elif "image" in cl:
            col_map[c] = "image_url"

    df = df.rename(columns=col_map)

    # Convert numeric fields (handle dashes and empty strings)
    for col in ["attendance_pct", "questions_asked", "num_debates",
                "state_avg_attendance", "state_avg_questions", "state_avg_debates"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].replace(["--", "-", ""], pd.NA), errors="coerce")

    if "age" in df.columns:
        df["age"] = pd.to_numeric(df["age"], errors="coerce")

    # Identify ministers
    df["is_minister"] = False
    if "note" in df.columns:
        df["is_minister"] = df["note"].fillna("").str.lower().str.contains("minister|speaker|deputy speaker")

    # Add normalized name for matching
    df["name_normalized"] = df["name"].apply(normalize_name)

    # Add constituency normalized
    if "constituency" in df.columns:
        df["constituency_normalized"] = df["constituency"].apply(
            lambda x: re.sub(r'\s+', ' ', re.sub(r'[^a-zA-Z\s]', '', str(x))).strip().lower()
            if pd.notna(x) else ""
        )

    # Deduplicate: for constituencies with multiple entries (by-elections),
    # keep only the MLA who served most recently (latest term_start).
    # This ensures exactly 140 MLAs (one per constituency).
    if "term_start" in df.columns:
        df["term_start_dt"] = pd.to_datetime(df["term_start"], errors="coerce")
        df = df.sort_values("term_start_dt", ascending=False)
        df = df.drop_duplicates(subset="constituency", keep="first")
        df = df.drop(columns=["term_start_dt"])
        df = df.reset_index(drop=True)

    return df


def scrape():
    """Main entry point: download and parse PRS data."""
    print("\n[PRS SCRAPER] Starting...")
    filepath = download_csv()
    df = parse_csv(filepath)

    # Summary stats
    total = len(df)
    ministers = df["is_minister"].sum()
    has_attendance = df["attendance_pct"].notna().sum()
    has_questions = df["questions_asked"].notna().sum()
    has_debates = df["num_debates"].notna().sum()

    avg_att = df.loc[~df["is_minister"], "attendance_pct"].mean()
    avg_q = df.loc[~df["is_minister"], "questions_asked"].mean()

    print(f"  [PRS] Total MLAs: {total}")
    print(f"  [PRS] Ministers identified: {ministers}")
    print(f"  [PRS] With attendance data: {has_attendance}")
    print(f"  [PRS] With questions data: {has_questions}")
    print(f"  [PRS] With debates data: {has_debates}")
    print(f"  [PRS] Avg attendance (non-ministers): {avg_att:.1f}%")
    print(f"  [PRS] Avg questions (non-ministers): {avg_q:.1f}")
    print("[PRS SCRAPER] Done.\n")

    return df


if __name__ == "__main__":
    df = scrape()
    print(df[["name", "constituency", "party", "attendance_pct", "questions_asked", "num_debates", "is_minister"]].to_string())
