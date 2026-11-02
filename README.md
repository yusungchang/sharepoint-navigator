# SharePoint Navigator

**See where your SharePoint storage goes.** A small app for Microsoft 365 admins that runs on your own
computer and shows every site's Documents library as one tree: how much each library and folder uses, how much
of that is version history, and where any file is. You can rename, copy and move files and trim old versions.

Product page: <https://yusungchang.github.io/sharepoint-navigator/> · English and 한국어 · light and dark ·
macOS and Windows · MIT licence. Changes are listed in [docs/HISTORY.md](docs/HISTORY.md).

## What it does

- **Every site, one tree.** Each site's Documents library is a row; open it to see its folders, 200 items at a
  time. Nothing is scanned recursively, so even huge libraries open at once.
- **Storage used, split in two.** Each bar shows the current files (blue) and the version history SharePoint
  keeps (orange). One scale for every row: the largest library is 100%.
- **Search across all sites.** One search through SharePoint's index, with filters for site, type, size and
  date. **Show in tree** opens the folders down to the result and highlights it.
- **Rename, copy and move** within a library, with a preview and a check that the item hasn't changed meanwhile.
- **Trim old versions** for a site (Automatic, older than N days, or keep N versions), with a typed
  confirmation and a stop button. Sites with a trim waiting, running or recently finished are marked.
- **Stays on your computer.** The app listens on `127.0.0.1` only, talks only to Microsoft, and keeps the
  sign-in in your system's protected storage (Keychain on macOS, DPAPI on Windows). No telemetry.

## Download

Get the latest build from [Releases](https://github.com/yusungchang/sharepoint-navigator/releases/latest):

- **macOS (Apple silicon):** `SharePoint-Navigator-macOS-AppleSilicon.zip`
- **Windows 10/11 (64-bit):** `SharePoint-Navigator-Windows.zip`

Unzip it first, then double-click the app. A terminal window opens next to the browser; keep it open while you
use the app. Closing the browser tab stops the app.

The builds aren't signed with a paid certificate yet, so the first launch needs one extra step:
- **macOS:** when macOS says it can't verify the app, click **Done**, then open System Settings → Privacy &
  Security, scroll down and click **Open Anyway**. macOS may also ask once to use the saved sign-in in your
  Keychain; choose **Always Allow**.
- **Windows:** if "Windows protected your PC" appears, click **More info**, then **Run anyway**.

## First run

The app asks two questions, once:

1. **Tenant name**: the part before `.sharepoint.com` in your SharePoint address (`contoso` for
   `https://contoso.sharepoint.com`). A full address works too.
2. **Application (client) ID** of your organisation's Entra app (see the next section). Ask your admin.

Both are saved in `~/.sharepoint-navigator/settings.json` (your user folder, not the app), so later launches
go straight to the Microsoft sign-in. Run the app with `--setup` to change them.

Then sign in: the terminal shows a code, the browser opens Microsoft's sign-in page, and you enter the code.
Later launches reuse the sign-in.

**Admins handing the app to staff:** put a file named `<tenant>_clientid.txt` (for example
`contoso_clientid.txt`) containing only the client ID next to the app. The app then asks nothing at all.

## Set up the Entra app (once per organisation)

The app signs in as the person using it ("delegated" permissions), so each organisation registers its own
Entra app once. No client secret is needed. A Global Administrator or Application Administrator does this:

1. Open the [Microsoft Entra admin center](https://entra.microsoft.com) → **App registrations** → **New
   registration**. Name it, for example, *SharePoint Navigator*. Supported account types: **this
   organisational directory only**. Leave Redirect URI empty. Register.
2. **Authentication** → **Advanced settings** → **Allow public client flows**: **Yes**. Save. (The app signs in
   with a device code.)
3. **API permissions** → **Add a permission**, all **Delegated**:
   - **Microsoft Graph:** `Sites.Read.All` (browse, sizes, search) and `Sites.ReadWrite.All` (rename, copy, move).
   - **SharePoint:** `AllSites.Read` (site list, sizes) and `AllSites.FullControl` (only for Trim old versions).
4. Click **Grant admin consent for <your organisation>**.
5. Copy the **Application (client) ID** from the app's Overview page. That's what the app asks for.

Who can see what: the app only shows what the signed-in person may open. The full site list and version trims
need the **SharePoint Administrator** role. Without it the app finds sites through search instead, which lists
only sites the person can access, and trims are refused.

## Run from source

Python 3.11 or later (3.13 recommended). [uv](https://docs.astral.sh/uv/) installs it in your user folder
without admin rights: `uv python install 3.13`.

**macOS:** double-click `sharepoint-navigator.command`. It creates `.venv`, installs the requirements, starts
the app and opens the browser.

**Windows (PowerShell):**

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python .\sharepoint-navigator.py
```

Options: `python sharepoint-navigator.py [tenant]` picks the tenant, `--setup` asks again, `--self-check`
checks an install without signing in, `--version` prints the version. `SHAREPOINT_NAVIGATOR_PORT` changes the
port (default 8765); `SHAREPOINT_NAVIGATOR_AUTO_STOP=0` keeps the app running after the tab closes.

Offline tests (no sign-in, nothing sent to Microsoft): `python -m unittest tests/test_service.py`.

## Build the single-file app

```sh
python -m pip install -r requirements-build.txt
python build_app.py
```

This writes `dist/sharepoint-navigator` (macOS) or `dist\sharepoint-navigator.exe` (Windows) and runs its
self-check. PyInstaller builds only for the system it runs on. Pushing a `v*` tag makes GitHub Actions run the
tests and build both, and attach them to a release ([.github/workflows/build.yml](.github/workflows/build.yml)).

## How it works

- **Microsoft Graph** finds sites and libraries, lists a folder's direct children, renames, copies, moves and
  searches (`POST /search/query`).
- **SharePoint REST**, with tokens from the same sign-in, gives the full site list (admin API
  `GetSitePropertiesFromSharePointByFilters`), folder sizes including versions (`StorageMetrics`; one request
  covers every subfolder of an opened folder), and site version trims (`StartDeleteFileVersionsByMode` and its
  progress and cancel calls).
- Sizes: Storage used is `TotalSize`; current files are `TotalFileStreamSize` (Graph's folder `size` is the
  same); the rest is version history plus a little file information. SharePoint updates them with a delay
  of a few minutes.
- Safety: Rename and Move send the item's eTag, so they fail rather than overwrite a change made meanwhile; Copy
  never overwrites (a clash gets a new name); Copy and Move stay inside the item's own library. A trim is checked
  against what SharePoint recorded right after it starts, and stopped at once if it differs. Every API call
  needs a per-run token, and other web pages can't call the app.

## Licence

[MIT](LICENSE). SharePoint, Microsoft 365 and Entra are trademarks of Microsoft; this project isn't affiliated
with Microsoft.
