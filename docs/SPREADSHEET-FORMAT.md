# Spreadsheet import format

`import-sheets` reads ratings and metadata you already keep in a
spreadsheet and fills the gaps in your catalog with them. This is the
format it accepts.

```
python -m humble_catalog import-sheets [workbook.xlsx ...]
```

It never writes to the workbook, and it never overwrites a catalog value
that is already set — so re-running it is safe and repeated runs are
mostly no-ops.

## Which files

Pass any number of `.xlsx` paths. With no arguments it looks for two
files and silently skips either that is absent:

```
Reference spreadsheets/Audiobooks (loose collection).xlsx
Reference spreadsheets/E-books (loose collection).xlsx
```

**The file name decides what a workbook can match.** If the name
contains `audiobook` (any case) its rows are matched against audiobook
items only; every other file is matched against ebooks and comics.
There is no column for this and no way to override it:

| File name | Matches |
|---|---|
| `Audiobooks 2026.xlsx` | audiobooks |
| `my audiobook list.xlsx` | audiobooks |
| `Spoken Word.xlsx` | **ebooks and comics** — probably not what you meant |
| `Comics.xlsx` | ebooks and comics |

A workbook of audiobooks whose name omits the word will report every row
as unmatched, because it is being compared against the wrong half of the
catalog.

## Which sheets

Every worksheet is read. **Row 1 is the header row**, and a sheet is
used only if one of its headers is recognised as the title column;
sheets without one are skipped and listed at the end of the run. Sheet
names are free-form — they appear in reports and are not otherwise
interpreted, so you can organise by genre, source, or anything else.

Data starts at row 2. Rows with an empty title are skipped silently.

## Columns

Header matching ignores case, surrounding whitespace, and one trailing
colon, so `Name`, `name:`, and `  Name :` are the same column.

| Header | Fills | Notes |
|---|---|---|
| `Name` | the title used for matching | **required** — no `Name`, no import |
| `Rating` | your rating (the "Mine" column) | number; see below |
| `Genre` *or* `Setting` | genre | either spelling |
| `Series` | series | free text |
| `Number in the series` | position in the series | must be a number |
| `Author` | author | singular; see multi-value below |
| `Narrator` *or* `Narator` | narrator | the misspelling is accepted deliberately |
| `Bundle`, `Humble`, `Publisher` | *nothing* | recognised and ignored: your Humble orders are authoritative for these |

**Any other column is ignored, and the run now says so** — a header the
importer does not know is listed under "Unrecognized columns" with the
accepted spellings beside it. That report is the thing to read first
when an import does less than you expected, because the common failure
is a near-miss like `Ratings` or `Authors`.

## Cell values

- **Empty** means empty, and so does `N/A` in any case — the importer
  treats it as "no value here" rather than importing the text.
- **`Rating`** is applied only when it is a number greater than zero, so
  `0` reads as "unrated" rather than a rating of nought. A fractional
  value is truncated (`4.5` → `4`). The viewer offers 1–5; nothing
  enforces that range on import.
- **`Number in the series`** must parse as a number. Anything else is
  skipped without failing the row.
- **Multi-value cells are not split.** `Author` of
  `Alex Penner, Sam Reader` becomes a single author literally named
  "Alex Penner, Sam Reader". One name per cell; use the viewer to add
  more.
- **Genre is case-normalised** against genres already in your catalog:
  typing `science fiction` where the catalog has `Science Fiction`
  snaps to the existing spelling instead of creating a second tag.

## How rows are matched

A row's `Name` is compared with catalog titles after lowercasing,
replacing punctuation with spaces, and collapsing whitespace — so
`The Hollow Crypt` matches `the hollow crypt` and
`The Hollow Crypt!`. Purely numeric titles work too.

| Result | Meaning | What happens |
|---|---|---|
| exactly one match | good | the row is imported |
| several matches | ambiguous | **nothing is written**; the row is listed |
| no match | unmatched | the row is listed, with the closest catalog title as a hint |

Suggestions are printed only. Nothing is ever applied on a guess, so an
unmatched row is a prompt to fix a title by hand, not a silent partial
import.

## What gets written

Strictly gap-filling, field by field:

- A rating is written only if that item has no rating yet.
- Genre, author, narrator, series and series number are each written
  only if that field is currently empty.
- Nothing is ever replaced — not enrichment results, not your own edits.

Filled rows get the "edited" badge in the viewer and a revert point, so
an import can be undone per row with `↩`. A matched row with nothing
left to fill is counted as "already complete".

## A minimal example

Sheet `Fiction` in `My Audiobooks.xlsx`:

| Name | Author | Narrator | Series | Number in the series | Rating |
|---|---|---|---|---|---|
| Axebearer | Alex Penner | Sam Reader | The Elder Realm | 1 | 4 |
| Circle of Storms | | Sam Reader | The Elder Realm | 2 | |
| How Sound Behaves | | | N/A | N/A | 5 |

Against a catalog holding all three as audiobooks, that reports
`3 rows read, 3 matched, 2 ratings set, 7 fields filled`: row 1 sets a
rating and fills four fields, row 2 fills three and leaves the rating
alone, and row 3 sets a rating while its `N/A` cells are ignored.
Ratings and fields are counted separately in that summary, which is
worth knowing when checking whether a run did what you expected.

## When an import does nothing

| Symptom | Likely cause |
|---|---|
| "Skipped sheets (no Name: column)" | the title column is called something else — check the "Unrecognized columns" list for what it saw |
| Rows read, but 0 ratings set | `Rating` misspelled, all values `0`, or those items are already rated |
| Every row unmatched | audiobook workbook whose file name lacks `audiobook`, so it is being matched against ebooks |
| One row unmatched, close title shown | the catalog spells the title differently; fix it in the viewer, then re-run |
| Row ambiguous | two catalog items share the title; merge or rename them first |
| Author imported as one long name | multi-value cell — see above |
| Matched, but "already complete" | the fields are filled already; the importer never overwrites |
