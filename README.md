# Wild Rift Skin Version

[简体中文](README.zh-CN.md)

A static archive for browsing League of Legends: Wild Rift skins by international release patch.

The Wild Rift mirror of [League Skin Version](https://github.com/syy674998887/league-skin-version), with the same core browsing interface and a separate Wild Rift data pipeline.

[GitHub repository](https://github.com/syy674998887/wild-rift-skin-version)

This is an unofficial, free, non-commercial community project. It is not endorsed or sponsored by Riot Games.

## Features

- Browse skins by patch, with separate Upcoming, patch-unverified, and region-unconfirmed groups. The regional group appears first and is collapsed by default.
- Skin details show the individual skin release date; PATCH headings show only the patch release date. Missing dates are omitted. A known future skin date is labeled Expected release.
- Search English and Chinese names, and filter by champion, skinline, CN grade, Legacy status, chroma availability, and patch evidence.
- Switch between Original, Wiki, and Loading images where available. The viewer adjusts to the loaded image's actual dimensions and includes related champion and skinline lists.
- Open automatically matched SkinSpotlights videos directly from the Video button.
- Use responsive filters, light and dark themes, keyboard navigation, and reduced-motion support. Filter and search state can be shared through the URL.
- Failed grade and Legacy icons fall back to text. Failed chroma images retain the browser's broken-image indicator and alternative text; names and color swatches remain visible.

Standard grade labels are hidden on cards and in details, while the data and filter remain available. Upcoming uses plain text in details; inferred and unresolved states use short tags. Skin identifiers and detailed evidence remain in the data, but identifiers are neither displayed in details nor searched.

## Data sources

The skin update pipeline uses three source groups:

| Source | Used for |
| --- | --- |
| [League Wiki's Wild Rift module](https://wiki.leagueoflegends.com/en-us/Module:SkinDataWR/data), WR patch pages, and Wild Rift files | Skin identities and catalog, release dates, patch records, skinlines, Legacy status, chromas, and artwork |
| Official CN [champion catalog](https://game.gtimg.cn/images/lgamem/act/lrlib/js/heroList/hero_list.js) and [skin catalog](https://game.gtimg.cn/images/lgamem/act/lrlib/js/skins/skins.js) | Chinese names, explicitly labeled CN grades, and supplementary images |
| International [champion pages](https://wildrift.leagueoflegends.com/en-us/champions/) and [patch announcements](https://wildrift.leagueoflegends.com/en-us/news/game-updates/) | Matched official artwork, new-skin records, and explicit release dates |

Wiki is the primary identity catalog. Official names are joined only when normalized names match; CN entries are joined through champion and poster identifiers. Unmatched names or grades remain English or unknown instead of receiving per-skin overrides. Source aliases are labels collected automatically from the official site.

Grades use the CN classification, since the current Wiki and international champion catalogs do not provide a complete alternative. Skinline and chroma-color translations and icon mappings are display resources; they do not determine patch versions or dates.

There are no manually maintained per-skin patch, date, name-alias, or video-link overrides. SkinSpotlights supplies independent viewing links, not skin identities or release evidence.

| Repository file | Contents |
| --- | --- |
| [data/skins.json](data/skins.json) | Generated skin snapshot, groups, metadata, source links, and diagnostics |
| [data/verification_report.json](data/verification_report.json) | Generated unresolved, inferred, and regional records with their evidence |
| [data/skin_spotlights.json](data/skin_spotlights.json) | Automatically collected video titles and IDs |
| [data/translations.json](data/translations.json) | Display translations for skinlines |

## Dates and patch assignment

Direct new-skin records from Wiki patch pages and official announcements take priority. Returning skins, chromas, and rework mentions are excluded from first-release evidence. Without a direct record, an eligible release date may be placed on an unambiguous patch timeline and labeled Inferred. Missing or conflicting evidence remains Patch unverified. Date-based inference can inherit upstream date errors and does not constitute official confirmation.

Explicit dates in supported official lists, tables, ranked rewards, events, and passes are parsed automatically. Announcement-only dates do not assign the announcement's patch as the skin's release patch. The updater retains source dates and conflicts for inspection rather than adding per-skin corrections.

A Wiki patch date more than seven days away from the official announcement date is omitted and recorded as a discrepancy. This is the project's consistency rule, not independent confirmation of the actual patch launch date.

Upcoming and explicitly China-exclusive records remain separate from the main archive totals. China-exclusive catalog dates are not shown as international release dates. Upcoming records may change or be withdrawn upstream; other existing catalog identities are protected against unexplained removal. Version counts include only numbered patch groups.

## Run locally

Requires Python 3.10 or newer and [uv](https://docs.astral.sh/uv/). Runtime code uses only the Python standard library.

From the repository root:

~~~console
uv sync
uv run site-build
uv run python -B -m http.server 8001 --bind 127.0.0.1 --directory dist
~~~

Open <http://127.0.0.1:8001>. The build reads saved skin and video data and writes the static site to the ignored `dist/` directory. Building does not contact upstream services; externally hosted images still require a connection.

## Update data

Refresh the skin sources and recent videos, run the checks, then rebuild:

~~~console
uv run skin-update
uv run python -B -m wild_rift_skin_version.spotlights
uv run python -B -m unittest discover -s tests -q
uv run site-build
~~~

The updater fetches Wiki records and files, official champion pages and numbered patch announcements, and the CN catalogs. It validates the complete candidate snapshot before writing and replaces changed files atomically. Wiki requests are spaced out, and rate limits receive bounded retries. Fetch or parse failures leave the saved skin snapshot intact.

To rebuild from previously saved responses without making network requests:

~~~console
uv run skin-update --cached
~~~

This requires a populated local `.cache/`. It reuses recorded fetch times rather than inventing a new online-sync time. Generated skin data and verification reports should not be edited by hand.

## Video links

The Video button opens the corresponding [SkinSpotlights Wild Rift](https://www.youtube.com/@SkinSpotlightsWildRift) video. Matching uses the complete English skin name with punctuation normalization, without fuzzy or manual per-skin matching. Skins without a match have no video button. Videos are not embedded or played automatically.

Routine updates merge the public channel feed into the saved catalog without an API key. The feed covers only recent uploads, so it cannot guarantee complete coverage or detect old videos becoming private or deleted. A long interruption may require another full import.

A full channel listing exported by `yt-dlp --flat-playlist -J` can be imported with:

~~~console
uv run python -B -m wild_rift_skin_version.spotlights --import-catalog PATH
uv run site-build
~~~

Replace `PATH` with the exported JSON file. yt-dlp is an optional import tool, not a project runtime dependency.

## Automation and deployment

The [GitHub Actions workflow](.github/workflows/pages.yml) builds and deploys `dist/` to GitHub Pages, including repository subpaths.

| Trigger | Behavior |
| --- | --- |
| Push to `main` | Test, build, and deploy the saved data without refreshing sources |
| Daily at 12:34 in `America/New_York` | Test, build, and deploy; also refresh sources when the last successful data sync is at least 20 hours old |
| Manual dispatch | Optionally refresh sources before testing, building, and deploying |

When refresh is enabled, changed generated JSON files are committed back to `main`. The SkinSpotlights refresh is a separate step; a failure keeps the saved video catalog and does not block the skin update or deployment.

The deployed Updated timestamp uses the newer of the snapshot time and the successful core data-sync completion time. A local build uses the saved snapshot time unless an actual later completion time is supplied through `WR_DATA_UPDATED_AT`.

To enable deployment in the [Wild Rift repository](https://github.com/syy674998887/wild-rift-skin-version), select **GitHub Actions** under **Settings → Pages**, ensure the repository permits the workflow's write permission, and run the workflow. The deployment job reports the Pages URL after a successful run.

## Development

Run the existing tests:

~~~console
uv run python -B -m unittest discover -s tests -q
~~~

The Python tests do not cover browser interactions. After frontend changes, check narrow-screen layout, filter and URL state restoration, patch navigation, image switching, keyboard dismissal and focus restoration, and failed-image rendering.

The frontend is plain HTML, CSS, and JavaScript in `site/`. Python modules live in `src/wild_rift_skin_version/`; `skin_update.py` and `build_site.py` are repository-local entry points. Generated site files, response caches, and local virtual environments are ignored by Git.

## License

Original code and documentation are licensed under the [MIT License](LICENSE). The interface is adapted from League Skin Version by the same author. Third-party game data, artwork, videos, names, and trademarks are not relicensed; see [Third-Party Notices](THIRD_PARTY_NOTICES.md).
