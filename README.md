# AI Copyright Licensing Tracker

Parser and dataset tracking AI licensing deals between copyright owners and AI companies, sourced from the [Copyright Alliance](https://copyrightalliance.org/artificial-intelligence-copyright/licensing/copyright-owners/).

## Dataset

`copyright_licensing.csv` contains structured records with the following fields:

| Field | Description |
|-------|-------------|
| Media Company | The copyright holder / media organization |
| Work Type | Category: Literary Works, Music & Audio, Audiovisual & Image |
| Content Type | Content category: Text, Music/Audio, Visual/Video |
| License Type | Type of agreement (AI License, TDM License, AI Partnership, etc.) |
| AI Company | The AI company or licensee |
| URL | Source URL for the licensing announcement |

## Usage

```bash
pip install requests beautifulsoup4

# Fetch latest data and generate CSV
python parse_copyright_licensing.py

# Custom output path
python parse_copyright_licensing.py output.csv
```

## Files

- `parse_copyright_licensing.py` — Reusable parser that fetches and converts the Copyright Alliance page to CSV
- `copyright_licensing.csv` — Latest parsed dataset
- `original.csv` — Manually curated reference dataset with granular content types
- `NOTES.md` — Comparison notes between parser output and original dataset
