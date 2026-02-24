# Data Comparison Notes

Comparison of parser-generated CSV vs manually curated `original.csv`.

## Record Counts

- Original: 227 rows
- Generated: 233 rows (6 more — new entries added to source page)

## Key Differences

### 1. Work Type / Content Type (systematic)

The original uses **granular, hand-curated values**:

- **Work Type**: `Literary`, `Image`, `Music & Audio` — parser uses `Literary Works`, `Audiovisual & Image`, `Music & Audio`
- **Content Type**: Original has 13 specific types (`News`, `Academic`, `STM`, `Stock Image`, `Audiovisual Characters`, `Travel`, `Social`, `Book`, `Marketing`, `Sound Effects`, `Spoken Word Audio`) — parser only has 3 coarse categories (`Text`, `Music/Audio`, `Visual/Video`)

The content type granularity is **not derivable from the HTML** — it was manually assigned in the original.

### 2. AI Company normalization

- Original keeps `Licensees Undisclosed`, `Undisclosed Licensees`, and empty strings as distinct — parser normalizes all to `Undisclosed`
- Original keeps `$21 million confidential AI licensing deal` as the AI Company — parser moves it into the License Type field

### 3. Company name differences

- `GEDI)` in parser output (truncated) vs `Gruppo Editoriale S.p.A. (GEDI)` in original — parsing bug with parentheses in company name
- `Industry Drive` (parser) vs `Industry Dive` (original) — `Industry Drive` is what's on the source page
- `Svenska Tonsättares Internationella Musikbyrå (STIM)` (parser, full name) vs `STIM` (original, abbreviated)
- Sub-brand entries: parser appends `(Warner Chappell Music)` / `(Sony Music Publishing)` / `(Universal Music Publishing Group)` to the parent company name

### 4. Records in generated but not original (6 extra)

These appear to be **new entries added to the source page** since the original was created:

- `All Rights Consulting` / Protoge
- `Copyright Licensing Agency` (2 entries)
- `Merlin` / Udio
- `Rightsify` / vAIsual

### 5. Casing difference

- `Bandlab` (original) vs `BandLab` (parser) — parser matches the source page
