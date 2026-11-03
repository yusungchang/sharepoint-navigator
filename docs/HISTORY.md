# History

## Versions

| Version | Date | Change |
|---|---|---|
| 1.0.0 | 2026-11-03 | Version 1.0, set by the owner. The same app as 0.8.0 (row menu, file dates, Delete with many confirmations), released as the first 1.x. 72 offline tests. |
| 0.8.0 | 2026-11-03 | Delete for files and folders (to the site's recycle bin), behind many confirmations: live preview, tick-boxes, typed name and file count, a countdown and a last question; the service re-checks it all. 72 offline tests. |
| 0.7.0 | 2026-11-03 | Row actions move into one "⋯" menu per row (also on right-click), freeing the wide actions column. Files show their last-modified date under the size. 57 offline tests. |
| 0.6.1 | 2026-11-02 | Fix: Download did nothing. Graph left out the download address because the request used `$select`; it now uses `select`. Failed downloads are logged with their reason. 57 offline tests. |
| 0.6.0 | 2026-11-02 | No terminal window: setup and Microsoft sign-in happen in the browser page. Windowless apps with the app icon: `SharePoint Navigator.app` (macOS, background app) and `SharePoint Navigator.exe` (Windows). Change organisation from the page. Download button for files in the tree and in search results. 57 offline tests. |
| 0.5.0 | 2026-11-02 | Public on GitHub (MIT) with a product page. First run asks for the tenant and client ID and saves them in the user's folder (`--setup` to change); a client ID file beside the app still wins. GitHub builds macOS and Windows apps on each release. Demo mode with a made-up company for screenshots. 52 offline tests. |
| 0.4.0 | 2026-11-02 | New: search across all libraries. Enter in the search box searches every site through SharePoint's search index, with site, type, size and date filters and sorting. A Search button sits beside the box. Each result offers Show in tree (folder-with-magnifier icon; opens the folders down to it and highlights it) and Open. The box no longer filters only the loaded rows. 46 offline tests (14 new). |
| 0.3.2 | 2026-11-01 | Bar parts renamed to "Current files" and "Version history"; rows show both numbers with a coloured square and no words, since the legend at the top names the colours. Trim icon is now a trash can with a clock. Site lines drop the repeated tenant address, which now sits once beside the "Library / folder" header. Sort by clicking column headers; the colour legend sits in the bar column's header. Bars and folder/file icons inside an opened library are visible again in light theme. Rename's name check is one shared method; Move explains a name clash in plain words. Offline tests for the service (32 checks, faked Graph and SharePoint). Files renamed to kebab-case: `sharepoint-navigator.py`, `.command`, `.html`. PowerShell scripts tidied (names and help text only). |
| 0.3.1 | 2026-11-01 | Trim queue: sites with a trim waiting, running or failed (or version limits being applied) get a badge; a Trims pane lists those and trims that ended in the last 7 days. Simpler page; quieter terminal. |
| 0.3.0 | 2026-11-01 | New: Trim old versions for a site (Automatic, older than N days, or keep N versions), with the site's last trim, a typed confirmation and Stop. |
| 0.2.11 | 2026-11-01 | Fix: Word, Excel and PowerPoint files showed as "Doc.aspx" with a wrong path; they now show their real names and paths. |
| 0.2.10 | 2026-11-01 | Copy and Move stay in the item's own library; the picker drops its library dropdown and shows a breadcrumb, an Up icon and folder icons. |
| 0.2.9 | 2026-11-01 | Open, Rename, Copy and Move are icons with quick tooltips (English and Korean); narrower actions column. |
| 0.2.8 | 2026-11-01 | Library rows highlight as full-width square bands, matching the shape of an opened library. |
| 0.2.7 | 2026-11-01 | Closing slides the pane up with an ease-in curve (200 ms); a soft glow above the tray's lit bottom edge. |
| 0.2.6 | 2026-11-01 | Opening a library or folder slides its pane down with an ease-out curve (260 ms). |
| 0.2.5 | 2026-11-01 | An opened library's row stays pinned at the top while its contents scroll under it; the tray's bottom edge is a solid 1px lit line. |
| 0.2.4 | 2026-11-01 | Tray edge lines removed; only the soft shadow (top) and highlight (bottom) remain. |
| 0.2.3 | 2026-11-01 | Tray edges simplified: one line each, a subtle shadow under the top line and a subtle highlight over the bottom line. |
| 0.2.2 | 2026-11-01 | The opened library's contents sit in a full-width recessed tray (two-tone lines, darker background, soft inner shadow) instead of the 0.2.1 card. |
| 0.2.1 | 2026-11-01 | An opened library is shown as a card (tinted background, outline, soft shadow) so its contents stand apart from the other libraries. |
| 0.2.0 | 2026-10-31 – 11-01 | No PowerShell: site list and sizes straight from SharePoint. Redesigned page with one size scale, plain wording, Light/Dark/System and English/한국어. Auto-stop when the tab closes, a macOS launcher, Python 3.13, single-file builds. |
| 0.1.0 | 2026-10-27 – 10-30 | First version: PowerShell edition, then the Python + Microsoft Graph edition with a library/folder tree, sizes from PnP Storage Metrics, and rename, copy and move. |

Versions follow the owner's "vibe" scheme: `x.y.z`. Each working session raises z; a meaningful change
(a new feature or product) raises y and resets z to 0. x stays 0 until the owner says 1.0. The version is
set in one place, `__version__` in `sharepoint-navigator.py`, and shown in the page header, the
terminal, `--version` and `--self-check`.

## 1.0.0, 3 November 2026

**Version 1.0.** The owner set the version to 1.0.0 and asked for a release. Nothing in the app changed from
0.8.0; this release is the first to carry 0.7.0 (row menu, file dates) and 0.8.0 (Delete) to the downloads.
From here the vibe scheme goes on from 1.0.0: each session raises z, a new feature raises y.
Offline tests 72/72.

**Product page, after the release: where the tools are.** People missed the faint "⋯" button at the end of each
row, so the page has a new section, "Every tool is in the ⋯ menu" (Tools in the top bar). It says to click ⋯ or
right-click a row, lists what the menu offers on files, folders, libraries and search results, and gives the
keyboard keys. Beside it is a cropped screenshot of a file row's open menu, in English and Korean, light and
dark. `tools/shots.py` makes these four `menu*.png` shots by driving Chrome over its DevTools pipe (standard
library only): Chrome's one-shot `--screenshot` leaves an open row menu out of the picture. The other shots were
retaken too, so they show 1.0.0. The app itself didn't change. Offline tests 72/72.

## 0.8.0, 3 November 2026

**Delete.** Files and folders can now be deleted from the tree's row menu ("Delete…", in red, at the bottom).
The owner asked for it to ask for permission "excessively", so it does, on both sides:

- The page opens a dialog that first fetches a live preview (`/api/delete-inspect`): name, path, site, size and,
  for a folder, the number of files in all its subfolders (counted again, not taken from the tree). It says if
  the item changed since the tree showed it.
- Three tick-boxes must be ticked (four for a folder: "everything inside goes too: N files").
- The exact name must be typed (capitals count), and for a folder the number of files inside.
- Delete stays locked for a countdown (5 s). Then a last browser question repeats what goes and where.
- The service (`/api/delete`) refuses unless the single-use preview is under 3 minutes old and at least 5 s old
  (so the countdown can't be skipped), the acknowledgement is present, the typed name and file count match, and
  a fresh snapshot (the folder walked again) is identical. Graph DELETE then goes with If-Match. Any refusal uses
  the preview up, so the person has to start again with Check again.
- Never for a library's root, never from search results (owner's rule: search offers only Show in tree and
  Open), and only for sites in the loaded list. Rename previews and delete previews are kept apart, so one
  can't be used as the other.

Graph's DELETE moves the item to the site's recycle bin, so it can be restored from there (normally for up
to 93 days). The dialog says so. Typed names are compared after Unicode NFC normalising, because names
uploaded from a Mac can be stored decomposed (common for Korean) and couldn't be typed back otherwise.
No new permission: `Sites.ReadWrite.All` already covers delete.

Checked in the demo tenant with headless Chrome (folder and file, English light and Korean dark, phone width):
countdown, a wrong count or wrong capitals keep Delete locked, declining the last question sends nothing, a
refused delete forces Check again, and a delete removes the row and refreshes the folder. The demo itself stays
read-only; the delete check used a scratch copy that allowed it in memory. Not run against the real tenant.
Offline tests 72/72 (15 new delete tests; the service's wait is shortened for them with
`SHAREPOINT_NAVIGATOR_DELETE_WAIT`).

## 0.7.0, 3 November 2026

**Row menu instead of a row of icons.** Each row used to show up to five icons (Open, Download, Rename, Copy,
Move; Trim on libraries; Show in tree in search), which took a 164px column on every row. Now each row has one
faint "⋯" button that opens a small menu with the same actions, with names instead of icon-only tooltips.
Right-clicking a row opens the same menu at the pointer. The menu closes on Esc, a click elsewhere, scrolling or
resizing; the arrow keys move through it. The actions column is now 32px in both the tree and search results.
On narrow windows the button sits at the end of the name line instead of taking a line of its own.

**File dates.** A file's last-modified date sits under its size in a smaller grey line; hovering shows the time.
Folders don't show one: a SharePoint folder's date doesn't change when files inside it change, so it misleads.

Checked in the demo tenant with headless Chrome (menus open in light and dark, English and Korean, with the
right items for a file, a library and a search result). Offline tests 57/57. Screenshots on the product page
were retaken.

## 0.6.1, 2 November 2026

**Fix: Download did nothing.** Reported right after the 0.6.0 release (macOS, Chrome): the button's spinner
appeared and vanished, and nothing downloaded. The app log showed `HTTP 400: POST /api/download-link` without a
reason. Asked directly, the running app said "SharePoint didn't return a download address for this file".
A read-only probe against the real tenant showed why: with `?$select=id,name,@microsoft.graph.downloadUrl` Graph
returns the item **without** the download address; with `?select=…` (no `$`), or with no select at all, it is
there. The offline fake didn't model that, so the tests passed.
- *Fix:* the request uses `select=`. A test now checks that the query starts with `select=`, so it can't
  quietly go back.
- *Logging:* a failed download link is printed with its reason ("Download link failed: …"), so app.log says why.
- *Checked live (read-only):* the fixed version on a spare port got a link for a 26 MB PDF; a HEAD request
  showed `200`, `application/pdf` and `Content-Disposition: attachment`, so the browser saves it without leaving
  the page. Offline tests 57/57.

## 0.6.0, 2 November 2026

**No terminal window.** The owner's main complaint after 0.5.0: the console had to stay open the whole time.
It was needed for three things, and all three moved into the browser page:
- *Setup:* a **Connect to your Microsoft 365** screen asks for the tenant name and client ID (with a link to
  the admin guide) and saves them, instead of terminal questions. A client ID file beside the app still skips it.
- *Sign-in:* the page shows the device code with **Copy** and **Open sign-in page**, and a spinner until
  Microsoft confirms. Before, the code was printed in the terminal.
- *Staying alive and stopping:* already handled by the tab (auto-stop) and **Stop app**.

How it works: the server now starts first and signs in on a background thread (`connect()`); `/api/status`
reports the stage (setup, connecting, code, ready, error) and every SharePoint route answers 409 until ready.
A generation counter makes a waiting sign-in stop when the person chooses **Change organisation** (new, at the
top of the page) and ignores it if it finishes anyway. `AuthSession` no longer blocks on a prompt; a sign-in that
expires mid-session says to reopen the app. Opening the app again while it runs just reopens the page (it checks
its own Server header on the port). Without a terminal, messages go to `~/.sharepoint-navigator/app.log`
(started over above 1 MB), and a start-up error shows a system dialog (Windows message box, macOS alert).

**Apps with an icon.** The build is now windowless: `SharePoint Navigator.exe` on Windows (one file, icon in
Explorer and the taskbar) and `SharePoint Navigator.app` on macOS (a normal folder bundle, since PyInstaller
discourages one-file .app; a background app with no Dock window, because the browser tab is its window; the
bundle is re-signed ad hoc after its Info.plist is edited, which Apple silicon requires). The icon is the
product page's SVG, turned into `assets/icon.icns` (with Apple's margin) and `assets/icon.ico` by
`tools/make_icons.py`; the app's tab icon is the same design. On macOS a client ID file is looked for next to the
.app, not inside it. The release zips keep their names; inside are the new apps (`ditto` zips the .app).

**Download.** The owner asked for a download button in the tree and in search results. Files get a Download
icon (tree: after Open; search: between Show in tree and Open). It asks the app for Graph's
`@microsoft.graph.downloadUrl`, a pre-authorised address valid for about an hour, so the browser saves the file
under its own name even when it isn't signed in to SharePoint. Read-only; only a SharePoint https address is ever
handed to the browser. Folders get no button: Graph has no simple folder-as-zip download. The action columns
widened by one icon. New route `/api/download-link`, 3 new tests (file link, folder refused, unknown site refused).

**Pages and docs:** first-launch, install and uninstall steps no longer mention a terminal, and use the new names.
Switching organisation is "Change organisation" instead of `--setup` (which still works from source).

**Checks.** Offline tests 57/57 (new: setup → code → ready with settings saved, a bad client ID refused,
Change organisation stopping a waiting sign-in; settings helpers rewritten). Built the Mac app here: background
app flag, version and icon in the bundle, signature valid, self-check passes, a second launch reopens the page,
output in app.log. The demo has `--setup` and `--signin` modes, used to check both new screens in English/Korean
and light/dark. The Windows app is built by GitHub; it still needs a try on a real PC.

## 0.5.0, 2 November 2026

**Public project.** The owner asked to publish the app like their other project, PDF Epsilon: a public GitHub
repo (github.com/yusungchang/sharepoint-navigator, MIT) and a product page on GitHub Pages, in the same design
(light and dark from the system, English and 한국어).
- *Where it lives:* the working copy moved out of iCloud Drive to `~/Projects/sharepoint-navigator`, because
  iCloud sync can damage a `.git` folder. The iCloud folder stays as an archive of everything up to 0.4.0.
- *Kept private:* the client ID file, the handover notes, the admin change logs and the old PowerShell edition
  stay in the archive. Tenant, customer, staff and site names were replaced in this history and in code comments
  (contoso and made-up names). Owner-only notes go in `CLAUDE.local.md`, which git ignores.

**Tenant and client ID without a file.** Asked whether to keep these in a file or ask, the owner chose both:
- A `<tenant>_clientid.txt` beside the app still wins, so an admin can hand staff a zip that asks nothing.
- Otherwise the app asks once in the terminal (tenant name, a full SharePoint address works too, then the
  client ID with a link to the setup guide) and saves both in `~/.sharepoint-navigator/settings.json`, next to
  the encrypted sign-in cache and readable by the user only. The next launch asks nothing. `--setup` asks again.
- The tenant prompt no longer appears when a client ID file or saved tenant says which one to use.
- The User-Agent sent to Microsoft no longer names a company.

**Builds on GitHub.** `.github/workflows/build.yml`: on a `v*` tag, the offline tests run on macOS and
Windows, then PyInstaller builds each app (with its self-check) and both zips are attached to the release under
fixed names the page links to. Intel Macs aren't built (GitHub's Intel runners are being retired); they can
run from source. `pages.yml` publishes `site/` when it changes.

**Product page** (`site/`): hero, six badges, features, a search showcase, "careful by design", a short admin
setup (the full guide is in the README) and downloads with first-launch steps per system, as on the PDF Epsilon
page. Screenshots come in four versions (English/Korean × light/dark) and follow the visitor's choice.

**Install, update and uninstall** are on the page and in the README: there's no installer (Windows SmartScreen
signing was judged not worth it for now), so they are plain file steps, including the settings folder and, on macOS,
the **msal-extensions** Keychain entry that holds the sign-in key.

**Demo mode** (`tools/demo.py`): the real app against a made-up company (Contoso, nine sites, about 5,000 items,
sizes and version history from a fixed seed), with sign-in and Microsoft replaced in memory and changes refused.
`tools/shots.py` takes the eight screenshots with headless Chrome, so no real tenant data can appear in them.

**Checks.** Offline tests: 52/52 (6 new for settings: first run asks then remembers, a file beside the app is
never asked about, command-line tenant, bad ID asked again, `--setup`, invalid tenant refused). `--self-check`
shows the saved settings. Page script and product page script pass `node --check`; every page text has a Korean
version. The Windows build hasn't been run on a PC yet.

## 0.4.0, 2 November 2026

**Search across all libraries.** The old search box only filtered rows already loaded in the tree, so it
couldn't find anything in a folder nobody had opened (the owner called it "pretty useless"). We compared
three options: Graph `POST /search/query` (Microsoft Search), SharePoint REST `/_api/search/query`, and
Graph `/drives/{id}/root/search`. The last needs one call per library. Graph `/search/query` covers every site in one call, uses the
same sign-in and Sites.Read.All, and supports KQL filters and sorting, so it was chosen. SharePoint
search REST stays the fallback if custom columns or extra refiners are ever needed.
- *Service:* new read-only route `/api/search` → `run_search()`. It builds KQL from the typed text plus
  filters (`search_kql`), always limited to `https://<tenant>.sharepoint.com/` (OneDrive is excluded) or one
  loaded site (`path:"<site>/"`; the trailing slash stops /sites/Alpha matching /sites/AlphaBeta). An empty box
  with no filter is refused, so nobody lists the whole tenant by accident. Unknown filter values are refused.
  50 results per block, up to 1,000 (Graph refuses very deep paging).
- *What a live probe showed (read-only, a real tenant):* `webUrl` in search hits is the plain path (not the
  Doc.aspx viewer link), unencoded, so it is turned into a server path without URL parsing (a `#` in a name
  would otherwise be cut). Folder hits wrongly carry a `file` facet, so the `IsContainer` field decides
  folder vs file. A folder's size in the index is 0, so results show no folder size. Asking for `fields`
  replaces the default set, so name, webUrl, size and date are requested explicitly.
- *Page:* Enter runs the search; results replace the tree (which keeps its state underneath). Filters:
  Where (all sites or one), Type, Size, Modified; Sort: best match, largest, newest, oldest. Each result
  shows name, location ("Site/Documents / folder"), size and date, plus two actions only, as the owner
  asked: **Show in tree** and **Open**. Rename, Copy and Move stay on the tree row the result leads to.
- *Follow-up the same day:* a **Search** button beside the box (same as Enter; with an empty box it just
  focuses the box). The Show in tree icon changed from a crosshair to a folder with a magnifier, the usual
  sign for "show in enclosing folder" (macOS Finder has no icon of its own for it).
- *Show in tree* goes back to the tree and opens the library and each folder on the way, one direct
  listing at a time (no recursive scan, same calls as clicking), loading further 200-item pages until the
  name turns up. It then scrolls to the row and highlights it briefly. It is greyed out when the item
  is in a library the tree doesn't show (e.g. Site Pages) or a site that wasn't loaded.
- *Checks:* offline tests 46/46 pass (14 new: result parsing, subsite vs parent site, "#" in names,
  KQL scope and filters, paging, read-only, refusals). Live read-only check on port 8799: hundreds of
  hits for a Korean word across sites, archives over 1 GB sorted by size, folder + date filter; a hit four folders
  deep was reached by walking the folder listings as Show in tree does. The page script passes
  `node --check`; EN and KO phrase lists have the same keys. The page itself wasn't clicked through in
  a browser this session.

## 0.3.2, 1 November 2026

**Clearer size names.** In 0.3.1 the "Size" line left each row (it moved to the tooltip), so the colours are now
named only by the legend at the top. Row labels no longer need to be short, so the owner asked to go back to
more useful names. Earlier names, for reference: "Current files" / "History / other est." (PowerShell edition),
"Current files" / "Previous versions + metadata" (early 0.2.0), "Size" / "Old versions" (late 0.2.0 to 0.3.1).
- *Now:* **Current files** (blue, TotalFileStreamSize) and **Version history** (orange, the rest of Storage
  used). Korean: 현재 파일 / 버전 기록, the names SharePoint itself uses. "Size" was vague, since Storage used
  is a size too; "metadata" broke the plain-language rule, and the tooltip already mentions the small amount of
  file information in the orange part.
- *Changed in:* the legend, the summary line, the bar and size-cell tooltips, the loading notes and
  **About these numbers**, in both languages.
- *Rows:* under Storage used, two lines: a blue square with Current files and an orange square with Version
  history, numbers only (the 0.3.1 "Size" line is back, without its word). The squares tie each number to
  the legend; screen readers still hear the names.
- *Kept:* "Trim old versions" (button and dialog), because it names the action.

**Trim icon.** Scissors suggested cutting, not permanent deletion. The icon is now a trash can with a clock
inside: "permanently delete old versions". A plain trash can was rejected because, on a library row, it
would read as "delete this library"; a history arrow with an X and an eraser were also tried.

**Shorter site lines.** Every site is in the same tenant, so the line under each library name showed
`contoso.sharepoint.com` again and again. It now shows only the site's path (`/sites/Finance`), or
"Home site" for the tenant's root site; the full address is in its tooltip. The trim dialog still shows the
full address, since it confirms one site before a permanent change.
- The tenant address now sits once beside the **Library / folder** column header (not in capitals), so the
  rows' `/sites/...` paths read as continuing from it. It is also still at the top of the page above the title.
  The bottom of the page was considered and rejected: too far from the rows.

**Sort and legend where file browsers put them.** The owner asked whether the sort menu and the colour
legend, both in the search bar, were placed conventionally. They weren't. Finder's list view, Windows Explorer's
details view, SharePoint / OneDrive and Google Drive in list view, TreeSize and WinDirStat all sort by clicking a
column header, with an arrow showing the direction; a separate Sort menu belongs to tile or grid views, which have no
headers. A colour legend sits next to the chart it explains (macOS Storage puts it right under the bar), not at
the far right of a toolbar, above other columns.
- *Column headers sort:* **Library / folder**, **Storage used** and, new, **Files**. A column starts in its usual
  direction (names A–Z, sizes and file counts largest first); clicking it again reverses. The active header is
  brighter and shows ↓ or ↑; each header's tooltip names the order a click gives ("Sort: Smallest size").
  Largest size is still the default.
- *Legend in the bar column's header:* "■ Current files ■ Version history" replaces "Compared with the largest
  library", which moved to the legend's tooltip ("Bar = storage used · largest library = 100%"). The legend now
  sits over the bars and beside the squares in the Storage used column.
- *Toolbar:* search only, as in SharePoint and Google Drive.
- *Narrow screens (900 px or less):* the header row is hidden there, so the Sort menu (now also with Most / Fewest
  files) and the legend stay in the toolbar. The menu and the headers share one sort setting.
- Strings: `head.bar` removed; `sort.filesDesc`, `sort.filesAsc` and `sort.next` added, in both languages.

**Fix: bars in an opened library, light theme.** The bar track (`--track` #e9eff6) was almost the colour of
the opened library's tray (`--well-bg` #eff3f8), so a folder's bar looked like a lone sliver with no track.
A new token, `--well-track` (#d6dfea in light), colours the track inside the tray only. Dark theme keeps its
track colour (#2d3b49, set in both dark copies).
The folder and file icon tiles had the same problem (#edf4ff and #eef1f5 on the #eff3f8 tray); their light
backgrounds are now #d9e6fb and #dce3eb. Library tiles sit on the white list and are unchanged; dark theme too.

**Small refactor (service).** The owner asked for refactoring candidates without overdoing it. Done:
- *One name check for Rename:* `/api/inspect` and `/api/rename` each had the same 10-line "is the new name
  taken?" check. It is now `Inventory.name_taken(site_url, item_path, new_name)`: found means taken, HTTP 404
  means free, any other error is raised so a rename never goes ahead on a failed check. The old copies raised
  their "already exists" error inside the `try` and relied on its text not containing "HTTP 404"; that trick is
  gone. Lines barely change (18 lines of code became 15); the point is one copy of a safety rule.
- *Move name clash in plain words:* Move sets no conflict rule, so Graph refuses (HTTP 409) when the destination
  already holds that name, and nothing is overwritten. The page used to show "Microsoft Graph returned HTTP
  409: …"; it now says "An item with that name is already in the destination folder. Nothing was moved."
  (English, like every other service message). No pre-check: it would cost a request and could still race.
  Copy needs nothing: `conflictBehavior=rename` saves a clash as "name 1".
- *Stale comment:* the Copy comment said Copy may target another library; since 0.2.10 it stays in the item's
  own library.
- *Not done (candidates for later):* one `postJson()` helper for the page's 9 POST calls (about 44 lines
  saved), one `require_loaded_site()` for the four site-list checks in the service, and reusing `siteKey()` for
  the page's site comparisons.
- *Checked:* `name_taken` against a fake Graph (found, 404, 500); live `/api/inspect` on a project site: renaming
  "01. Contract Documents" to its sibling's name is refused, a free name gives a preview. No rename, copy or
  move was run; the 409 wording was not triggered live, since that needs a real move.

**Offline tests.** The owner asked for a safe way to test the Graph-facing code. `tests/test_service.py`
(about 580 lines, standard library only) starts the real service on a spare port with the outside world faked:
sign-in, client ID and site discovery return fixed answers; `GraphClient.request` and
`SharePointRestClient.request` answer from an in-memory tenant (one site and a subsite, two libraries, a few
folders and files); `time.sleep` is a no-op. The app's own path handling, paging, If-Match headers and
response parsing still run. 32 checks, about 2 s:
- *Access:* missing token, other origin, unknown route.
- *Rename:* name taken (case-insensitive), invalid characters, same name, wrong type, eTag sent with the rename,
  folder totals, single-use preview, name must match the preview, item changed after the preview, name taken
  after the preview.
- *Copy and Move:* copy never overwrites (`conflictBehavior=rename`), move sends the eTag, name clash gives the
  plain message, same folder, folder into itself, other library, changed size, site not in the list, unknown
  operation.
- *Trim:* rule sent with FullControl, count rule read back, out-of-range days never sent, refused while a trim or
  a version-limit change runs, subsite refused, a different or unconfirmed recorded rule is stopped at once,
  Stop, and the queue marking a subsite.
- *Proof the tests bite:* run against copies of the app with one safety rule broken, each fails the matching
  test: the pre-refactor app (raw 409 text), rename without the eTag comparison, and trim without the
  read-back stop. The unchanged app passes.
- The fakes follow Graph's documented behaviour (409, 412, 202); a test site in the tenant would confirm it.
  The page itself (buttons, dialogs) is not covered.

**Consistent file names.** The owner asked whether the `Start-` prefix was needed (it came from the PowerShell
edition's verb-noun naming) and to name the files consistently, using the usual convention for a command-line
tool: lowercase kebab-case, which also matches the project folder and `~/.sharepoint-navigator`.
- `Start-SharePointNavigator.py` → `sharepoint-navigator.py`; `Start-SharePointNavigator.command` →
  `sharepoint-navigator.command`; `SharePoint-Navigator.html` → `sharepoint-navigator.html`; the build output
  `dist/SharePointNavigator` → `dist/sharepoint-navigator` (the old build in `dist/` stays until the next build).
- Updated: the launcher, `PAGE_FILE`, `build_app.py`, the tests, the page's "start it with …" messages (both
  languages), README (its version line also said 0.2.11), CLAUDE.md, HANDOVER.md and powershell/README.md.
- Kept: the `SharePointNavigatorGraph/1.0` server header (the launcher checks it to see if the app is running),
  the `SharePointNavigator/<version>` user agent sent to Microsoft (a product name), the `powershell/` scripts,
  and the file names in earlier HISTORY entries. Sign-in is unaffected: its cache lives in `~/.sharepoint-navigator/`.
- Checked: compile, `--self-check` (page found), page JS, the 32 offline tests, and a start through the renamed
  launcher on a spare port (28 sites, version 0.3.2), then stopped.

**PowerShell scripts tidied.** Asked to clean up `powershell/`, the owner chose to keep every script and tidy
only names and docs (five of the six are replaced by the app; only the full folder-size export is not).
- `Trim-SharePointSiteFileVersions.ps1` → `Remove-SharePointSiteFileVersions.ps1`: `Trim` is not an approved
  PowerShell verb (`Get-Verb`), and `Remove` is the one for deleting. All file names now use approved verbs.
- Help text brought up to date (comment blocks only): the old navigator and the size worker say the Python app
  replaced them; the site-list exporter no longer claims the app reads its CSV.
- `powershell/README.md` rewritten as a table: each script, what it does, what replaced it, and requirements.
  Root README and CLAUDE.md updated; CLAUDE.md's "leave these scripts as they are" is now "keep them and don't
  change what they do; renames to approved verbs and help-text fixes are fine".
- Not changed: script code. One internal function, `Normalize-SiteUrl` in `Start-SharePointNavigator.ps1`, also
  uses an unapproved verb; renaming it would be a code change, so it stays.
- Checked: every script parses in PowerShell 7 with no errors and `Get-Help` shows the new synopses. None was run.

**Checked.** JS syntax (`node --check`), `--self-check`, and the real app on a spare port (read-only, 28 sites):
wide dark and light, English and Korean, sort by Storage used and by Files in both directions, and the narrow
layout. Size cells: squares and numbers line up from row to row.

## 0.3.1, 1 November 2026

**New: trim queue.** The owner asked to see which sites are already in the trim queue.
- *Automatic check:* once the libraries have loaded, the page checks every site in one request
  (`POST /api/trim-queue`, read-only, six sites at a time, under a second for 28 sites). A **Check trim queue**
  button repeats it.
- *Two kinds of job,* as the old `Get-SharePointSiteTrimQueue.ps1` checked: version trims
  (`GetProgressForDeleteFileVersions`) and version-limit changes applied to a site's libraries
  (`GetProgressForSetVersionPolicyForDocLibs`), which can delete versions too.
- *Where it shows:* a badge under the site's URL ("Trim queued", "Trimming", "Applying version limits"). The
  badge opens the trim dialog. The summary line shows "Trim queue N" with the site names, and how many sites
  couldn't be checked. Hovering it shows when it was last checked.
- *Kept up to date:* opening the dialog, starting or stopping a trim also updates that site's badge.
- *Safety:* Start trim is now also refused (in the page and in the service) while version limits are being
  applied to the site. A subsite in the list is reported as not checked, so it can't show its parent's jobs.

**Recently finished trims.** The owner queued two trims (two project sites, 90 days),
restarted the app and saw "Trim queue 0". Not lost: SharePoint keeps the status, and both had already finished
within 3–5 minutes (422 and 165 versions deleted, 20.8 GB and 6.6 GB freed), so neither was waiting or running
any more. They were the first trims started from the app, and both passed its read-back check. The queue only
counted active jobs, so a quick trim left no trace. Now a trim that ended in the last 7 days also gets a badge
("Trimmed Nov 1" in green, "Trim failed …" in red, or "Trim stopped …" in grey), with its result in the tooltip,
and the summary adds "ended in the last 7 days: …", newest first.

**Less on screen.** The owner found the page too busy. Nothing was removed; detail moved into tooltips or
panes opened on demand:
- The subtitle under the title is gone.
- The summary is one line: Storage used, Old versions, and a **Trims** toggle ("Trims 0 active · 7 recent").
  "Sites" and "Documents libraries" were dropped because the loading line already shows both counts; while
  sizes load, Storage used says how many libraries it covers.
- The **Trims** pane (closed by default, remembered per browser) lists waiting, running and recently ended
  trims with their result, and holds the **Check again** button (was "Check trim queue" in the loading line).
- Rows: badges only for waiting, running or failed trims, on the URL line instead of a line of their own;
  finished trims are listed only in the pane. Size cells show Storage used and Old versions; Size moved to
  the cell's tooltip (it is still the blue part of the bar).
- "Bar = storage used · largest library = 100%" moved from the legend to the bar column's tooltip, and the
  footnote is folded under **About these numbers**.
- Unused strings were removed from both languages.

**Quieter terminal.** The owner asked whether lines like `HTTP: "POST /api/trim-queue HTTP/1.1" 200 -` were
needed. They weren't: successful requests are no longer printed, only failed ones (`HTTP 400: POST /api/...`,
without the query string, which can hold the page token). Since those lines were the only terminal trace of
rename, copy and move, each change now prints its own line ("Renamed … to …", "Moved … to …",
"Copied …" / "Copy submitted …"), as trims already did.

**Checked.** Live: all 28 sites read; nothing is queued or running in the tenant today. The badges, the
summary and the dialog's version-limit notice were checked in a scratch test harness that ran the real app
with three sites' job reports faked in memory (English/Korean, light/dark). Nothing was started or stopped.

## 0.3.0, 1 November 2026

**New: Trim old versions.** Each library row (one per site) has a scissors icon that opens a dialog for the
whole site, every library in it. The owner asked for the same three rules SharePoint offers, which the old
Windows-only `powershell/Trim-SharePointSiteFileVersions.ps1` also used:
- *Automatic (recommended):* SharePoint keeps recent versions and thins out or deletes older ones by age.
- *Delete versions older than N days* (30 to 36,500).
- *Keep a set number of versions:* N versions per file, with draft (minor) versions kept for the newest M.

The dialog first shows the site's last trim: its state, rule, when it was requested and finished, versions
deleted and storage freed. Start stays disabled until the rule is valid, nothing is running on the site, and
the site's short name (last part of its URL) is typed. A queued or running trim can be stopped. The dialog
warns that trimmed versions are deleted permanently and skip the recycle bin.

**How it works.** No PowerShell. The service calls the SharePoint REST forms of the CSOM methods behind
`New-SPOSiteFileVersionBatchDeleteJob`: `POST <site>/_api/site/StartDeleteFileVersionsByMode` with
`{"batchDeleteParameters": {...}}`, plus `GetProgressForDeleteFileVersions` and `CancelDeleteFileVersions`.
The mode is an Int32 with no REST documentation; the values (0 older-than-days, 1 count limits, 2 automatic)
were read from the official CSOM library (NuGet Microsoft.SharePointOnline.CSOM 16.1.27709.12000, enum
`FileVersionBatchDeleteMode`). Unused limits are sent as -1 and `SyncListPolicy` as false, so the libraries'
version settings are not changed. Start and Stop request an `AllSites.FullControl` token, already
admin-consented on the Entra app; reads still use `AllSites.Read`. New routes: `/api/trim-status`,
`/api/trim-start`, `/api/trim-cancel`, limited to sites in the loaded list. The service refuses a start while
a trim is already queued or running on that site.

**Safety checks** (added after the owner asked for a second look, since a trim can't be undone):
- *Right site only:* `/_api/site` always means the whole site collection, so a subsite URL would trim its
  parent. The service now refuses any URL that isn't its own site collection. All 28 current sites pass;
  the guard matters if the app ever falls back to Graph site search, which can return subsites.
- *Rule read back:* after starting, the service reads the new job (new WorkItemId) and compares its mode
  and numbers with the request. If they differ, or no new job shows within about 9 seconds, it stops the
  job at once and reports an error. Trims run in later batches, so this comes before any deletion. The
  parameter names were also checked against the CSOM type `FileVersionBatchDeleteParameters`.
- *One at a time:* start and stop requests are serialized, and a start is refused while a job is queued or
  running, so a double click can't queue two jobs.
- *Visible target:* the dialog shows the site's full URL under its title.

**Checked.** Status read live for all 28 sites (six have finished trims from 28–29 October; the largest
freed 22.5 GB). Unknown sites and bad rules are refused before anything reaches SharePoint. The dialog was
checked in light and dark, English and Korean. **No trim was started or stopped**; the first real one
should be on a small site.

## 0.2.11, 1 November 2026

**Bug.** Every Office document (Word, Excel, PowerPoint) appeared as "Doc.aspx". For those files Graph's
`webUrl` is the Office viewer link (`/_layouts/15/Doc.aspx?sourcedoc=…`), not the file's path, and the
service built item paths and names from `webUrl`. The Open link pointed at the viewer page without its
file, and Rename, Copy or Move on such a file would have used the wrong path. Found when the owner asked
what "Doc.aspx" was (it was an Excel file with a Korean name).

**Fix.** Child paths are built from the parent folder's path plus the item's name (`item_web_path`), and a
`webUrl` that points into `/_layouts/` is never used as a path (`item_path_from_url`, used by the rename
snapshot and the transfer checks). Checked live: real names in the folder, no "Doc.aspx" rows left in the
library, and a rename preview (nothing renamed) resolving the real file path.

## 0.2.10, 1 November 2026

**Why.** The owner does not allow copying or moving between sites, and each site has one Documents library
here, so the destination-library dropdown never had a second choice.

**Changes.**
- Copy and Move both pick a destination in the item's own library; the dropdown and its handler are gone.
  The server already refuses transfers to another site.
- The picker shows a breadcrumb (`Finance/Documents › Reports`) with an Up icon button, folder
  icons and chevrons instead of the 📁 emoji, and the copy hint says "in the same library" (English and Korean).
- The dialog's × no longer opens with a focus ring; it gets a quiet highlight instead.

## 0.2.9, 1 November 2026

**Change.** The row actions are 28px icon buttons instead of words: Open (box with an outward arrow), Rename
(pencil), Copy (two sheets) and Move (folder with an arrow). Icons are inline SVG in the text colour, so
they follow the theme. A short tooltip (`data-tip`) appears after 0.25 s, above the icon and anchored at
its right, or below it on library rows, which pin to the top. Screen readers get the full label, e.g.
"Rename Contract Documents". The actions column narrowed from 190px to 132px, giving the bars more room.

## 0.2.8, 1 November 2026

**Why.** Pointing at a closed library showed a rounded, inset highlight, while an opened library is a square,
full-width band; the owner asked for them to match.

**Change.** Every library row (open or closed) is now a full-width band with square ends; the full-width
geometry moved from the opened-row rule to all library rows, with padding that keeps the columns in line.
Folder and file rows inside a library keep their rounded highlight.

## 0.2.7, 1 November 2026

**Changes.**
- *Closing slide:* collapsing a library or folder slides its pane up over 200 ms with an ease-in curve
  (`cubic-bezier(.4, 0, 1, 1)`), the counterpart of the ease-out opening, and only then closes the row.
  `closePane()` updates state first (forgets the open rows below, marks the row as closing), so a redraw
  during the slide just draws the row closed. "Collapse all" stays instant.
- *Bottom edge:* the 1px lit line now has a soft glow just above it (`--well-glow`), in both themes.

## 0.2.6, 1 November 2026

**Change.** Opening a library or folder slides its pane down: height from 0 to the content's height, rows
fading in and moving down slightly, over 260 ms with an ease-out curve (`cubic-bezier(.22, .8, .24, 1)`).
The slide starts once the folder's contents have arrived, so rows unfold rather than a "Loading…" line.
The page redraws often while sizes stream in, so the start time of each slide is remembered
(`revealStarts`) and a redraw resumes the slide at the same point instead of restarting or cutting it.
Skipped when the system asks for reduced motion. Closing is still instant.

## 0.2.5, 1 November 2026

**Why.** In a long library it was easy to lose track of which library you were in. The owner also preferred a
crisp lit edge to the soft glow at the bottom of the tray.

**Changes.**
- *Pinned library row:* an opened library's row is sticky, so it stays at the top of the screen while its
  contents scroll under it, and slides away with the end of the library. It casts the tray's soft top
  shadow, so the shadow follows it. Collapsing a library from the pinned position scrolls its row back into
  view. The tree panel now uses `overflow: clip` rather than `hidden`, because `hidden` makes the panel a
  scroll container and stops pinning.
- *Bottom edge:* the soft glow is replaced by a solid 1px lit line (`--well-edge`). It shows in the dark theme;
  in the light theme it matches the white panel, so the tray simply ends there.

## 0.2.4, 1 November 2026

**Change.** At the owner's request the 1px edge lines are gone (`--well-line` removed). The tray is set apart by
its background, a soft shadow under its top edge and a soft highlight over its bottom edge.

## 0.2.3, 1 November 2026

**Why.** The owner found the double lines too heavy and asked for one line per edge with soft shading.

**Change.** Each edge of the tray is a single 1px line (`--well-line`). Below the top line, a shadow fades
in over about 4px (`--well-shade`); above the bottom line, a highlight does the same (`--well-glow`).
Both are very faint, in light and dark themes alike.

## 0.2.2, 1 November 2026

**Why.** The owner wanted the look of the list splitting open, with the contents slightly recessed, rather
than a rounded card.

**Change.** The card from 0.2.1 is gone. An opened library's contents now sit in a tray that runs the full
width of the panel, under the library's row: a dark line then a light line on top, a slightly darker
background with a soft inner shadow under the top edge, and a light line then a dark line at the bottom.
Rows inside keep their positions, so the columns still line up. Each theme has its own tray colours
(`--well-*` tokens); the tree's side padding is now `--tree-pad`, so the tray reaches the panel edges.

## 0.2.1, 1 November 2026

**Why.** With a library open, its folders sat between the other libraries and were easy to mistake for them.

**Change.** An opened library and everything opened inside it are drawn as one card: a tinted background,
a hairline outline and a soft shadow, with a little space above and below. The outline is a shadow rather
than a border, so the columns inside still line up with the rows outside. Light and dark themes each have
their own card colours (`--open-*` tokens).

## 0.2.0, 31 October – 1 November 2026

First session in Claude Code, which took over from Codex.

**Why.** The app depended on PowerShell for two things Graph seemed unable to do, which made it slower,
needed a second sign-in, and tied parts of it to one machine. Tests against the tenant showed SharePoint's
own REST API, using the same sign-in, does both.

**Changes.**
- *No PowerShell in the app:* the site list now comes from the SharePoint admin API at start-up (needs the
  SharePoint Administrator role; Graph site search is the fallback), and folder sizes from SharePoint REST
  Storage Metrics. One request returns sizes for all subfolders of an opened folder. The old site-list CSV
  had missed two renamed sites. The scripts in `powershell/` are unchanged and no longer called.
- *No CSV files:* the per-scan report (library roots with zero sizes, read by nothing) is gone.
- *Page redesign:* fixed columns with only the name indented, so bars line up at every depth; one bar scale
  for every row (largest library = 100%); a compact loading line once loading finishes; a quiet one-line
  summary; a styled sort menu; a tab icon.
- *Wording:* plain language throughout. Sizes are "Storage used" (everything SharePoint keeps), "Size" (the
  files as they are now) and "Old versions" (the difference), following Microsoft's own terms.
- *Theme and language:* Light | Dark | System and EN | 한국어, remembered per browser.
- *Auto-stop:* the app stops about 20 seconds after its last browser tab closes.
- *Running it:* `Start-SharePointNavigator.command` (macOS launcher that sets up `.venv` and opens the page),
  Python 3.13 via uv, `build_app.py` for single-file PyInstaller builds, `--self-check` and `--version`.
- *Fixes:* the page updated a throwaway copy of each library row, so opened libraries said "Not loaded yet";
  collapsing a row did not forget the open folders inside it; size and folder errors are now printed in the
  terminal; the favicon request no longer shows as a 403.
- *Code:* comments throughout both files; unused functions and styles removed.

**Also in this session (tenant administration, not the app).** At the owner's request: owner and site
collection admin changes across all sites, and a private Teams channel handed to the owner. The Entra app
gained Graph `Group.ReadWrite.All`, `User.ReadBasic.All` and `ChannelMember.ReadWrite.All` for this. Every
change was logged privately (not in this repository).

## 0.1.0, 27–30 October 2026

Built in one long Codex session (the tool used at the time).

**Changes.**
- *PowerShell edition:* a PnP PowerShell navigator page, a Documents folder-size inventory exporter, and
  Windows-only version-trim and trim-queue scripts (now kept in `powershell/`).
- *Python + Microsoft Graph edition:* a local service on 127.0.0.1 with device-code sign-in and an
  encrypted token cache; a tree of "site / Documents" libraries that loads a folder's direct children
  200 at a time; sizes from a persistent PnP PowerShell worker (`Get-PnPFolderStorageMetric`); a site
  list from a CSV made by a PowerShell exporter.
- *Actions:* rename (preview, then confirm with an eTag check), copy within a site, and move within a
  library, each re-checking the live item first.
- `HANDOVER.md` for the next assistant.
