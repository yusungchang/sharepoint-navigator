# SharePoint Navigator

A local browser app that lets a Microsoft 365 admin browse every site's Documents library, see used storage (current files vs. version history), search across sites, rename, copy, move or delete files and folders, and trim old versions. Public repo: github.com/yusungchang/sharepoint-navigator (MIT), product page in `site/` (GitHub Pages). Claude Code maintains it. History and reasoning: docs/HISTORY.md. Owner-only notes (tenant, private files) are in `CLAUDE.local.md`, which git ignores.

## Files
- `sharepoint-navigator.py`: the local service on 127.0.0.1:8765. It handles MSAL device-code sign-in, Graph (`GraphClient`), SharePoint REST (`SharePointRestClient`) and the API routes.
- `sharepoint-navigator.html`: the UI, served by the service, which injects an `X-Local-Token`. Not to be confused with `powershell/SharePoint-Navigator.html` (old edition).
- `build_app.py` + `requirements-build.txt`: PyInstaller build for the current OS, windowless, with the icon: `dist/SharePoint Navigator.app` (macOS, onedir, LSUIElement background app; signed with the Developer ID and notarized when the `APPLE_*` variables are set, else ad hoc; see docs/SIGNING.md) or `dist/SharePoint Navigator.exe` (Windows, onefile). The files to release go to `dist/release/` under fixed names: a signed and notarized `.dmg` on macOS; on Windows a per-user installer from `installer/windows.iss` (Inno Setup 6) and a portable zip. Without a terminal, output goes to `~/.sharepoint-navigator/app.log`, and start-up errors show a system dialog.
- `assets/icon.svg` → `tools/make_icons.py` → `assets/icon.icns`, `assets/icon.ico`, `site/icon.png` (committed; needs Chrome + Pillow to remake). The app page's tab icon is the same SVG inline.
- `tests/test_service.py`: offline tests (see below).
- `site/`: the product page (index.html, style.css, site.js, icon, shots/), English with Korean swapped in by site.js; follows the system's light/dark setting. Deployed by `.github/workflows/pages.yml`. Its public address is https://yusungchang.com/sharepoint-navigator (the owner's forward to GitHub Pages); the app's update panel, Info.plist and README use it.
- `tools/demo.py`: runs the real app against a made-up tenant (the test fakes) for screenshots; `tools/shots.py` takes the page's screenshots with headless Chrome.
- `.github/workflows/build.yml`: on a `v*` tag, runs the tests and builds the macOS (Apple silicon) dmg and the Windows installer and zip, attached to a GitHub release with fixed names the page links to; it also checks the dmg and installs, self-checks and uninstalls the Windows app. The Mac app is signed and notarized from the `APPLE_*` repository secrets (set by `tools/signing/setup-mac.sh`); a tag without them fails. Windows is not signed (owner's decision).
- Start-up (no terminal needed): the server starts first; `/api/status` reports a stage (setup → connecting → code → ready, or error) and the page shows a setup form or the device code until "ready". Routes needing SharePoint answer 409 before that. `connect()` signs in on a thread; a generation counter drops a sign-in replaced by "Change organisation" (`/api/setup-reset`). A second launch while running opens the page if the running copy is the same or newer; an older one (1.2.0+) is stopped with the key in `~/.sharepoint-navigator/running-<port>.json` (0600) and the new copy starts (`take_over`); for one before 1.2.0 it opens the old page and says to click Stop app. Tests and the demo must keep that file out of the real folder (per-port file; tests use a temp `USER_FOLDER`).
- Tenant and client ID: `<tenant>_clientid.txt` beside the app (beside the .app on macOS) wins; else `~/.sharepoint-navigator/settings.json`; else the page's setup screen asks and saves. Never print, copy or commit a client ID; `*_clientid.txt` is git-ignored.

## Architecture
- Graph handles site and library lookups, a folder's *direct* children (200 per page), rename/copy/move, delete (to the recycle bin), and search (`/api/search` → `POST /search/query`, driveItem hits across all sites, read-only; results offer only Show in tree and Open).
- SharePoint REST, using tokens obtained silently from the same MSAL sign-in, handles:
  - The site list: admin API `GetSitePropertiesFromSharePointByFilters`, falling back to Graph search.
  - Folder `StorageMetrics`. A single `/Folders?$expand=StorageMetrics` call returns metrics for all subfolders.
  - Site version trim (Trim old versions dialog): `site/StartDeleteFileVersionsByMode` (mode 0 days, 1 count, 2 automatic), `GetProgressForDeleteFileVersions`, `CancelDeleteFileVersions`. Start/Stop use an `AllSites.FullControl` token. `/api/trim-queue` reads every site's trim and `GetProgressForSetVersionPolicyForDocLibs` status for the row badges.
- The bar shows TotalSize split into TotalFileStreamSize (current content) and the remainder (versions + metadata, an estimate). Graph folder `size` equals TotalFileStreamSize.

## Rules the user set
- Top level is "site / Documents"; no extra site wrapper row.
- Size bars use one global scale: the largest library is 100% at every depth, so bars are never relative to siblings. Only the name column is indented, so the bar, size, files and action columns line up at every depth.
- Wording in the UI is plain language: say "libraries" and "app", not Graph, scan, report, PnP or PowerShell.
- The UI is bilingual (EN | 한국어) and has a theme switch (Light | Dark | System), with both choices kept in localStorage. Every new UI string goes into both `I18N.en` and `I18N.ko` in sharepoint-navigator.html and is shown with `t('key')`, or with `data-i18n` for fixed markup. Dark colours live in two copies of the same rules: the system-dark media query and `:root[data-theme="dark"]`. Change both together.
- Opening a folder fetches only its direct children. Never scan recursively for the UI (`Inventory.stats` is only for the rename and delete snapshots).
- Sizes load for visible rows and never block opening a folder. No Expand all; nothing starts expanded.
- A 403 or other error on one site is skipped, and the scan continues.
- Bind to 127.0.0.1 only; no shell or arbitrary command routes.
- The only contact outside Microsoft is Check for updates (round arrow in the header, after PDF-Epsilon's): the page asks `api.github.com/repos/…/releases/latest` only when clicked, trusts only a strict `x.y.z` tag, and links to the fixed product-page download section. Never check on its own or send anything else.
- Copy and Move stay within the item's own library; no transfers between sites (owner's rule). The picker has no library selector.
- Delete must keep asking a lot (owner's rule): live preview, tick-boxes, the exact name typed, a folder's file count typed, a countdown (`DELETE_WAIT_SECONDS`, enforced by the service too) and a last browser confirm; the service re-checks everything and sends If-Match. Delete is only in the tree's row menu, never in search results, and never for a library root.
- Search results offer only Show in tree and Open; everything else is done from the tree row (owner's choice).
- The repo is public: no tenant, customer, staff or site names in code, docs, tests, commits or screenshots. Use contoso / made-up names (screenshots come from tools/demo.py).
- Never run a real rename, copy, move, delete or version trim in the tenant unless the user asks for it directly.

## Versioning ("vibe" scheme)
- `x.y.z`, set only in `__version__` in sharepoint-navigator.py; the page, terminal, `--version` and `--self-check` show it.
- Each working session raises z by one; a meaningful change (new feature) raises y instead and resets z to 0; x became 1 when the owner set 1.0.0 (2026-11-03); it changes again only when the owner says so.
- At the end of every session: run the offline tests (`.venv/bin/python -m unittest tests/test_service.py`, see below) and fix or report any failure, bump the version, add a row to the table in `docs/HISTORY.md` plus a section on what changed and why (including the test result), and update the README if behaviour changed. Commit; tag `vX.Y.Z` and push the tag to publish a release when the owner wants one. The owner asked for the tests every session, even when only the page changed.

## Running and checking
- Run: double-click `sharepoint-navigator.command` (macOS launcher: sets up `.venv`, starts the app, and opens the browser itself; Python gets `BROWSER=true` so it doesn't open a second tab). Manual alternative: `source .venv/bin/activate && python sharepoint-navigator.py`. The venv is Python 3.13, built with uv.
- After backend edits the user must restart the service and refresh the browser.
- Auto-stop: each open tab holds `GET /api/session-events?token=…` (an event stream). When the last one closes and no tab reconnects within 15 s, the service shuts down. `SHAREPOINT_NAVIGATOR_AUTO_STOP=0` turns this off, and `SHAREPOINT_NAVIGATOR_AUTO_STOP_GRACE` shortens the wait for tests.
- Quick check without sign-in: `python sharepoint-navigator.py --self-check`.
- Live read-only check: run on a spare port without opening a browser, e.g. `BROWSER=true SHAREPOINT_NAVIGATOR_PORT=8799 .venv/bin/python -u sharepoint-navigator.py <tenant>` (the tenant is in CLAUDE.local.md). Read the token from `GET /`, then call `/api/status`, `/api/scan`, `/api/folder-children` and `/api/storage-metric`, and stop via `/api/stop`. The app writes no files during a scan.
- JS syntax: extract the inline `<script>` and run `node --check`.
- Offline tests: `.venv/bin/python -m unittest tests/test_service.py` (a few seconds, no sign-in, nothing sent to the tenant). They run the real service with Graph and SharePoint REST faked in memory and cover the safety rules of rename, copy, move, delete and trim plus access checks. Run them after every service change; when the service starts a new kind of Graph or REST call, extend the fakes in the same file.
- Git repo at ~/Projects/sharepoint-navigator (not in iCloud). Commit in small steps; never commit private files.
