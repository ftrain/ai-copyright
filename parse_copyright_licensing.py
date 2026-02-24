#!/usr/bin/env python3
"""
Parser for Copyright Alliance AI licensing data.

Fetches and parses the Copyright Alliance's listing of AI licensing deals
between copyright owners and AI companies from:
https://copyrightalliance.org/artificial-intelligence-copyright/licensing/copyright-owners/

Outputs structured CSV with fields:
  Media Company, Work Type, Content Type, License Type, AI Company, URL
"""

import csv
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup, Tag

SOURCE_URL = "https://copyrightalliance.org/artificial-intelligence-copyright/licensing/copyright-owners/"

# Maps section headings to (work_type, content_type)
SECTION_MAP = {
    "literary": ("Literary Works", "Text"),
    "music": ("Music & Audio", "Music/Audio"),
    "audiovisual": ("Audiovisual & Image", "Visual/Video"),
}


def classify_section(heading_text: str) -> tuple[str, str]:
    """Determine work_type and content_type from section heading text."""
    text = heading_text.lower()
    for key, value in SECTION_MAP.items():
        if key in text:
            return value
    return ("Unknown", "Unknown")


def parse_license_entry(li_text: str, li_element: Tag) -> dict | None:
    """Parse a single <li> bullet into license_type, ai_company, url."""
    # Extract URL from the <a> tag
    link = li_element.find("a")
    url = link.get("href", "").strip() if link else ""

    # Get the full text of the bullet
    text = li_element.get_text(strip=True)
    if not text:
        return None

    # The pattern is typically: "License Type (AI Company)"
    # or "License Type" with "(Licensees Undisclosed)" outside the link
    # The link text contains "License Type (AI Company)" or just "License Type"
    link_text = link.get_text(strip=True) if link else text

    # Try to extract AI company from parentheses in the link text
    # Pattern: "Some License Type (Company Name)"
    paren_match = re.search(r"\(([^)]+)\)\s*$", link_text)
    if paren_match:
        ai_company = paren_match.group(1).strip()
        license_type = link_text[: paren_match.start()].strip()
    else:
        license_type = link_text.strip()
        # Check for parenthetical info in the full text outside the link
        remaining = text[len(link_text) :].strip()
        paren_match2 = re.search(r"\(([^)]+)\)", remaining)
        if paren_match2:
            extra = paren_match2.group(1).strip()
            if "undisclosed" in extra.lower() or "licensee" in extra.lower():
                ai_company = "Undisclosed"
            else:
                ai_company = extra
        else:
            ai_company = "Undisclosed"

    # Clean up license type
    license_type = license_type.strip(" –-—:")

    return {
        "license_type": license_type,
        "ai_company": ai_company,
        "url": url,
    }


def fetch_page(url: str = SOURCE_URL) -> str:
    """Fetch the page HTML."""
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; CopyrightAllianceParser/1.0)"
    }
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.text


def parse_html(html: str) -> list[dict]:
    """Parse the HTML and extract all licensing entries."""
    soup = BeautifulSoup(html, "html.parser")

    # Find the main content area
    content = soup.find("div", class_="entry-content") or soup.find(
        "article"
    ) or soup

    records = []
    current_work_type = "Unknown"
    current_content_type = "Unknown"
    current_company = None

    # Walk through all elements in content order
    for element in content.descendants:
        if not isinstance(element, Tag):
            continue

        # Detect section headings — look for bold/strong text containing our keywords
        if element.name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            text = element.get_text(strip=True).lower()
            for key, (wt, ct) in SECTION_MAP.items():
                if key in text:
                    current_work_type = wt
                    current_content_type = ct
                    break

        # Section headings may also be in <strong> or <b> within <p> tags
        if element.name == "strong" or element.name == "b":
            parent = element.parent
            text = element.get_text(strip=True)

            # Check if this is a section heading
            text_lower = text.lower()
            is_section = False
            for key, (wt, ct) in SECTION_MAP.items():
                if key in text_lower and "licensing" in text_lower:
                    current_work_type = wt
                    current_content_type = ct
                    is_section = True
                    break

            if is_section:
                continue

            # Otherwise it's a company name (bold text that isn't a section heading)
            # Company names are typically in <strong> inside <p> or directly
            if text and not is_section and parent and parent.name in ("p", "li", "div", "td", "span"):
                # Avoid picking up bold text inside list items that are license entries
                if parent.name != "li":
                    current_company = text

        # Detect list items with license info
        if element.name == "li" and current_company:
            entry = parse_license_entry(element.get_text(strip=True), element)
            if entry and entry["license_type"]:
                records.append(
                    {
                        "media_company": current_company,
                        "work_type": current_work_type,
                        "content_type": current_content_type,
                        "license_type": entry["license_type"],
                        "ai_company": entry["ai_company"],
                        "url": entry["url"],
                    }
                )

    return normalize_records(records)


def normalize_records(records: list[dict]) -> list[dict]:
    """Clean up and normalize parsed records."""
    for rec in records:
        # Normalize "Licensees Undisclosed" -> "Undisclosed"
        ai = rec["ai_company"]
        if "undisclosed" in ai.lower():
            rec["ai_company"] = "Undisclosed"

        # Confidential deals with dollar amounts as AI company -> Undisclosed
        if ai.startswith("$") or "confidential" in ai.lower():
            # Move the financial detail into the license type
            rec["license_type"] = f'{rec["license_type"]} ({ai})'
            rec["ai_company"] = "Undisclosed"

        # Sub-brand prefixes in license types (e.g. "Warner Chappell Music AI Partnership")
        # The link text sometimes includes a sub-brand before the license type.
        # Extract the license type portion and note the sub-brand in the company.
        lt = rec["license_type"]
        subbrand_match = re.match(
            r"^(.+?)\s+(AI (?:License|Partnership|Licensing Partnership|Development|Development Deal).*)",
            lt,
        )
        if subbrand_match:
            subbrand = subbrand_match.group(1)
            actual_license = subbrand_match.group(2)
            # Only apply if the sub-brand doesn't look like a normal license modifier
            known_prefixes = {"Copilot Daily", "Generative", "TDM", "Annual Copyright",
                              "News Corp Australia Copyright", "Harper Collins",
                              "Politico", "Multi-year", "Global Copyright"}
            if not any(subbrand.startswith(k) for k in known_prefixes):
                rec["license_type"] = actual_license
                rec["media_company"] = f'{rec["media_company"]} ({subbrand})'

    return records


def write_csv(records: list[dict], output_path: str | Path) -> None:
    """Write records to CSV."""
    fieldnames = [
        "Media Company",
        "Work Type",
        "Content Type",
        "License Type",
        "AI Company",
        "URL",
    ]
    key_map = {
        "Media Company": "media_company",
        "Work Type": "work_type",
        "Content Type": "content_type",
        "License Type": "license_type",
        "AI Company": "ai_company",
        "URL": "url",
    }

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for rec in records:
            writer.writerow({col: rec[key_map[col]] for col in fieldnames})

    print(f"Wrote {len(records)} records to {output_path}")


def main():
    output = sys.argv[1] if len(sys.argv) > 1 else "copyright_licensing.csv"

    print(f"Fetching {SOURCE_URL} ...")
    html = fetch_page()

    print("Parsing licensing data ...")
    records = parse_html(html)

    if not records:
        print("WARNING: No records parsed! The page structure may have changed.")
        print("Check the HTML manually and update the parser.")
        sys.exit(1)

    # Summary
    work_types = {}
    for r in records:
        wt = r["work_type"]
        work_types[wt] = work_types.get(wt, 0) + 1

    print(f"\nParsed {len(records)} total records:")
    for wt, count in sorted(work_types.items()):
        print(f"  {wt}: {count}")

    write_csv(records, output)


if __name__ == "__main__":
    main()
