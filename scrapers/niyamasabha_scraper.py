"""
Niyamasabha.nic.in Scraper
Scrapes bills introduced and committee memberships for each MLA.
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
    NIYAMASABHA_BILLS_URL, NIYAMASABHA_COMMITTEES_URL,
    RAW_DIR, REQUEST_HEADERS, NIYAMASABHA_DELAY_SECONDS,
    ASSEMBLY_NUMBER,
)


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


def get_session():
    """Create a requests session with proper headers."""
    session = requests.Session()
    session.headers.update(REQUEST_HEADERS)
    return session


def scrape_bills_page(session):
    """
    Scrape the bills page to find:
    1. All member names in the dropdown
    2. Bills data for the 15th KLA
    """
    cache_path = os.path.join(RAW_DIR, "bills.json")
    if os.path.exists(cache_path):
        print("  [Niyamasabha] Using cached bills data")
        with open(cache_path) as f:
            return json.load(f)

    print("  [Niyamasabha] Fetching bills page...")

    # First, get the page to see form structure and dropdown options
    resp = session.get(NIYAMASABHA_BILLS_URL, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.content, "lxml")

    # Find the member dropdown to get all member names
    member_dropdown = None
    for select in soup.find_all("select"):
        select_name = select.get("name", "").lower()
        select_id = select.get("id", "").lower()
        # Look for the "introduced by" dropdown
        if "member" in select_name or "member" in select_id or "introduced" in select_name:
            member_dropdown = select
            break

    # If not found by name, look for the dropdown with the most options (likely the member list)
    if not member_dropdown:
        all_selects = soup.find_all("select")
        if all_selects:
            member_dropdown = max(all_selects, key=lambda s: len(s.find_all("option")))

    dropdown_members = []
    if member_dropdown:
        for option in member_dropdown.find_all("option"):
            value = option.get("value", "").strip()
            text = option.get_text(strip=True)
            if value and text and text.lower() not in ("select", "all", "--select--", ""):
                dropdown_members.append({
                    "value": value,
                    "text": text,
                    "name_normalized": normalize_name(text),
                })

    print(f"  [Niyamasabha] Found {len(dropdown_members)} members in bills dropdown")

    # Now try to scrape ALL private bills for 15th KLA
    # Attempt POST with bill_type=Private and kla=15
    bills_data = {"dropdown_members": dropdown_members, "bills_by_member": {}}

    # Try to get all private member bills at once
    form_data = {}
    # Discover form action and field names
    form = soup.find("form")
    if form:
        form_action = form.get("action", NIYAMASABHA_BILLS_URL)
        if not form_action.startswith("http"):
            form_action = "https://niyamasabha.nic.in" + form_action

        # Get all form fields with default values
        for inp in form.find_all(["input", "select"]):
            name = inp.get("name")
            if not name:
                continue
            if inp.name == "select":
                # Use default selected option or first meaningful option
                selected = inp.find("option", selected=True)
                if selected:
                    form_data[name] = selected.get("value", "")
                else:
                    options = inp.find_all("option")
                    if options:
                        form_data[name] = options[0].get("value", "")
            else:
                form_data[name] = inp.get("value", "")

        print(f"  [Niyamasabha] Form fields discovered: {list(form_data.keys())}")

        # Try to set KLA to 15th and bill type to Private
        for key in form_data:
            kl = key.lower()
            if "kla" in kl:
                form_data[key] = str(ASSEMBLY_NUMBER)
            elif "type" in kl:
                # Try "Private" or the value for private bills
                form_data[key] = "2"  # Often private=2, government=1
            elif "status" in kl:
                form_data[key] = ""  # All statuses

        # Submit form to get all private bills
        print("  [Niyamasabha] Submitting bills search form...")
        try:
            resp = session.post(form_action, data=form_data, timeout=30)
            resp.raise_for_status()
            result_soup = BeautifulSoup(resp.content, "lxml")

            # Parse result table
            tables = result_soup.find_all("table")
            for table in tables:
                rows = table.find_all("tr")
                if len(rows) > 1:
                    for row in rows[1:]:
                        cells = row.find_all("td")
                        if len(cells) >= 4:
                            bill_info = {
                                "bill_no": cells[1].get_text(strip=True) if len(cells) > 1 else "",
                                "title": cells[2].get_text(strip=True) if len(cells) > 2 else "",
                                "date": cells[3].get_text(strip=True) if len(cells) > 3 else "",
                                "synopsis": cells[5].get_text(strip=True) if len(cells) > 5 else "",
                            }
                            # Try to find the introducer name in the row
                            row_text = row.get_text()
                            for member in dropdown_members:
                                if member["text"] in row_text:
                                    member_key = member["name_normalized"]
                                    if member_key not in bills_data["bills_by_member"]:
                                        bills_data["bills_by_member"][member_key] = []
                                    bills_data["bills_by_member"][member_key].append(bill_info)
                                    break

            print(f"  [Niyamasabha] Found bills for {len(bills_data['bills_by_member'])} members")

        except Exception as e:
            print(f"  [Niyamasabha] Bills form submission failed: {e}")

    # If we didn't get results from the bulk approach, try per-member
    if not bills_data["bills_by_member"] and dropdown_members:
        print("  [Niyamasabha] Trying per-member bills scraping (sampling first 10)...")
        sample_members = dropdown_members[:10]
        for member in sample_members:
            try:
                member_form = form_data.copy()
                # Set the member field
                for key in member_form:
                    if "member" in key.lower() or "introduced" in key.lower():
                        member_form[key] = member["value"]

                resp = session.post(form_action, data=member_form, timeout=30)
                result_soup = BeautifulSoup(resp.content, "lxml")

                # Count result rows
                tables = result_soup.find_all("table")
                bill_count = 0
                for table in tables:
                    rows = table.find_all("tr")
                    bill_count = max(bill_count, len(rows) - 1)

                if bill_count > 0:
                    bills_data["bills_by_member"][member["name_normalized"]] = [
                        {"count": bill_count}
                    ]
                    print(f"    {member['text']}: {bill_count} bills")

                time.sleep(NIYAMASABHA_DELAY_SECONDS)

            except Exception as e:
                print(f"    Error for {member['text']}: {e}")

    # Save cache
    with open(cache_path, "w") as f:
        json.dump(bills_data, f, indent=2)

    return bills_data


def scrape_committees(session):
    """
    Scrape committee membership data for 15th KLA.
    """
    cache_path = os.path.join(RAW_DIR, "committees.json")
    if os.path.exists(cache_path):
        print("  [Niyamasabha] Using cached committees data")
        with open(cache_path) as f:
            return json.load(f)

    print("  [Niyamasabha] Fetching committees page...")

    resp = session.get(NIYAMASABHA_COMMITTEES_URL, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.content, "lxml")

    committees_data = {"memberships": {}, "dropdown_members": []}

    # Find form structure
    form = soup.find("form")
    if not form:
        print("  [Niyamasabha] No form found on committees page")
        with open(cache_path, "w") as f:
            json.dump(committees_data, f, indent=2)
        return committees_data

    form_action = form.get("action", NIYAMASABHA_COMMITTEES_URL)
    if not form_action.startswith("http"):
        form_action = "https://niyamasabha.nic.in" + form_action

    # Get form fields
    form_data = {}
    member_dropdown = None

    for inp in form.find_all(["input", "select"]):
        name = inp.get("name")
        if not name:
            continue

        if inp.name == "select":
            options = inp.find_all("option")

            # Check if this is the member dropdown (has the most options)
            if len(options) > 50:
                member_dropdown = inp
                for opt in options:
                    val = opt.get("value", "").strip()
                    text = opt.get_text(strip=True)
                    if val and text.lower() not in ("select", "all", "--select--", ""):
                        committees_data["dropdown_members"].append({
                            "value": val,
                            "text": text,
                            "name_normalized": normalize_name(text),
                        })

            selected = inp.find("option", selected=True)
            if selected:
                form_data[name] = selected.get("value", "")
            elif options:
                form_data[name] = options[0].get("value", "")
        else:
            form_data[name] = inp.get("value", "")

    print(f"  [Niyamasabha] Found {len(committees_data['dropdown_members'])} members in committee dropdown")

    # Set KLA to 15th
    for key in form_data:
        if "kla" in key.lower():
            form_data[key] = str(ASSEMBLY_NUMBER)

    # Try getting ALL committee data at once (member=All)
    print("  [Niyamasabha] Attempting bulk committee fetch...")
    try:
        bulk_form = form_data.copy()
        # Set member to "All" or empty
        for key in bulk_form:
            if "member" in key.lower():
                bulk_form[key] = ""

        resp = session.post(form_action, data=bulk_form, timeout=60)
        resp.raise_for_status()
        result_soup = BeautifulSoup(resp.content, "lxml")

        # Parse results
        tables = result_soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            if len(rows) > 1:
                for row in rows[1:]:
                    cells = row.find_all("td")
                    if len(cells) >= 3:
                        member_name = cells[1].get_text(strip=True)
                        committee_name = cells[2].get_text(strip=True)
                        role = cells[3].get_text(strip=True) if len(cells) > 3 else "Member"

                        name_norm = normalize_name(member_name)
                        if name_norm not in committees_data["memberships"]:
                            committees_data["memberships"][name_norm] = []

                        committees_data["memberships"][name_norm].append({
                            "committee": committee_name,
                            "role": role.lower(),
                        })

        print(f"  [Niyamasabha] Found committee data for {len(committees_data['memberships'])} members")

    except Exception as e:
        print(f"  [Niyamasabha] Bulk committee fetch failed: {e}")

    # If bulk didn't work well, try per-member (sample)
    if len(committees_data["memberships"]) < 10 and committees_data["dropdown_members"]:
        print("  [Niyamasabha] Trying per-member committee scraping (sampling first 10)...")
        sample = committees_data["dropdown_members"][:10]
        member_field = None
        for key in form_data:
            if "member" in key.lower():
                member_field = key
                break

        if member_field:
            for member in sample:
                try:
                    mform = form_data.copy()
                    mform[member_field] = member["value"]

                    resp = session.post(form_action, data=mform, timeout=30)
                    result_soup = BeautifulSoup(resp.content, "lxml")

                    memberships = []
                    tables = result_soup.find_all("table")
                    for table in tables:
                        rows = table.find_all("tr")
                        for row in rows[1:]:
                            cells = row.find_all("td")
                            if len(cells) >= 2:
                                committee_name = cells[-2].get_text(strip=True) if len(cells) > 2 else cells[1].get_text(strip=True)
                                role = cells[-1].get_text(strip=True) if len(cells) > 2 else "Member"
                                memberships.append({
                                    "committee": committee_name,
                                    "role": role.lower(),
                                })

                    if memberships:
                        committees_data["memberships"][member["name_normalized"]] = memberships
                        print(f"    {member['text']}: {len(memberships)} committees")

                    time.sleep(NIYAMASABHA_DELAY_SECONDS)

                except Exception as e:
                    print(f"    Error for {member['text']}: {e}")

    # Save cache
    with open(cache_path, "w") as f:
        json.dump(committees_data, f, indent=2)

    return committees_data


def scrape():
    """Main entry point: scrape niyamasabha data."""
    print("\n[NIYAMASABHA SCRAPER] Starting...")
    session = get_session()

    bills_data = scrape_bills_page(session)
    committees_data = scrape_committees(session)

    print(f"  [Niyamasabha] Bills: data for {len(bills_data.get('bills_by_member', {}))} members")
    print(f"  [Niyamasabha] Committees: data for {len(committees_data.get('memberships', {}))} members")
    print("[NIYAMASABHA SCRAPER] Done.\n")

    return {
        "bills": bills_data,
        "committees": committees_data,
    }


if __name__ == "__main__":
    data = scrape()
    print(json.dumps(data, indent=2)[:2000])
