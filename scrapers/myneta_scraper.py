"""
MyNeta Scraper
Phase 1: Scrape winners list (summary data for all 140 MLAs)
Phase 2: Scrape individual profiles (detailed criminal/asset data)
"""

import json
import os
import re
import time

import requests
from bs4 import BeautifulSoup

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import (
    MYNETA_WINNERS_URL, MYNETA_CANDIDATE_URL,
    RAW_DIR, MYNETA_PROFILES_DIR,
    REQUEST_HEADERS, MYNETA_DELAY_SECONDS,
)


def parse_money(text):
    """Parse Indian currency string to float. E.g., 'Rs 3,02,34,747~ 3 Crore+' -> 30234747.0"""
    if not text or not isinstance(text, str):
        return 0.0
    # Extract the first Rs X,XX,XX,XXX pattern (before the ~)
    # Format: "Rs 3,02,34,747~ 3 Crore+"
    parts = text.split("~")
    raw = parts[0] if parts else text
    # Remove Rs, Rs., currency symbol, commas, spaces
    cleaned = re.sub(r'[Rrs\.\s,+]', '', raw)
    # Try to extract numeric part
    match = re.search(r'(\d+)', cleaned)
    if match:
        # Rebuild the full number from the cleaned string
        digits_only = re.sub(r'[^\d]', '', cleaned)
        try:
            return float(digits_only)
        except ValueError:
            return 0.0
    return 0.0


def normalize_name(name):
    """Create a canonical name for cross-source matching."""
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


def scrape_winners_list():
    """
    Phase 1: Scrape the winners summary table.
    Returns list of dicts with summary data + candidate_id.
    """
    cache_path = os.path.join(RAW_DIR, "myneta_winners.json")
    if os.path.exists(cache_path):
        print("  [MyNeta] Using cached winners list")
        with open(cache_path) as f:
            return json.load(f)

    print("  [MyNeta] Fetching winners list...")
    winners = []

    resp = requests.get(MYNETA_WINNERS_URL, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.content, "lxml")

    # Find all candidate entries - MyNeta uses divs or table rows
    # Look for links to candidate pages
    candidate_links = soup.find_all("a", href=re.compile(r"candidate\.php\?candidate_id=\d+"))

    seen_ids = set()
    for link in candidate_links:
        href = link.get("href", "")
        id_match = re.search(r"candidate_id=(\d+)", href)
        if not id_match:
            continue

        candidate_id = id_match.group(1)
        if candidate_id in seen_ids:
            continue
        seen_ids.add(candidate_id)

        # Get the parent row
        row = link.find_parent("tr")
        if not row:
            continue

        cells = row.find_all("td")
        # Expected columns: Serial, Name(link), Constituency, Party, Criminal Cases, Education, Assets, Liabilities
        # Name is always in cell[1], not the link text (some links have empty text)
        name = cells[1].get_text(strip=True) if len(cells) > 1 else link.get_text(strip=True)

        constituency = cells[2].get_text(strip=True) if len(cells) > 2 else ""
        party = cells[3].get_text(strip=True) if len(cells) > 3 else ""

        # Criminal cases — often in <strong> tag
        criminal_cases = 0
        if len(cells) > 4:
            case_text = cells[4].get_text(strip=True)
            case_match = re.search(r'(\d+)', case_text)
            if case_match:
                criminal_cases = int(case_match.group(1))

        education = cells[5].get_text(strip=True) if len(cells) > 5 else ""
        total_assets = cells[6].get_text(strip=True) if len(cells) > 6 else ""
        liabilities = cells[7].get_text(strip=True) if len(cells) > 7 else ""

        winner = {
            "candidate_id": candidate_id,
            "name": name,
            "name_normalized": normalize_name(name),
            "constituency": constituency,
            "party": party,
            "criminal_cases_count": criminal_cases,
            "education": education,
            "total_assets_str": total_assets,
            "total_assets": parse_money(total_assets),
            "liabilities_str": liabilities,
            "liabilities": parse_money(liabilities),
        }
        winners.append(winner)

    print(f"  [MyNeta] Found {len(winners)} candidates with IDs")

    # Save cache
    with open(cache_path, "w") as f:
        json.dump(winners, f, indent=2)

    return winners


def scrape_candidate_profile(candidate_id):
    """
    Phase 2: Scrape individual candidate profile for detailed data.
    Returns dict with criminal case details, asset breakdown, education, etc.
    """
    cache_path = os.path.join(MYNETA_PROFILES_DIR, f"{candidate_id}.json")
    if os.path.exists(cache_path):
        with open(cache_path) as f:
            return json.load(f)

    url = MYNETA_CANDIDATE_URL.format(candidate_id=candidate_id)
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.content, "lxml")

    profile = {
        "candidate_id": candidate_id,
        "criminal_cases": [],
        "serious_criminal_cases": False,
        "total_criminal_cases": 0,
        "movable_assets": 0.0,
        "immovable_assets": 0.0,
        "total_assets": 0.0,
        "total_liabilities": 0.0,
        "education": "",
        "education_detail": "",
        "profession": "",
        "name": "",
        "party": "",
        "constituency": "",
    }

    # Get page text for parsing
    page_text = soup.get_text()

    # Extract name from title or heading
    title = soup.find("title")
    if title:
        title_text = title.get_text()
        name_match = re.match(r"(.+?)\(", title_text)
        if name_match:
            profile["name"] = name_match.group(1).strip()

    # Look for party and constituency in the page
    party_match = re.search(r"Party\s*:\s*(.+?)(?:\n|<|$)", page_text)
    if party_match:
        profile["party"] = party_match.group(1).strip()

    const_match = re.search(r"Constituency\s*:\s*(.+?)(?:\n|<|$)", page_text)
    if const_match:
        profile["constituency"] = const_match.group(1).strip()

    # === Criminal Cases ===
    # Look for case tables/sections
    case_tables = soup.find_all("table")
    for table in case_tables:
        header_text = ""
        prev = table.find_previous(["h2", "h3", "h4", "b", "strong"])
        if prev:
            header_text = prev.get_text().lower()

        if "criminal" in header_text or "case" in header_text or "ipc" in header_text:
            rows = table.find_all("tr")
            for row in rows[1:]:  # Skip header
                cells = row.find_all("td")
                if len(cells) >= 2:
                    case_text = " ".join(c.get_text(strip=True) for c in cells)
                    case_info = {"raw_text": case_text}

                    # Extract IPC sections
                    ipc_matches = re.findall(r'(?:IPC|Section)\s*(\d+[A-Z]?)', case_text, re.IGNORECASE)
                    case_info["ipc_sections"] = ipc_matches

                    profile["criminal_cases"].append(case_info)

    # Count criminal cases from the page text
    case_count_match = re.search(r'(\d+)\s*(?:Criminal|criminal)\s*(?:Case|case)', page_text)
    if case_count_match:
        profile["total_criminal_cases"] = int(case_count_match.group(1))
    else:
        profile["total_criminal_cases"] = len(profile["criminal_cases"])

    # Check for serious IPC sections
    all_sections = set()
    for case in profile["criminal_cases"]:
        all_sections.update(case.get("ipc_sections", []))

    from config import SERIOUS_IPC_SECTIONS
    profile["serious_criminal_cases"] = bool(all_sections & SERIOUS_IPC_SECTIONS)

    # === Assets ===
    # Look for asset-related text
    movable_match = re.search(
        r'(?:Movable|movable)\s*(?:Assets?|assets?)\s*[:\-]?\s*(?:Rs\.?\s*)?([0-9,]+)',
        page_text
    )
    if movable_match:
        profile["movable_assets"] = parse_money(movable_match.group(1))

    immovable_match = re.search(
        r'(?:Immovable|immovable)\s*(?:Assets?|assets?)\s*[:\-]?\s*(?:Rs\.?\s*)?([0-9,]+)',
        page_text
    )
    if immovable_match:
        profile["immovable_assets"] = parse_money(immovable_match.group(1))

    total_assets_match = re.search(
        r'(?:Total\s*Assets?|Grand\s*Total)\s*[:\-]?\s*(?:Rs\.?\s*)?([0-9,]+)',
        page_text
    )
    if total_assets_match:
        profile["total_assets"] = parse_money(total_assets_match.group(1))
    else:
        profile["total_assets"] = profile["movable_assets"] + profile["immovable_assets"]

    # Liabilities
    liab_match = re.search(
        r'(?:Total\s*)?(?:Liabilities?|liabilities?)\s*[:\-]?\s*(?:Rs\.?\s*)?([0-9,]+)',
        page_text
    )
    if liab_match:
        profile["total_liabilities"] = parse_money(liab_match.group(1))

    # === Education ===
    edu_match = re.search(r'(?:Education|Qualification)\s*[:\-]?\s*(.+?)(?:\n|Profession|Self)', page_text)
    if edu_match:
        profile["education_detail"] = edu_match.group(1).strip()[:200]

    # Map to standard categories
    edu_text = profile["education_detail"].lower()
    if "doctor" in edu_text or "ph.d" in edu_text or "phd" in edu_text:
        profile["education"] = "Doctorate"
    elif "post graduate" in edu_text or "m.a" in edu_text or "m.sc" in edu_text or "mba" in edu_text:
        profile["education"] = "Post Graduate"
    elif any(x in edu_text for x in ["b.l", "ll.b", "b.tech", "mbbs", "b.e", "law"]):
        profile["education"] = "Graduate Professional"
    elif "graduate" in edu_text or "b.a" in edu_text or "b.sc" in edu_text or "b.com" in edu_text:
        profile["education"] = "Graduate"
    elif "12th" in edu_text or "higher secondary" in edu_text or "intermediate" in edu_text:
        profile["education"] = "12th Pass"
    elif "10th" in edu_text or "sslc" in edu_text or "matricul" in edu_text:
        profile["education"] = "10th Pass"
    elif "8th" in edu_text:
        profile["education"] = "8th Pass"
    elif "5th" in edu_text:
        profile["education"] = "5th Pass"
    elif "literate" in edu_text:
        profile["education"] = "Literate"
    elif "illiterate" in edu_text:
        profile["education"] = "Illiterate"
    else:
        profile["education"] = "Others"

    # === Profession ===
    prof_match = re.search(r'(?:Profession|Occupation)\s*[:\-]?\s*(.+?)(?:\n|Source)', page_text)
    if prof_match:
        profile["profession"] = prof_match.group(1).strip()[:200]

    profile["name_normalized"] = normalize_name(profile["name"])

    # Save cache
    with open(cache_path, "w") as f:
        json.dump(profile, f, indent=2)

    return profile


def scrape_all_profiles(winners):
    """Phase 2: Scrape all individual profiles with rate limiting."""
    profiles = []
    total = len(winners)

    for i, winner in enumerate(winners):
        cid = winner["candidate_id"]
        cache_path = os.path.join(MYNETA_PROFILES_DIR, f"{cid}.json")

        if os.path.exists(cache_path):
            with open(cache_path) as f:
                profiles.append(json.load(f))
            continue

        print(f"  [MyNeta] Scraping profile {i+1}/{total}: ID {cid}...")
        try:
            profile = scrape_candidate_profile(cid)
            profiles.append(profile)
        except Exception as e:
            print(f"  [MyNeta] ERROR scraping {cid}: {e}")
            profiles.append({
                "candidate_id": cid,
                "error": str(e),
                "name": winner.get("name", ""),
                "name_normalized": winner.get("name_normalized", ""),
            })

        time.sleep(MYNETA_DELAY_SECONDS)

    return profiles


def scrape():
    """Main entry point: scrape all MyNeta data."""
    print("\n[MYNETA SCRAPER] Starting...")

    # Phase 1: Winners list
    winners = scrape_winners_list()
    print(f"  [MyNeta] Phase 1 complete: {len(winners)} winners")

    # Phase 2: Individual profiles
    print(f"  [MyNeta] Phase 2: Scraping {len(winners)} individual profiles...")
    profiles = scrape_all_profiles(winners)

    successful = sum(1 for p in profiles if "error" not in p)
    print(f"  [MyNeta] Phase 2 complete: {successful}/{len(profiles)} profiles scraped")

    # Save processed data
    processed_path = os.path.join(RAW_DIR, "myneta_all_data.json")
    all_data = {
        "winners_summary": winners,
        "profiles": profiles,
    }
    with open(processed_path, "w") as f:
        json.dump(all_data, f, indent=2)

    print("[MYNETA SCRAPER] Done.\n")
    return all_data


if __name__ == "__main__":
    data = scrape()
    print(f"\nTotal winners: {len(data['winners_summary'])}")
    print(f"Total profiles: {len(data['profiles'])}")
