#!/usr/bin/env python3
"""Run the real app against a made-up company ("Contoso"), for screenshots and demos.

Nothing signs in and nothing reaches Microsoft: sign-in, site discovery, Graph and SharePoint REST
are replaced by an in-memory tenant built from a fixed random seed, so every run looks the same.
All page code and all of the service's own logic (paths, paging, sizes, search parsing) are real.

    python tools/demo.py [port] [--setup | --signin]
        default port 8790; opens nothing, Ctrl+C to stop. --setup starts at the setup screen;
        --signin shows the sign-in code screen (with a made-up code) and stays there.

For screenshots, tools/shots.py starts this and drives the page. The page gets two small extras,
only in the demo: a URL fragment (#lang=ko&theme=dark&shot=tree) chooses language, theme and what
to show, and the session-events stream is switched off so a headless browser can finish loading.
"""
from __future__ import annotations

import importlib.util
import json
import os
import random
import re
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote, unquote

ROOT = Path(__file__).resolve().parent.parent
HOST = "contoso.sharepoint.com"
GB = 1024 ** 3
MB = 1024 ** 2


def load_app():
    """Import sharepoint-navigator.py as a module (its name has a hyphen)."""
    spec = importlib.util.spec_from_file_location("navigator_demo", ROOT / "sharepoint-navigator.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


nav = load_app()

# ---- The made-up tenant ----
# Site name, URL name, current-files size of its library, share of extra space taken by versions.
SITES = [
    ("Engineering", "Engineering", 412 * GB, 0.62),
    ("Marketing", "Marketing", 238 * GB, 0.35),
    ("Product Design", "ProductDesign", 176 * GB, 0.48),
    ("Finance", "Finance", 64 * GB, 0.21),
    ("Sales", "Sales", 58 * GB, 0.30),
    ("Legal", "Legal", 31 * GB, 0.12),
    ("Human Resources", "HR", 22 * GB, 0.15),
    ("Operations", "Operations", 17 * GB, 0.40),
    ("IT", "IT", 9 * GB, 0.25),
]
# Folder and file names per site; "{y}" becomes a year.
FOLDERS = {
    "Engineering": ["Builds", "Test Data", "Firmware", "CAD Models", "Specifications", "Releases", "Field Logs", "Archive"],
    "Marketing": ["Campaigns", "Brand Assets", "Video", "Photos", "Events", "Press", "Web", "Archive"],
    "ProductDesign": ["Prototypes", "Renders", "Research", "UX", "Sketches", "Handoff", "Archive"],
    "Finance": ["Budget", "Reports", "Invoices", "Audit", "Payroll", "Forecasts"],
    "Sales": ["Proposals", "Contracts", "Price Lists", "Customer Decks", "Quotes", "Training"],
    "Legal": ["Contracts", "Policies", "NDAs", "Trademarks", "Litigation"],
    "HR": ["Onboarding", "Policies", "Training", "Recruiting", "Reviews"],
    "Operations": ["Facilities", "Logistics", "Vendors", "Safety", "Inventory"],
    "IT": ["Scripts", "Licences", "Diagrams", "Backups", "Handbooks"],
}
SUBFOLDERS = ["{y}", "Q1 {y}", "Q2 {y}", "Q3 {y}", "Q4 {y}", "Drafts", "Final", "Shared", "Old", "Project Atlas", "Project Nova", "Client Review"]
FILES = [
    ("Budget {y}.xlsx", 0.4), ("Quarterly Report {y}.docx", 0.6), ("Board Deck {y}.pptx", 8), ("Contract Summary.pdf", 1.2),
    ("Launch Video {y}.mp4", 900), ("Product Shots.zip", 600), ("Site Survey {y}.pdf", 14), ("Raw Footage {y}.mov", 2400),
    ("Model Export.step", 120), ("Test Results {y}.csv", 30), ("Release Notes.docx", 0.3), ("Backup {y}.zip", 3000),
    ("Price List {y}.xlsx", 0.5), ("Training Session.mp4", 450), ("Brand Guide.pdf", 25), ("Floor Plan.pdf", 6),
]


class Tenant:
    """Sites, drives and items in memory, sized so each library adds up to its target."""

    def __init__(self):
        rng = random.Random(7)
        self.items: dict[str, dict] = {}
        self.drives: dict[str, dict] = {}
        self.sites: dict[str, dict] = {}
        for title, url_name, target, history in SITES:
            site_id = f"{HOST},site-{url_name.lower()},web-{url_name.lower()}"
            drive_id = f"drive-{url_name.lower()}"
            web_url = f"https://{HOST}/sites/{url_name}"
            self.sites[url_name.lower()] = {"id": site_id, "displayName": title, "webUrl": web_url,
                                            "drive": drive_id, "history": history}
            self.drives[drive_id] = {"id": drive_id, "name": "Documents", "driveType": "documentLibrary",
                                     "webUrl": f"{web_url}/{quote('Shared Documents')}", "site": url_name.lower()}
            root = self.add(drive_id, None, "root", folder=True)
            # Spread the target size over folders with uneven weights, like real libraries.
            leaves = []
            for name in FOLDERS[url_name]:
                top = self.add(drive_id, root, name, folder=True)
                for sub in rng.sample(SUBFOLDERS, rng.randint(2, 5)):
                    leaves.append(self.add(drive_id, top, sub.format(y=rng.choice([2022, 2023, 2024, 2025, 2026])), folder=True))
                leaves.append(top)
            weights = [rng.paretovariate(1.2) for _ in leaves]
            scale = target / sum(weights)
            for leaf, weight in zip(leaves, weights):
                budget = weight * scale
                # Repeats are fine: add() renames them "Name (2).ext", as SharePoint would.
                picks = rng.choices(FILES, k=rng.randint(6, 30))
                total_hint = sum(mb for _, mb in picks)
                for index, (pattern, mb) in enumerate(picks):
                    name = pattern.format(y=rng.choice([2022, 2023, 2024, 2025, 2026]))
                    size = int(budget * mb / total_hint * rng.uniform(0.8, 1.2))
                    self.add(drive_id, leaf, name, size=max(size, 20_000), days=rng.randint(1, 1400))

    def add(self, drive, parent, name, folder=False, size=0, days=30):
        """Create an item (names are unique within a folder) and return its id."""
        if parent is not None:
            taken = {item["name"].casefold() for item in self.children(parent)}
            base, n = name, 2
            while name.casefold() in taken:
                stem, dot, ext = base.rpartition(".")
                name = f"{stem} ({n}).{ext}" if dot and not folder else f"{base} ({n})"
                n += 1
        item_id = f"item-{len(self.items) + 1}"
        self.items[item_id] = {"id": item_id, "drive": drive, "parent": parent, "name": name,
                               "folder": folder, "size": size, "days": days}
        self._children_cache = None
        return item_id

    def children(self, item_id):
        if getattr(self, "_children_cache", None) is None:
            self._children_cache = {}
            for item in self.items.values():
                self._children_cache.setdefault(item["parent"], []).append(item)
        return self._children_cache.get(item_id, [])

    def root(self, drive):
        return next(i for i in self.items.values() if i["drive"] == drive and i["parent"] is None)

    def relative(self, item):
        names = []
        while item["parent"] is not None:
            names.append(item["name"])
            item = self.items[item["parent"]]
        return "/".join(reversed(names))

    def find(self, drive, relative):
        item = self.root(drive)
        for name in [p for p in relative.split("/") if p]:
            item = next((c for c in self.children(item["id"]) if c["name"].casefold() == name.casefold()), None)
            if item is None:
                return None
        return item

    def size(self, item):
        if not item["folder"]:
            return item["size"]
        return sum(self.size(c) for c in self.children(item["id"]))

    def files(self, item):
        if not item["folder"]:
            return 1
        return sum(self.files(c) for c in self.children(item["id"]))

    def modified(self, item):
        from datetime import datetime, timedelta, timezone
        when = datetime(2026, 11, 1, 9, 30, tzinfo=timezone.utc) - timedelta(days=item["days"])
        return when.strftime("%Y-%m-%dT%H:%M:%SZ")

    def json(self, item):
        """The item as Graph returns it."""
        drive = self.drives[item["drive"]]
        relative = self.relative(item)
        value = {"id": item["id"], "name": item["name"], "size": self.size(item),
                 "webUrl": drive["webUrl"] + ("/" + quote(relative) if relative else ""),
                 "eTag": f'"{item["id"]},1"', "cTag": f'"c:{item["id"]},1"',
                 "lastModifiedDateTime": self.modified(item),
                 "parentReference": {"driveId": item["drive"], "id": item["parent"] or ""}}
        if item["folder"]:
            value["folder"] = {"childCount": len(self.children(item["id"]))}
        else:
            value["file"] = {"mimeType": "application/octet-stream"}
            # Points nowhere real: the demo has no files to download.
            value["@microsoft.graph.downloadUrl"] = f"https://{HOST}/_layouts/15/download.aspx?demo={item['id']}"
        return value

    def metric(self, item, history):
        """StorageMetrics for a folder: versions add a site-specific share on top of current files."""
        current = self.size(item)
        return {"TotalSize": int(current * (1 + history)), "TotalFileStreamSize": current,
                "TotalFileCount": self.files(item), "LastModified": self.modified(item)}

    def item_at(self, server_relative):
        """The item at a decoded server-relative path, with its site, or (None, None)."""
        for site in self.sites.values():
            drive = self.drives[site["drive"]]
            root = unquote(drive["webUrl"].split(HOST, 1)[1])
            if server_relative == root or server_relative.startswith(root + "/"):
                return self.find(drive["id"], server_relative[len(root):]), site
        return None, None


TENANT = Tenant()


def graph_error(status, message):
    return nav.NavigatorError(f"Microsoft Graph returned HTTP {status}: {message}")


class DemoGraph(nav.GraphClient):
    """GraphClient answering from TENANT."""

    def __init__(self, auth=None):
        self.auth = auth

    def request(self, method, url_or_path, *, json_body=None, headers=None, return_response=False):
        path = url_or_path[len(nav.GRAPH_ROOT):] if url_or_path.startswith(nav.GRAPH_ROOT) else url_or_path
        route = path.partition("?")[0]
        if route == "/search/query":
            return self.search(json_body["requests"][0])
        if m := re.fullmatch(r"/sites/([^/:]+):/sites/([^/]+)", route):
            site = TENANT.sites.get(unquote(m.group(2)).lower())
            if not site:
                raise graph_error(404, "Site not found.")
            return {k: site[k] for k in ("id", "displayName", "webUrl")}
        if m := re.fullmatch(r"/sites/([^/]+)/drives?", route):
            site = next(s for s in TENANT.sites.values() if s["id"] == unquote(m.group(1)))
            drive = {k: v for k, v in TENANT.drives[site["drive"]].items() if k != "site"}
            return {"value": [drive]} if route.endswith("drives") else drive
        if m := re.fullmatch(r"/drives/([^/]+)/root", route):
            return TENANT.json(TENANT.root(unquote(m.group(1))))
        if m := re.fullmatch(r"/drives/([^/]+)/root:/(.+)", route):
            item = TENANT.find(unquote(m.group(1)), unquote(m.group(2)))
            if item is None:
                raise graph_error(404, "The resource could not be found.")
            return TENANT.json(item)
        if m := re.fullmatch(r"/drives/([^/]+)/items/([^/]+)/children", route):
            return {"value": [TENANT.json(c) for c in TENANT.children(unquote(m.group(2)))]}
        if m := re.fullmatch(r"/drives/([^/]+)/items/([^/]+)", route):
            return TENANT.json(TENANT.items[unquote(m.group(2))])
        # Demo is read-only: rename, copy and move are refused.
        raise graph_error(403, "This is a demo; changes are switched off.")

    @staticmethod
    def search(request):
        """Name search over every item, honouring the folder/file and size filters and size sort."""
        kql = request["query"]["queryString"]
        word = re.match(r"\(([^)]*)\)", kql)
        words = word.group(1).casefold().split() if word else []
        min_size = int((re.search(r"Size>=(\d+)", kql) or [0, 0])[1])
        hits = []
        for item in TENANT.items.values():
            if item["parent"] is None or not all(w in item["name"].casefold() for w in words):
                continue
            if "IsContainer:true" in kql and not item["folder"] or "IsContainer:false" in kql and item["folder"]:
                continue
            size = 0 if item["folder"] else item["size"]
            if min_size and size < min_size:
                continue
            drive = TENANT.drives[item["drive"]]
            site = TENANT.sites[drive["site"]]
            hits.append({"resource": {"name": item["name"], "size": size, "lastModifiedDateTime": TENANT.modified(item),
                                      "webUrl": unquote(drive["webUrl"]) + "/" + TENANT.relative(item),
                                      "listItem": {"fields": {"isContainer": item["folder"], "spWebUrl": site["webUrl"],
                                                              "siteTitle": site["displayName"]}}}})
        if request.get("sortProperties"):
            hits.sort(key=lambda h: -h["resource"]["size"])
        start, size = request.get("from", 0), request.get("size", 25)
        return {"value": [{"hitsContainers": [{"hits": hits[start:start + size], "total": len(hits),
                                                "moreResultsAvailable": start + size < len(hits)}]}]}


class DemoSharePoint(nav.SharePointRestClient):
    """SharePointRestClient answering sizes, trim status and site checks from TENANT."""

    def __init__(self, auth=None):
        self.auth = auth

    def request(self, method, url, *, json_body=None, write=False):
        site_part, _, path = url.partition("/_api")
        if write:
            raise nav.NavigatorError("SharePoint returned HTTP 403: This is a demo; changes are switched off.")
        if path.startswith("/site?$select=Url"):
            return {"Url": unquote(site_part)}
        if path == "/site/GetProgressForDeleteFileVersions":
            # One site shows a finished trim, so the page's trim badges and pane have something to show.
            if site_part.endswith("/Marketing"):
                return {"value": json.dumps({"Status": "CompleteSuccess", "WorkItemId": "demo",
                                             "BatchDeleteMode": "DeleteOlderThanDays",
                                             "RequestTimeInUTC": "10/31/2026 08:00:00", "CompleteTimeInUTC": "10/31/2026 08:04:00",
                                             "VersionsDeleted": "1842", "StorageReleased": str(31 * GB)})}
            return {"value": json.dumps({"Status": "NoRequestFound"})}
        if path == "/site/GetProgressForSetVersionPolicyForDocLibs":
            return {"value": json.dumps({"Status": "NoRequestFound"})}
        if m := re.match(r"/web/GetFolderByServerRelativePath\(decodedurl='(.*)'\)(/Folders)?\?", path):
            folder, site = TENANT.item_at(unquote(m.group(1)).replace("''", "'"))
            if folder is None:
                raise nav.NavigatorError("SharePoint returned HTTP 404: File Not Found.")
            if m.group(2):
                return {"value": [{"Name": c["name"], "StorageMetrics": TENANT.metric(c, site["history"])}
                                  for c in TENANT.children(folder["id"]) if c["folder"]]}
            return {"StorageMetrics": TENANT.metric(folder, site["history"])}
        raise nav.NavigatorError(f"SharePoint returned HTTP 404: no demo answer for {path}")


class DemoAuth:
    """Stands in for the MSAL sign-in (already signed in)."""

    def __init__(self, *args):
        pass

    def signed_in(self):
        return True

    def token(self):
        return "demo"

    def token_for(self, scopes, force_refresh=False):
        return "demo"


class DemoSignInAuth(DemoAuth):
    """For --signin: not signed in yet; shows a made-up code and waits until the demo stops."""

    def signed_in(self):
        return False

    def begin_device_flow(self):
        return {"user_code": "DXQF-7KLM", "verification_uri": "https://microsoft.com/devicelogin", "expires_in": 900}

    def complete_device_flow(self, flow, exit_condition=None):
        import time
        while not (exit_condition and exit_condition(flow)):
            time.sleep(0.2)
        raise nav.NavigatorError("Demo sign-in stopped.")


# Added to the page, demo only: language/theme from the URL fragment, no session stream, and
# (for screenshots) a few clicks once everything has loaded. The page's own code is unchanged.
HEAD_SCRIPT = """<script>
(() => {
  const opts = Object.fromEntries(new URLSearchParams(location.hash.slice(1)));
  window.__demo = opts;
  try {
    if (opts.lang) localStorage.setItem('spnav-lang', opts.lang);
    if (opts.theme) localStorage.setItem('spnav-theme', opts.theme);
  } catch {}
  // A headless browser waits for open connections; the demo doesn't need auto-stop.
  window.EventSource = class { constructor() {} addEventListener() {} close() {} };
})();
</script>"""
END_SCRIPT = """<script>
(() => {
  const opts = window.__demo || {};
  const wait = (test, ms = 15000) => new Promise((resolve, reject) => {
    const start = Date.now();
    const tick = () => test() ? resolve(test()) : Date.now() - start > ms ? reject(new Error('timeout')) : setTimeout(tick, 100);
    tick();
  });
  const libraryRows = () => [...document.querySelectorAll('#tree > details.node > summary')];
  async function run() {
    // Libraries listed and every library measured.
    await wait(() => libraryRows().length >= 9 && !document.querySelector('#tree .size-note'));
    if (opts.shot === 'tree' || opts.shot === 'menu') {
      libraryRows()[0].click();
      await wait(() => document.querySelectorAll('#tree details.node[open] > .children .node').length > 3);
      await new Promise(r => setTimeout(r, 900));
      const folders = [...document.querySelectorAll('#tree details.node[open] > .children > details.node[data-kind="folder"] > summary')];
      if (folders[0]) folders[0].click();
      await new Promise(r => setTimeout(r, 1500));
      await wait(() => !document.querySelector('#tree .size-note'));
    } else if (opts.shot === 'search') {
      document.getElementById('searchSize').value = '100mb';
      document.getElementById('searchSort').value = 'size';
      const box = document.getElementById('search');
      box.value = opts.q || '2025';
      document.getElementById('searchButton').click();
      await wait(() => document.querySelectorAll('#searchResults .search-row').length > 0);
    }
    window.scrollTo(0, 0);
    if (opts.shot === 'menu') {
      // The product page's "where the tools are" shot: a file row's ⋯ menu, opened like a click
      // would. No scrolling (scrolling closes the menu): the window is tall, and tools/shots.py
      // crops the picture around the row and its menu.
      await new Promise(r => setTimeout(r, 300));
      const file = [...document.querySelectorAll('#tree details.node[data-kind="file"] > summary')]
        .find(s => s.getBoundingClientRect().top > innerHeight * 0.45);
      if (file) file.querySelector('.row-menu-button').click();
      await new Promise(r => setTimeout(r, 300));
    }
    document.body.dataset.demoReady = '1';
  }
  run().catch(err => { document.body.dataset.demoReady = 'error: ' + err.message; });
})();
</script>"""


def install(page_dir: Path, signin: bool = False):
    """Swap the outside world for the demo and point the service at a page copy with the extras."""
    nav.AuthSession = DemoSignInAuth if signin else DemoAuth
    nav.GraphClient = DemoGraph
    nav.SharePointRestClient = DemoSharePoint
    nav.discover_sites = lambda tenant, sharepoint, graph: (
        [{"url": s["webUrl"], "title": s["displayName"]} for s in TENANT.sites.values()], "demo site list")
    html = (ROOT / nav.PAGE_FILE).read_text(encoding="utf-8")
    html = html.replace("</head>", HEAD_SCRIPT + "\n</head>", 1).replace("</body>", END_SCRIPT + "\n</body>", 1)
    (page_dir / nav.PAGE_FILE).write_text(html, encoding="utf-8")
    nav.RESOURCE_ROOT = page_dir


def main():
    numbers = [a for a in sys.argv[1:] if a.isdigit()]
    port = int(numbers[0]) if numbers else 8790
    os.environ["SHAREPOINT_NAVIGATOR_AUTO_STOP"] = "0"
    with tempfile.TemporaryDirectory() as page_dir:
        install(Path(page_dir), signin="--signin" in sys.argv)
        # The demo never writes the real settings file.
        nav.save_settings = lambda tenant, client_id=None: None
        nav.load_settings = lambda: {"tenant": "contoso"}
        # The running file (version and stop key) goes to the temporary folder too, never the
        # real ~/.sharepoint-navigator: tools/shots.py ends the demo before it can clean up.
        nav.USER_FOLDER = Path(page_dir)
        nav.run_server(port, "contoso", "00000000-0000-0000-0000-000000000000",
                       force_setup="--setup" in sys.argv, open_browser=False)


if __name__ == "__main__":
    main()
