"""
Kerala MLA Scorecard - Configuration
All constants, URLs, weights, and mappings.
"""

import os

# === Project Paths ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
RAW_DIR = os.path.join(DATA_DIR, "raw")
PROCESSED_DIR = os.path.join(DATA_DIR, "processed")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
TEMPLATE_DIR = os.path.join(BASE_DIR, "dashboard", "templates")
MYNETA_PROFILES_DIR = os.path.join(RAW_DIR, "myneta_profiles")

# === Data Source URLs ===
PRS_CSV_URL = "https://prsindia.org/files/mlatrack/kerala/15/kerala_assembly_term_15.csv"

MYNETA_WINNERS_URL = "https://www.myneta.info/Kerala2021/index.php?action=show_winners&sort=candidate"
MYNETA_CANDIDATE_URL = "https://www.myneta.info/Kerala2021/candidate.php?candidate_id={candidate_id}"

NIYAMASABHA_BILLS_URL = "https://niyamasabha.nic.in/index.php/bills/billview"
NIYAMASABHA_COMMITTEES_URL = "https://niyamasabha.nic.in/index.php/committe/contents/membersearch"

# === Scraping Settings ===
REQUEST_HEADERS = {
    "User-Agent": "Kerala-MLA-Scorecard-Research/1.0 (Academic Research Project)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}
MYNETA_DELAY_SECONDS = 2.0
NIYAMASABHA_DELAY_SECONDS = 3.0

# === Assembly Details ===
ASSEMBLY_NUMBER = 15
ASSEMBLY_TERM = "2021-2026"
ASSEMBLY_START = "2021-06-01"
ASSEMBLY_END = "2026-02-24"
TOTAL_MLAS = 140

# === Scoring Methodology ===
# Based on: IPU Indicators for Democratic Parliaments, Sansad Ratna Awards,
# B.PAC Framework, and PRS Legislative Research methodology.
#
# The IPU framework organizes parliamentary performance around 7 SDG-aligned
# targets: effective, accountable, transparent, responsive, inclusive,
# participatory, and representative. We map available data to these.
#
# Dimensions:
#   1. PARTICIPATION (30%) — Maps to IPU "Effective" + "Participatory"
#      Assembly attendance is the most basic duty of a legislator.
#      Sansad Ratna and B.PAC both weight attendance heavily.
#
#   2. ACCOUNTABILITY (35%) — Maps to IPU "Accountable" + "Responsive"
#      Questions are the primary oversight tool. The IPU framework
#      emphasizes government scrutiny as a core parliamentary function.
#      Sansad Ratna uses questions as the top criterion.
#
#   3. LEGISLATIVE INITIATIVE (15%) — Maps to IPU "Effective" (lawmaking)
#      Private member bills + committee work measure proactive contribution.
#
#   4. PROBITY (20%) — Maps to IPU "Accountable" (ethics/integrity)
#      Criminal record is the sole metric here. Education was deliberately
#      excluded as it reflects background, not legislative performance.
#
# Ministers are scored on a separate track since they represent the
# government and do not ask questions or sign the attendance register.

ACTIVE_WEIGHTS = {
    "participation": 0.30,
    "accountability": 0.35,
    "legislative": 0.15,
    "probity": 0.20,
}

# === Scoring Sub-weights ===
LEGISLATIVE_BILLS_WEIGHT = 0.6
LEGISLATIVE_COMMITTEE_WEIGHT = 0.4

# === Committee Role Points ===
COMMITTEE_ROLE_POINTS = {
    "chairperson": 10,
    "ex-officio chairperson": 8,
    "ex-officio member": 2,
    "member": 3,
}

# === Education data is retained for display but NOT used in scoring ===

# === Criminal Case Severity ===
# IPC sections considered "serious"
SERIOUS_IPC_SECTIONS = {
    "302", "307", "304", "306",  # Murder, attempt to murder
    "376", "354", "509",          # Sexual offences
    "363", "364", "365", "366", "367", "368", "369",  # Kidnapping
    "395", "396", "397", "398", "399", "400",          # Dacoity/robbery
    "120B",                       # Criminal conspiracy
    "153A", "153B",               # Promoting enmity
    "420",                        # Cheating
    "467", "468", "471",          # Forgery
    "13",                         # Prevention of Corruption Act
}
SERIOUS_CRIME_MULTIPLIER = 0.7

# === Grade Mapping ===
GRADES = [
    (90, "A+"),
    (80, "A"),
    (70, "B+"),
    (60, "B"),
    (50, "C"),
    (0, "D"),
]

def get_grade(score):
    """Return letter grade for a composite score."""
    if score is None:
        return "N/A"
    for threshold, grade in GRADES:
        if score >= threshold:
            return grade
    return "D"

# === Party Color Mapping ===
PARTY_COLORS = {
    "CPI(M)": "#FF0000",
    "Communist Party Of India(Marxist)": "#FF0000",
    "CPI": "#FF4444",
    "Communist Party Of India": "#FF4444",
    "INC": "#00BFFF",
    "Indian National Congress": "#00BFFF",
    "IUML": "#006400",
    "Indian Union Muslim League": "#006400",
    "BJP": "#FF9933",
    "Bharatiya Janata Party": "#FF9933",
    "KC(M)": "#800080",
    "Kerala Congress": "#800080",
    "JD(S)": "#008000",
    "NCP": "#004080",
    "RSP": "#CC0000",
    "Revolutionary Socialist Party": "#CC0000",
    "Independent": "#808080",
    "IND": "#808080",
}

# === Name Override Mapping ===
# For MLAs whose names differ significantly across sources
# Format: {"prs_name_normalized": "myneta_name_normalized"}
NAME_OVERRIDES = {
    # Add overrides as we discover mismatches during merging
}

# === Alliance Mapping ===
LDF_PARTIES = [
    "CPI(M)", "Communist Party Of India(Marxist)",
    "CPI", "Communist Party Of India",
    "JD(S)", "Janata Dal (Secular)",
    "NCP", "Nationalist Congress Party",
    "KC(M)", "Kerala Congress (Mani)",
    "LJD", "Loktantrik Janata Dal",
    "INL", "Indian National League",
    "KC(B)", "Kerala Congress (B)",
    "Cong(S)", "Congress (S)",
    "JKC", "Janadhipathya Kerala Congress",
]

UDF_PARTIES = [
    "INC", "Indian National Congress",
    "IUML", "Indian Union Muslim League",
    "KC(Jacob)", "Kerala Congress (Jacob)",
    "RSP", "Revolutionary Socialist Party",
    "RMPI", "Revolutionary Marxist Party Of India",
]

def get_alliance(party):
    """Determine LDF/UDF/Other alliance from party name."""
    if party in LDF_PARTIES:
        return "LDF"
    elif party in UDF_PARTIES:
        return "UDF"
    else:
        return "Other"
