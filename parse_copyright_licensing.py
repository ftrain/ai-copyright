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

# Maps section heading keywords to work_type and default content_type
SECTION_MAP = {
    "literary": ("Literary", "News"),
    "music": ("Music & Audio", "Music"),
    "audiovisual": ("Image", "Stock Image"),
}

# Content type overrides by company name. Companies not listed here get the
# section default (News for Literary, Music for Music & Audio, Stock Image
# for Image). When a company has multiple content types depending on the
# license, the value is a dict mapping license_type substrings to content types.
CONTENT_TYPE_MAP = {
    # Literary — Academic
    "Adam Mathew (AM) Digital": "Academic",
    "American Association for the Advancement of Science": "Academic",
    "Cambridge University Press": "Academic",
    "Informa": "Academic",
    "Johns Hopkins University Press": "Academic",
    "JSTOR": "Academic",
    "Oxford University Press": "Academic",
    "Taylor & Francis": "Academic",
    "World History Encyclopedia": "Academic",
    # Literary — STM (Science, Technology, Medicine)
    "CCC (Copyright Clearance Center)": "STM",
    "Elsevier": "STM",
    "Healthline": "STM",
    "IOPScience": "STM",
    "Journal of the American Medical Association (JAMA)": "STM",
    "Sage Journals": "STM",
    "Springer Nature": "STM",
    "The Royal Society": "STM",
    "Wiley Online Library": "STM",
    # Literary — Social
    "Mumsnet": "Social",
    "Reddit": "Social",
    "WordPress.com": "Social",
    # Literary — Travel
    "Atlas Obscura": "Travel",
    "Frommer\u2019s": "Travel",
    "Map Happy": "Travel",
    # Literary — Marketing
    "Raptive": "Marketing",
    # Literary — special case: News Corp has Book for Harper Collins entry
    "News Corp": {"Harper Collins": "Book", "_default": "News"},
    # Image — Audiovisual
    "Lionsgate": "Audiovisual",
    # Image — Audiovisual Characters
    "Disney": "Audiovisual Characters",
    # Music & Audio — Sound Effects
    "Pro Sound Effects": "Sound Effects",
    "Vadi Sound": "Sound Effects",
    # Music & Audio — Spoken Word Audio
    "Bertelsmann": "Spoken Word Audio",
}

# Company name corrections: source HTML name -> desired output name
COMPANY_NAME_FIXES = {
    "Svenska Tons\u00e4ttares Internationella Musikbyr\u00e5 (STIM)": "STIM",
    "Industry Drive": "Industry Dive",
}

# License type rewrites to match original conventions.
# Maps (substring_in_link_text) -> replacement license_type.
# The sub-brand prefix is dropped from the license type.
LICENSE_TYPE_FIXES = {
    "Sony Music Publishing AI Partnership": "Sony Music AI Partnership",
    "Universal Music Publishing Group AI Partnership": "AI Partnership",
    "Warner Chappell Music AI Partnership": "Warner Chappell Music AI Partnership",
    "Multi-year License Agreement": "Multi-Year License Agreement",
}

# AI Company name normalizations
AI_COMPANY_FIXES = {
    "BandLab": "Bandlab",
}


def get_content_type(company: str, license_type: str, section_default: str) -> str:
    """Determine content type for a record."""
    mapping = CONTENT_TYPE_MAP.get(company)
    if mapping is None:
        return section_default
    if isinstance(mapping, str):
        return mapping
    # Dict mapping: check license_type substrings
    for key, ct in mapping.items():
        if key != "_default" and key in license_type:
            return ct
    return mapping.get("_default", section_default)


def parse_license_entry(li_element: Tag) -> dict | None:
    """Parse a single <li> bullet into license_type, ai_company, url."""
    link = li_element.find("a")
    url = link.get("href", "").strip() if link else ""

    text = li_element.get_text(strip=True)
    if not text:
        return None

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
            ai_company = paren_match2.group(1).strip()
        else:
            ai_company = ""

    license_type = license_type.strip(" \u2013-\u2014:")

    return {
        "license_type": license_type,
        "ai_company": ai_company,
        "url": url,
    }


def fix_company_name(name: str) -> str:
    """Apply company name corrections."""
    # Handle GEDI: the <strong> text may be truncated by the parser to just
    # the part before the parenthetical. Check for partial matches too.
    for src, dst in COMPANY_NAME_FIXES.items():
        if name == src or name.startswith(src):
            return dst
    return name


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

    content = soup.find("div", class_="entry-content") or soup.find(
        "article"
    ) or soup

    records = []
    current_work_type = "Literary"
    current_default_ct = "News"
    current_company = None

    for element in content.descendants:
        if not isinstance(element, Tag):
            continue

        # Detect section headings in <h*> tags
        if element.name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            text = element.get_text(strip=True).lower()
            for key, (wt, default_ct) in SECTION_MAP.items():
                if key in text:
                    current_work_type = wt
                    current_default_ct = default_ct
                    break

        # Section headings may also be in <strong>/<b> within <p> tags
        if element.name in ("strong", "b"):
            parent = element.parent
            text = element.get_text(strip=True)
            text_lower = text.lower()

            # Check if this is a section heading
            is_section = False
            for key, (wt, default_ct) in SECTION_MAP.items():
                if key in text_lower and "licensing" in text_lower:
                    current_work_type = wt
                    current_default_ct = default_ct
                    is_section = True
                    break

            if is_section:
                continue

            # Company name: bold text in a <p> (not inside a <li>).
            # Use the parent <p>'s full text to handle names split across
            # multiple <strong> tags (e.g. "Gruppo Editoriale S.p.A. (GEDI)").
            if (
                text
                and parent
                and parent.name in ("p", "div", "td", "span")
            ):
                full_name = parent.get_text(strip=True)
                current_company = fix_company_name(full_name)

        # List items contain license entries
        if element.name == "li" and current_company:
            entry = parse_license_entry(element)
            if entry and entry["license_type"]:
                company = current_company
                license_type = entry["license_type"]
                ai_company = entry["ai_company"]

                # Apply license type fixes
                for pattern, replacement in LICENSE_TYPE_FIXES.items():
                    if license_type == pattern:
                        license_type = replacement
                        break

                # Apply AI company fixes
                ai_company = AI_COMPANY_FIXES.get(ai_company, ai_company)

                content_type = get_content_type(
                    company, license_type, current_default_ct
                )

                records.append(
                    {
                        "media_company": company,
                        "work_type": current_work_type,
                        "content_type": content_type,
                        "license_type": license_type,
                        "ai_company": ai_company,
                        "url": entry["url"],
                    }
                )

    # Sort alphabetically by company name (case-insensitive)
    records.sort(key=lambda r: r["media_company"].lower())

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
