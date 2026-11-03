"""Offline tests for the local service: the real app, with Microsoft Graph and SharePoint faked.

Nothing here signs in or reaches a tenant. The service runs on a spare port with these swaps:
- sign-in, client ID and site discovery return fixed answers;
- GraphClient.request and SharePointRestClient.request answer from a small in-memory tenant
  (FakeTenant), so the app's own path handling, paging, If-Match and response parsing still run;
- time.sleep is a no-op, so the trim read-back loop doesn't wait.

The fakes follow Graph's documented behaviour (HTTP 409 for a name clash on PATCH, 412 for a stale
If-Match, 202 for copy). They can't prove real SharePoint behaves that way; a test site does that.

Run from the project folder:  .venv/bin/python -m unittest tests/test_service.py
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import re
import socket
import sys
import threading
import time
import types
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, unquote

ROOT = Path(__file__).resolve().parent.parent
HOST = "contoso.sharepoint.com"
ALPHA = f"https://{HOST}/sites/Alpha"           # the site most tests act on
SUBSITE = f"{ALPHA}/Sub"                         # listed, but part of Alpha's site collection
DOCS = "/sites/Alpha/Shared Documents"           # server-relative root of Alpha's default library
SP_TIME = "%m/%d/%Y %H:%M:%S"                    # SharePoint's job-report time format


def load_app():
    """Import sharepoint-navigator.py as a module (its name has a hyphen, so via importlib)."""
    spec = importlib.util.spec_from_file_location("navigator_service", ROOT / "sharepoint-navigator.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


nav = load_app()


# ---- Fake tenant: one site with two libraries, a few folders and files ----

class FakeTenant:
    """In-memory drives and items, plus SharePoint trim jobs. reset() restores the starting state."""

    def __init__(self):
        self.reset()

    def reset(self):
        """Rebuild the tenant and clear call logs and settings; run before every test."""
        self.items: dict[str, dict] = {}
        self.next_id = 0
        self.graph_calls: list[dict] = []
        self.sp_calls: list[dict] = []
        self.trim_jobs: dict[str, dict] = {}      # raw job reports by lower-cased site URL
        self.policy_jobs: dict[str, dict] = {}
        self.start_behaviour = "match"            # what SharePoint records on start: match, mismatch, none
        self.extra_hits: list[dict] = []           # search hits outside the fake libraries (other sites)
        self.drives = {
            "drive-docs": {"id": "drive-docs", "name": "Documents", "driveType": "documentLibrary",
                           "webUrl": f"https://{HOST}{quote(DOCS)}"},
            "drive-archive": {"id": "drive-archive", "name": "Archive", "driveType": "documentLibrary",
                              "webUrl": f"https://{HOST}/sites/Alpha/Archive"},
        }
        docs = self.add("drive-docs", None, "root", folder=True)
        folder_a = self.add("drive-docs", docs, "Folder A", folder=True)
        self.add("drive-docs", folder_a, "Report.docx", size=100)
        self.add("drive-docs", folder_a, "Notes.txt", size=50)
        self.add("drive-docs", folder_a, "Inner", folder=True)
        folder_b = self.add("drive-docs", docs, "Folder B", folder=True)
        self.add("drive-docs", folder_b, "Report.docx", size=70)   # same name as in Folder A: Move clash
        archive = self.add("drive-archive", None, "root", folder=True)
        self.add("drive-archive", archive, "Old", folder=True)

    def add(self, drive: str, parent: str | None, name: str, folder: bool = False, size: int = 0) -> str:
        """Create an item and return its id."""
        self.next_id += 1
        item_id = f"item-{self.next_id}"
        self.items[item_id] = {"id": item_id, "drive": drive, "parent": parent, "name": name,
                               "folder": folder, "size": size, "version": 1}
        return item_id

    def children(self, item_id: str) -> list[dict]:
        return [item for item in self.items.values() if item["parent"] == item_id]

    def root(self, drive: str) -> dict:
        return next(item for item in self.items.values() if item["drive"] == drive and item["parent"] is None)

    def relative_path(self, item: dict) -> str:
        """Drive-relative path ("" for the root), built from names up the parent chain."""
        names = []
        while item["parent"] is not None:
            names.append(item["name"])
            item = self.items[item["parent"]]
        return "/".join(reversed(names))

    def find(self, drive: str, relative: str) -> dict | None:
        """Walk a drive-relative path, case-insensitively like SharePoint."""
        item = self.root(drive)
        for name in [part for part in relative.split("/") if part]:
            item = next((child for child in self.children(item["id"])
                         if child["name"].casefold() == name.casefold()), None)
            if item is None:
                return None
        return item

    def by_path(self, server_relative: str) -> dict:
        """Item at a server-relative path in Alpha's default library (test helper)."""
        return self.find("drive-docs", server_relative[len(DOCS):])

    def size_of(self, item: dict) -> int:
        """File size, or a folder's total, like Graph's folder ``size``."""
        if not item["folder"]:
            return item["size"]
        return sum(self.size_of(child) for child in self.children(item["id"]))

    def touch(self, item: dict):
        """Simulate someone else editing the item: new eTag, cTag and modified time."""
        item["version"] += 1

    def to_json(self, item: dict) -> dict:
        """The item as Graph returns it (the fields the app selects)."""
        drive = self.drives[item["drive"]]
        relative = self.relative_path(item)
        web_url = drive["webUrl"] + ("/" + quote(relative) if relative else "")
        value = {
            "id": item["id"], "name": item["name"], "size": self.size_of(item), "webUrl": web_url,
            "eTag": f'"{{{item["id"]}}},{item["version"]}"', "cTag": f'"c:{{{item["id"]}}},{item["version"]}"',
            "lastModifiedDateTime": f"2026-10-0{min(item['version'], 9)}T00:00:00Z",
            "parentReference": {"driveId": item["drive"], "id": item["parent"] or ""},
        }
        if item["folder"]:
            value["folder"] = {"childCount": len(self.children(item["id"]))}
        else:
            value["file"] = {"mimeType": "application/octet-stream"}
            # Graph adds this pre-authorised address to file items (shortened here).
            value["@microsoft.graph.downloadUrl"] = f"https://{HOST}/_layouts/15/download.aspx?UniqueId={item['id']}&tempauth=x"
        return value

    def search_hit(self, item: dict) -> dict:
        """One Graph search hit for an item, as the real API sends it when ``fields`` is given.

        Like the real index: webUrl is unencoded, folders report size 0, and the managed
        properties sit under listItem.fields with lower-camel names.
        """
        drive = self.drives[item["drive"]]
        relative = self.relative_path(item)
        return {"resource": {
            "@odata.type": "#microsoft.graph.driveItem", "name": item["name"],
            "webUrl": unquote(drive["webUrl"]) + "/" + relative,
            "size": 0 if item["folder"] else item["size"],
            "lastModifiedDateTime": "2026-10-01T00:00:00Z",
            "listItem": {"fields": {"isContainer": item["folder"], "spWebUrl": ALPHA, "siteTitle": "Alpha",
                                    "fileType": "" if item["folder"] else item["name"].rsplit(".", 1)[-1]}},
        }}

    def search(self, request: dict) -> dict:
        """Answer POST /search/query: every non-root item whose name holds the first word, plus extra_hits.

        Only the first plain word of the KQL is matched; the tests check the KQL itself separately.
        """
        word = re.match(r"\(([^ )]*)", request["query"]["queryString"])
        word = word.group(1).casefold() if word else ""
        hits = [self.search_hit(item) for item in self.items.values()
                if item["parent"] is not None and word in item["name"].casefold()] + self.extra_hits
        start, size = request.get("from", 0), request.get("size", 25)
        page = hits[start:start + size]
        return {"value": [{"searchTerms": [word], "hitsContainers": [
            {"hits": page, "total": len(hits), "moreResultsAvailable": start + size < len(hits)}]}]}

    def record_start(self, site_key: str, parameters: dict):
        """What SharePoint records after StartDeleteFileVersionsByMode, per start_behaviour."""
        if self.start_behaviour == "none":
            return
        mode = parameters["BatchDeleteMode"]
        recorded = mode if self.start_behaviour == "match" else (2 if mode != 2 else 0)
        now = datetime.now(timezone.utc)
        job = {"Status": "New", "WorkItemId": f"job-{len(self.sp_calls)}",
               "BatchDeleteMode": nav.TRIM_MODE_NAMES[recorded], "RequestTimeInUTC": now.strftime(SP_TIME)}
        if recorded == 0:
            days = parameters["DeleteOlderThanDays"] if recorded == mode else 30
            job["DeleteOlderThan"] = (now - timedelta(days=days)).strftime(SP_TIME)
        if recorded == 1:
            job["MajorVersionLimit"] = str(parameters["MajorVersionLimit"])
            job["MajorWithMinorVersionsLimit"] = str(parameters["MajorWithMinorVersionsLimit"])
        self.trim_jobs[site_key] = job

    def graph_patches(self) -> list[dict]:
        return [call for call in self.graph_calls if call["method"] == "PATCH"]

    def graph_deletes(self) -> list[dict]:
        return [call for call in self.graph_calls if call["method"] == "DELETE"]

    def sp_named(self, name: str) -> list[dict]:
        return [call for call in self.sp_calls if call["path"].endswith(name)]


TENANT = FakeTenant()
# Graph site objects by lower-cased host-relative path. Site ids contain commas, as real ones do.
GRAPH_SITES = {
    "sites/alpha": {"id": f"{HOST},site-alpha,web-alpha", "displayName": "Alpha", "webUrl": ALPHA},
    "sites/alpha/sub": {"id": f"{HOST},site-alpha,web-sub", "displayName": "Alpha Sub", "webUrl": SUBSITE},
}
SITE_DRIVES = {"site-alpha,web-alpha": ["drive-docs", "drive-archive"], "site-alpha,web-sub": []}


def graph_error(status: int, message: str):
    """The error the real GraphClient raises for a failed response."""
    return nav.NavigatorError(f"Microsoft Graph returned HTTP {status}: {message}")


class FakeGraph(nav.GraphClient):
    """GraphClient whose request() answers from TENANT; get, pages and patch are the real ones."""

    def __init__(self, auth=None):
        self.auth = auth

    def request(self, method, url_or_path, *, json_body=None, headers=None, return_response=False):
        path = url_or_path[len(nav.GRAPH_ROOT):] if url_or_path.startswith(nav.GRAPH_ROOT) else url_or_path
        route, _, query = path.partition("?")
        TENANT.graph_calls.append({"method": method, "route": route, "query": query,
                                   "body": json_body, "headers": headers or {}})
        if route == "/search/query" and method == "POST":
            return TENANT.search(json_body["requests"][0])
        if match := re.fullmatch(r"/sites/([^/:]+):/(.*)", route):
            site = GRAPH_SITES.get(unquote(match.group(2)).lower())
            if not site:
                raise graph_error(404, "Site not found.")
            return site
        if match := re.fullmatch(r"/sites/([^/]+)/drives", route):
            site_key = unquote(match.group(1)).split(",", 1)[1]
            return {"value": [TENANT.drives[d] for d in SITE_DRIVES[site_key]]}
        if match := re.fullmatch(r"/sites/([^/]+)/drive", route):
            return TENANT.drives["drive-docs"]
        if match := re.fullmatch(r"/drives/([^/]+)/root", route):
            return TENANT.to_json(TENANT.root(unquote(match.group(1))))
        if match := re.fullmatch(r"/drives/([^/]+)/root:/(.+)", route):
            item = TENANT.find(unquote(match.group(1)), unquote(match.group(2)))
            if item is None:
                raise graph_error(404, "The resource could not be found.")
            return TENANT.to_json(item)
        if match := re.fullmatch(r"/drives/([^/]+)/items/([^/]+)/children", route):
            return {"value": [TENANT.to_json(child) for child in TENANT.children(unquote(match.group(2)))]}
        if match := re.fullmatch(r"/drives/([^/]+)/items/([^/]+)/copy", route):
            # Graph copies in the background and answers 202; the tests only check the request.
            return types.SimpleNamespace(status_code=202)
        if match := re.fullmatch(r"/drives/([^/]+)/items/([^/]+)", route):
            item = TENANT.items.get(unquote(match.group(2)))
            if item is None:
                raise graph_error(404, "The resource could not be found.")
            if method == "GET":
                return TENANT.to_json(item)
            if method == "PATCH":
                return self._patch(item, json_body or {}, headers or {})
            if method == "DELETE":
                return self._delete(item, headers or {})
        raise graph_error(400, f"No fake for {method} {route}")

    @staticmethod
    def _patch(item: dict, body: dict, headers: dict) -> dict:
        """Rename or move, refusing a stale If-Match (412) or a name already used (409)."""
        if "If-Match" in headers and headers["If-Match"] != TENANT.to_json(item)["eTag"]:
            raise graph_error(412, "ETag does not match the current item.")
        new_parent = (body.get("parentReference") or {}).get("id") or item["parent"]
        new_name = body.get("name") or item["name"]
        if any(other["name"].casefold() == new_name.casefold() and other["id"] != item["id"]
               for other in TENANT.children(new_parent)):
            raise graph_error(409, "Name already exists.")
        item["parent"], item["name"] = new_parent, new_name
        TENANT.touch(item)
        return TENANT.to_json(item)


    @staticmethod
    def _delete(item: dict, headers: dict) -> dict:
        """Delete an item and everything under it (Graph: to the recycle bin), refusing a stale If-Match (412)."""
        if "If-Match" in headers and headers["If-Match"] != TENANT.to_json(item)["eTag"]:
            raise graph_error(412, "ETag does not match the current item.")
        doomed = [item["id"]]
        for item_id in doomed:                      # grows while walking: breadth-first over the subtree
            doomed.extend(child["id"] for child in TENANT.children(item_id))
        for item_id in doomed:
            del TENANT.items[item_id]
        return {}


class FakeSharePoint(nav.SharePointRestClient):
    """SharePointRestClient whose request() answers trim and site calls from TENANT."""

    def __init__(self, auth=None):
        self.auth = auth

    def request(self, method, url, *, json_body=None, write=False):
        self._scopes(url, write)  # keep the real "SharePoint hosts only" guard
        site_part, _, path = url.partition("/_api")
        site_key = nav.normalize_site_url(unquote(site_part)).lower()
        TENANT.sp_calls.append({"method": method, "site": site_key, "path": path, "body": json_body, "write": write})
        if path.startswith("/site?$select=Url"):
            # A subsite's /_api/site is its parent site collection.
            return {"Url": ALPHA if site_key == SUBSITE.lower() else site_part}
        if path == "/site/GetProgressForDeleteFileVersions":
            return {"value": json.dumps(TENANT.trim_jobs.get(site_key, {"Status": "NoRequestFound"}))}
        if path == "/site/GetProgressForSetVersionPolicyForDocLibs":
            return {"value": json.dumps(TENANT.policy_jobs.get(site_key, {"Status": "NoRequestFound"}))}
        if path == "/site/StartDeleteFileVersionsByMode":
            TENANT.record_start(site_key, json_body["batchDeleteParameters"])
            return {}
        if path == "/site/CancelDeleteFileVersions":
            if site_key in TENANT.trim_jobs:
                TENANT.trim_jobs[site_key]["Status"] = "Cancelled"
            return {}
        raise nav.NavigatorError(f"SharePoint returned HTTP 404: no fake for {path}")


class FakeAuth:
    """Stands in for the MSAL sign-in (already signed in); the fakes never look at tokens."""

    def __init__(self, *args):
        pass

    def signed_in(self):
        return True

    def token(self):
        return "fake-token"

    def token_for(self, scopes, force_refresh=False):
        return "fake-token"


# ---- Service harness ----

class ServiceTest(unittest.TestCase):
    """Starts the real service once with the fakes; every test starts from a fresh FakeTenant."""

    @classmethod
    def setUpClass(cls):
        # Swap the outside world for fakes. run_server looks these names up when it starts.
        nav.AuthSession = FakeAuth
        nav.GraphClient = FakeGraph
        nav.SharePointRestClient = FakeSharePoint
        nav.discover_sites = lambda tenant, sharepoint, graph: (
            [{"url": ALPHA, "title": "Alpha"}, {"url": SUBSITE, "title": "Alpha Sub"}], "test site list")
        nav.webbrowser = types.SimpleNamespace(open=lambda url: None)
        nav.time = types.SimpleNamespace(sleep=lambda seconds: None, time=time.time)
        os.environ["SHAREPOINT_NAVIGATOR_AUTO_STOP"] = "0"
        # Delete's required wait between preview and confirmation, shortened (see DeleteTests.WAIT).
        os.environ["SHAREPOINT_NAVIGATOR_DELETE_WAIT"] = "0.05"
        # The service prints to the terminal; keep that in a buffer the tests can read.
        cls.log = io.StringIO()
        cls.real_stdout, sys.stdout = sys.stdout, cls.log
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            cls.port = probe.getsockname()[1]
        cls.base = f"http://127.0.0.1:{cls.port}"
        cls.thread = threading.Thread(target=nav.run_server, daemon=True,
                                      args=(cls.port, "contoso", "00000000-0000-0000-0000-000000000000"))
        cls.thread.start()
        for _ in range(100):
            try:
                page = urllib.request.urlopen(cls.base + "/").read().decode("utf-8")
                break
            except OSError:
                time.sleep(0.05)
        else:
            sys.stdout = cls.real_stdout
            raise RuntimeError("The service did not start:\n" + cls.log.getvalue())
        cls.token = re.search(r"serviceToken = '([^']+)'", page).group(1)
        # Sign-in and site discovery run in the background; wait until the routes are ready.
        for _ in range(100):
            if cls.call("/api/status")[1].get("phase") == "ready":
                break
            time.sleep(0.05)

    @classmethod
    def tearDownClass(cls):
        cls.call("/api/stop", {})
        cls.thread.join(timeout=5)
        sys.stdout = cls.real_stdout

    def setUp(self):
        TENANT.reset()
        self.log_start = len(self.log.getvalue())

    @classmethod
    def call(cls, path, body=None, token=True, origin=None):
        """Send a request like the page does; returns (HTTP status, parsed JSON)."""
        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-Local-Token"] = cls.token
        if origin:
            headers["Origin"] = origin
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(cls.base + path, data=data, headers=headers,
                                         method="GET" if body is None else "POST")
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            return error.code, json.load(error)

    def new_log(self) -> str:
        """Terminal output printed during this test."""
        return self.log.getvalue()[self.log_start:]

    def refused(self, path, body, words):
        """Assert the call fails with a message containing ``words``; return the message."""
        status, result = self.call(path, body)
        self.assertEqual(status, 400, result)
        self.assertFalse(result["ok"])
        self.assertIn(words, result["error"])
        return result["error"]


# ---- Access ----

class AccessTests(ServiceTest):
    def test_missing_token_is_refused(self):
        status, result = self.call("/api/inspect", {}, token=False)
        self.assertEqual(status, 403)
        self.assertIn("token", result["error"])

    def test_other_origin_is_refused(self):
        status, result = self.call("/api/inspect", {}, origin="https://evil.example")
        self.assertEqual(status, 403)
        self.assertIn("Origin", result["error"])

    def test_unknown_route_is_404(self):
        status, _ = self.call("/api/run-shell", {})
        self.assertEqual(status, 404)


# ---- Rename (inspect, then rename) ----

class RenameTests(ServiceTest):
    REPORT = f"{DOCS}/Folder A/Report.docx"

    def inspect(self, new_name, item_path=REPORT, item_type="file"):
        return self.call("/api/inspect", {"siteUrl": ALPHA, "itemPath": item_path,
                                          "itemType": item_type, "newName": new_name})

    def test_name_taken_is_refused(self):
        self.refused("/api/inspect", {"siteUrl": ALPHA, "itemPath": self.REPORT, "itemType": "file",
                                      "newName": "notes.TXT"}, "already exists")

    def test_invalid_characters_are_refused(self):
        # A trailing space isn't listed: the service strips spaces from the name before checking it.
        for name in ("a:b.docx", "a/b", "trailing."):
            self.refused("/api/inspect", {"siteUrl": ALPHA, "itemPath": self.REPORT, "itemType": "file",
                                          "newName": name}, "invalid character")

    def test_same_name_is_refused(self):
        self.refused("/api/inspect", {"siteUrl": ALPHA, "itemPath": self.REPORT, "itemType": "file",
                                      "newName": "Report.docx"}, "same as the current name")

    def test_wrong_item_type_is_refused(self):
        self.refused("/api/inspect", {"siteUrl": ALPHA, "itemPath": self.REPORT, "itemType": "folder",
                                      "newName": "X"}, "changed type")

    def test_rename_sends_the_previewed_etag(self):
        item = TENANT.by_path(self.REPORT)
        etag = TENANT.to_json(item)["eTag"]
        _, preview = self.inspect("Summary.docx")
        status, result = self.call("/api/rename", {"inspectionId": preview["inspectionId"], "newName": "Summary.docx"})
        self.assertEqual(status, 200, result)
        self.assertEqual(item["name"], "Summary.docx")
        self.assertEqual(TENANT.graph_patches()[0]["headers"].get("If-Match"), etag)
        self.assertIn("Renamed", self.new_log())

    def test_folder_rename_counts_its_contents(self):
        _, preview = self.inspect("Folder C", f"{DOCS}/Folder A", "folder")
        self.assertEqual((preview["sizeBytes"], preview["fileCount"]), (150, 2))

    def test_preview_is_single_use(self):
        _, preview = self.inspect("Summary.docx")
        body = {"inspectionId": preview["inspectionId"], "newName": "Summary.docx"}
        self.assertEqual(self.call("/api/rename", body)[0], 200)
        self.refused("/api/rename", body, "already used")

    def test_name_must_match_the_preview(self):
        _, preview = self.inspect("Summary.docx")
        self.refused("/api/rename", {"inspectionId": preview["inspectionId"], "newName": "Other.docx"}, "does not match")
        self.assertEqual(TENANT.graph_patches(), [])

    def test_item_changed_after_preview_is_refused(self):
        _, preview = self.inspect("Summary.docx")
        TENANT.touch(TENANT.by_path(self.REPORT))
        self.refused("/api/rename", {"inspectionId": preview["inspectionId"], "newName": "Summary.docx"}, "changed after the preview")
        self.assertEqual(TENANT.graph_patches(), [])
        self.assertNotIn("Renamed", self.new_log())

    def test_name_taken_after_preview_is_refused(self):
        _, preview = self.inspect("Summary.docx")
        TENANT.add("drive-docs", TENANT.by_path(f"{DOCS}/Folder A")["id"], "Summary.docx", size=1)
        self.refused("/api/rename", {"inspectionId": preview["inspectionId"], "newName": "Summary.docx"}, "now exists")
        self.assertEqual(TENANT.graph_patches(), [])


# ---- Copy and Move ----

class TransferTests(ServiceTest):
    def transfer(self, operation, item, destination, **extra):
        return self.call("/api/transfer", {"operation": operation, "siteUrl": ALPHA, "itemPath": item,
                                           "destinationPath": destination, **extra})

    def test_copy_never_overwrites(self):
        status, result = self.transfer("copy", f"{DOCS}/Folder A/Report.docx", f"{DOCS}/Folder B")
        self.assertEqual(status, 200, result)
        self.assertTrue(result["queued"])
        copy = next(call for call in TENANT.graph_calls if call["route"].endswith("/copy"))
        self.assertIn("conflictBehavior=rename", copy["query"])
        self.assertEqual(TENANT.graph_patches(), [])

    def test_move_sends_the_etag_and_moves(self):
        item = TENANT.by_path(f"{DOCS}/Folder A/Notes.txt")
        etag = TENANT.to_json(item)["eTag"]
        status, result = self.transfer("move", f"{DOCS}/Folder A/Notes.txt", f"{DOCS}/Folder B")
        self.assertEqual(status, 200, result)
        self.assertEqual(item["parent"], TENANT.by_path(f"{DOCS}/Folder B")["id"])
        self.assertEqual(TENANT.graph_patches()[0]["headers"].get("If-Match"), etag)
        self.assertIn("Moved", self.new_log())

    def test_move_name_clash_is_explained(self):
        item = TENANT.by_path(f"{DOCS}/Folder A/Report.docx")
        error = self.refused("/api/transfer", {"operation": "move", "siteUrl": ALPHA,
                                               "itemPath": f"{DOCS}/Folder A/Report.docx",
                                               "destinationPath": f"{DOCS}/Folder B"}, "already in the destination folder")
        self.assertNotIn("HTTP", error)
        self.assertEqual(item["parent"], TENANT.by_path(f"{DOCS}/Folder A")["id"])
        self.assertNotIn("Moved", self.new_log())

    def test_move_into_the_same_folder_is_refused(self):
        self.refused("/api/transfer", {"operation": "move", "siteUrl": ALPHA, "itemPath": f"{DOCS}/Folder A/Notes.txt",
                                       "destinationPath": f"{DOCS}/Folder A"}, "already in that folder")

    def test_folder_into_itself_is_refused(self):
        for operation in ("copy", "move"):
            self.refused("/api/transfer", {"operation": operation, "siteUrl": ALPHA, "itemPath": f"{DOCS}/Folder A",
                                           "destinationPath": f"{DOCS}/Folder A/Inner"}, "into itself")

    def test_move_to_another_library_is_refused(self):
        self.refused("/api/transfer", {"operation": "move", "siteUrl": ALPHA, "itemPath": f"{DOCS}/Folder A/Notes.txt",
                                       "destinationPath": "/sites/Alpha/Archive/Old"}, "same document library")
        self.assertEqual(TENANT.graph_patches(), [])

    def test_changed_size_is_refused(self):
        self.refused("/api/transfer", {"operation": "move", "siteUrl": ALPHA, "itemPath": f"{DOCS}/Folder A/Notes.txt",
                                       "destinationPath": f"{DOCS}/Folder B", "expectedSizeBytes": 999}, "size changed")

    def test_site_outside_the_list_is_refused(self):
        self.refused("/api/transfer", {"operation": "move", "siteUrl": f"https://{HOST}/sites/Gamma",
                                       "itemPath": "/sites/Gamma/Shared Documents/x", "destinationPath": "/sites/Gamma/Shared Documents/y"},
                     "not in this tenant's loaded site list")

    def test_unknown_operation_is_refused(self):
        self.refused("/api/transfer", {"operation": "delete", "siteUrl": ALPHA, "itemPath": f"{DOCS}/Folder A",
                                       "destinationPath": f"{DOCS}/Folder B"}, "Choose Copy or Move")


# ---- Version trim ----

class TrimTests(ServiceTest):
    SITE = ALPHA.lower()

    def start(self, **rule):
        return self.call("/api/trim-start", {"siteUrl": ALPHA, **(rule or {"mode": "days", "days": 90})})

    def test_start_sends_the_rule_with_full_control(self):
        status, result = self.start()
        self.assertEqual(status, 200, result)
        start = TENANT.sp_named("StartDeleteFileVersionsByMode")
        self.assertEqual(len(start), 1)
        self.assertTrue(start[0]["write"])
        parameters = start[0]["body"]["batchDeleteParameters"]
        self.assertEqual((parameters["BatchDeleteMode"], parameters["DeleteOlderThanDays"]), (0, 90))
        self.assertFalse(parameters["SyncListPolicy"])
        self.assertEqual(TENANT.sp_named("CancelDeleteFileVersions"), [])
        self.assertTrue(result["trim"]["running"])

    def test_count_rule_is_checked_on_read_back(self):
        status, result = self.start(mode="count", majorVersions=10, minorVersions=2)
        self.assertEqual(status, 200, result)
        self.assertEqual(TENANT.sp_named("CancelDeleteFileVersions"), [])

    def test_out_of_range_days_never_reach_sharepoint(self):
        self.refused("/api/trim-start", {"siteUrl": ALPHA, "mode": "days", "days": 5}, "from 30")
        self.assertEqual(TENANT.sp_named("StartDeleteFileVersionsByMode"), [])

    def test_refused_while_a_trim_is_running(self):
        TENANT.trim_jobs[self.SITE] = {"Status": "InProgress", "WorkItemId": "old"}
        self.refused("/api/trim-start", {"siteUrl": ALPHA, "mode": "automatic"}, "already queued or running")
        self.assertEqual(TENANT.sp_named("StartDeleteFileVersionsByMode"), [])

    def test_refused_while_version_limits_are_applied(self):
        TENANT.policy_jobs[self.SITE] = {"Status": "InProgress"}
        self.refused("/api/trim-start", {"siteUrl": ALPHA, "mode": "automatic"}, "version-limit change")
        self.assertEqual(TENANT.sp_named("StartDeleteFileVersionsByMode"), [])

    def test_subsite_is_refused(self):
        self.refused("/api/trim-start", {"siteUrl": SUBSITE, "mode": "automatic"}, "part of the site")
        self.assertEqual(TENANT.sp_named("StartDeleteFileVersionsByMode"), [])

    def test_different_recorded_rule_is_stopped_at_once(self):
        TENANT.start_behaviour = "mismatch"
        self.refused("/api/trim-start", {"siteUrl": ALPHA, "mode": "days", "days": 90}, "different rule")
        cancel = TENANT.sp_named("CancelDeleteFileVersions")
        self.assertEqual(len(cancel), 1)
        self.assertTrue(cancel[0]["write"])

    def test_unconfirmed_trim_is_stopped_at_once(self):
        TENANT.start_behaviour = "none"
        self.refused("/api/trim-start", {"siteUrl": ALPHA, "mode": "automatic"}, "couldn't confirm")
        self.assertEqual(len(TENANT.sp_named("CancelDeleteFileVersions")), 1)

    def test_stop_cancels_with_full_control(self):
        TENANT.trim_jobs[self.SITE] = {"Status": "InProgress", "WorkItemId": "old"}
        status, result = self.call("/api/trim-cancel", {"siteUrl": ALPHA})
        self.assertEqual(status, 200, result)
        self.assertTrue(TENANT.sp_named("CancelDeleteFileVersions")[0]["write"])
        self.assertFalse(result["trim"]["running"])

    def test_queue_marks_the_subsite(self):
        status, result = self.call("/api/trim-queue", {})
        self.assertEqual(status, 200, result)
        by_site = {site["siteUrl"]: site for site in result["sites"]}
        self.assertIn("trim", by_site[ALPHA])
        self.assertIn("Part of the site", by_site[SUBSITE]["error"])



# ---- Search ----

class SearchTests(ServiceTest):
    def search(self, **body):
        return self.call("/api/search", {"query": "report", **body})

    def last_search(self) -> dict:
        """The request body the app sent to /search/query."""
        return [call for call in TENANT.graph_calls if call["route"] == "/search/query"][-1]["body"]["requests"][0]

    def test_results_carry_path_site_and_type(self):
        status, result = self.search(query="folder")
        self.assertEqual(status, 200, result)
        rows = {row["itemPath"]: row for row in result["rows"]}
        folder = rows[f"{DOCS}/Folder A"]
        self.assertTrue(folder["isFolder"])
        self.assertIsNone(folder["sizeBytes"])            # the index says 0 for folders; don't show it
        self.assertEqual((folder["siteUrl"], folder["inSiteList"]), (ALPHA, True))
        self.assertEqual(result["total"], 2)

    def test_file_hit_keeps_its_size(self):
        _, result = self.search()
        report = next(row for row in result["rows"] if row["itemPath"] == f"{DOCS}/Folder A/Report.docx")
        self.assertFalse(report["isFolder"])
        self.assertEqual((report["sizeBytes"], report["fileType"]), (100, "docx"))

    def test_subsite_wins_over_its_parent(self):
        TENANT.extra_hits = [{"resource": {"name": "Plan #1.docx", "size": 5,
                                           "webUrl": f"{SUBSITE}/Shared Documents/Plan #1.docx"}}]
        _, result = self.search(query="plan")
        row = next(row for row in result["rows"] if row["name"] == "Plan #1.docx")
        self.assertEqual(row["siteUrl"], SUBSITE)
        self.assertEqual(row["itemPath"], "/sites/Alpha/Sub/Shared Documents/Plan #1.docx")  # "#" kept

    def test_site_outside_the_list_is_marked(self):
        TENANT.extra_hits = [{"resource": {"name": "x.pdf", "webUrl": f"https://{HOST}/sites/Gamma/Docs/x.pdf"}}]
        _, result = self.search(query="nothing-matches-this")
        self.assertEqual(len(result["rows"]), 1)
        self.assertFalse(result["rows"][0]["inSiteList"])

    def test_query_is_scoped_to_the_tenant_and_filtered(self):
        status, result = self.search(type="pdf", size="100mb", modified="1y", sort="size")
        self.assertEqual(status, 200, result)
        sent = self.last_search()
        kql = sent["query"]["queryString"]
        self.assertTrue(kql.startswith("(report) filetype:pdf Size>=104857600 LastModifiedTime<"), kql)
        self.assertTrue(kql.endswith('path:"https://contoso.sharepoint.com/"'), kql)
        self.assertEqual(sent["entityTypes"], ["driveItem"])
        self.assertIn("IsContainer", sent["fields"])
        self.assertEqual(sent["sortProperties"], [{"name": "Size", "isDescending": True}])

    def test_site_scope_ends_with_a_slash(self):
        self.search(siteUrl=ALPHA)
        self.assertIn('path:"https://contoso.sharepoint.com/sites/Alpha/"', self.last_search()["query"]["queryString"])

    def test_home_site_scope_excludes_other_sites(self):
        kql = nav.search_kql("x", "contoso", site_url=f"https://{HOST}")
        self.assertIn('-path:"https://contoso.sharepoint.com/sites/"', kql)

    def test_paging_reports_the_next_block(self):
        for index in range(nav.SEARCH_PAGE_SIZE + 5):
            TENANT.add("drive-docs", TENANT.by_path(f"{DOCS}/Folder B")["id"], f"Bulk report {index}.txt", size=1)
        _, first = self.search()
        self.assertTrue(first["moreAvailable"])
        self.assertEqual(first["nextFrom"], nav.SEARCH_PAGE_SIZE)
        _, second = self.search(**{"from": first["nextFrom"]})
        self.assertFalse(second["moreAvailable"])
        self.assertEqual(self.last_search()["from"], nav.SEARCH_PAGE_SIZE)

    def test_search_is_read_only(self):
        self.search()
        self.assertEqual([call["route"] for call in TENANT.graph_calls], ["/search/query"])
        self.assertEqual(TENANT.sp_calls, [])

    def test_empty_search_is_refused(self):
        self.refused("/api/search", {"query": "  "}, "Type something")
        self.assertEqual(TENANT.graph_calls, [])

    def test_filter_alone_is_allowed(self):
        status, _ = self.call("/api/search", {"query": "", "size": "1gb"})
        self.assertEqual(status, 200)
        self.assertTrue(self.last_search()["query"]["queryString"].startswith("Size>=1073741824 "))

    def test_unknown_filter_is_refused(self):
        self.refused("/api/search", {"query": "x", "type": "everything"}, "Unknown search type")

    def test_site_outside_the_list_is_refused(self):
        self.refused("/api/search", {"query": "x", "siteUrl": f"https://{HOST}/sites/Gamma"},
                     "not in this tenant's loaded site list")

    def test_too_deep_paging_is_refused(self):
        self.refused("/api/search", {"query": "x", "from": nav.SEARCH_MAX_FROM}, "Only the first")



# ---- Delete (preview, then delete to the recycle bin) ----

class DeleteTests(ServiceTest):
    REPORT = f"{DOCS}/Folder A/Report.docx"
    FOLDER = f"{DOCS}/Folder A"
    WAIT = 0.08                                     # just over the service's shortened wait (0.05 s)

    def preview(self, item_path=REPORT, item_type="file", site=ALPHA):
        status, result = self.call("/api/delete-inspect", {"siteUrl": site, "itemPath": item_path, "itemType": item_type})
        self.assertEqual(status, 200, result)
        return result

    def confirm(self, preview, wait=True, **overrides):
        """Send the confirmation the page would send after the countdown, with optional changes."""
        if wait:
            time.sleep(self.WAIT)
        body = {"deleteId": preview["deleteId"], "confirmName": preview["name"],
                "confirmFileCount": preview["fileCount"], "acknowledge": "delete-to-recycle-bin", **overrides}
        return self.call("/api/delete", body)

    def assert_nothing_deleted(self):
        self.assertEqual(TENANT.graph_deletes(), [])
        self.assertNotIn("Deleted", self.new_log())

    def test_preview_changes_nothing(self):
        preview = self.preview(self.FOLDER, "folder")
        self.assertEqual((preview["sizeBytes"], preview["fileCount"]), (150, 2))
        self.assertEqual(TENANT.graph_deletes() + TENANT.graph_patches(), [])

    def test_file_delete_sends_the_previewed_etag(self):
        item = TENANT.by_path(self.REPORT)
        etag = TENANT.to_json(item)["eTag"]
        status, result = self.confirm(self.preview())
        self.assertEqual(status, 200, result)
        self.assertIsNone(TENANT.by_path(self.REPORT))
        self.assertEqual(TENANT.graph_deletes()[0]["headers"].get("If-Match"), etag)
        self.assertIn("Deleted (to the recycle bin) file", self.new_log())

    def test_folder_delete_removes_its_contents(self):
        status, result = self.confirm(self.preview(self.FOLDER, "folder"))
        self.assertEqual(status, 200, result)
        self.assertIsNone(TENANT.by_path(self.FOLDER))
        self.assertIsNotNone(TENANT.by_path(f"{DOCS}/Folder B/Report.docx"))   # the neighbour is untouched

    def test_library_root_is_refused(self):
        self.refused("/api/delete-inspect", {"siteUrl": ALPHA, "itemPath": DOCS, "itemType": "folder"}, "whole library")

    def test_site_outside_the_list_is_refused(self):
        self.refused("/api/delete-inspect", {"siteUrl": f"https://{HOST}/sites/Gamma",
                                             "itemPath": "/sites/Gamma/Shared Documents/x", "itemType": "file"},
                     "not in this tenant's loaded site list")

    def test_wrong_item_type_is_refused(self):
        self.refused("/api/delete-inspect", {"siteUrl": ALPHA, "itemPath": self.REPORT, "itemType": "folder"}, "changed type")

    def test_too_quick_a_confirmation_is_refused_and_used_up(self):
        preview = self.preview()
        status, result = self.confirm(preview, wait=False)
        self.assertEqual(status, 400)
        self.assertIn("too quickly", result["error"])
        # The preview is gone even though nothing happened: the person must start again.
        status, result = self.confirm(preview)
        self.assertIn("already used", result["error"])
        self.assert_nothing_deleted()

    def test_name_must_match_exactly(self):
        for typed in ("report.docx", "Report.docx ", "", "Report"):
            status, result = self.confirm(self.preview(), confirmName=typed)
            self.assertEqual(status, 400)
            self.assertIn("typed name", result["error"])
        self.assert_nothing_deleted()

    def test_folder_file_count_must_match(self):
        status, result = self.confirm(self.preview(self.FOLDER, "folder"), confirmFileCount="3")
        self.assertIn("file count", result["error"])
        status, result = self.confirm(self.preview(self.FOLDER, "folder"), confirmFileCount=None)
        self.assertIn("file count", result["error"])
        self.assert_nothing_deleted()

    def test_acknowledgement_is_required(self):
        status, result = self.confirm(self.preview(), acknowledge="yes")
        self.assertIn("acknowledged", result["error"])
        self.assert_nothing_deleted()

    def test_preview_is_single_use(self):
        preview = self.preview()
        self.assertEqual(self.confirm(preview)[0], 200)
        status, result = self.confirm(preview)
        self.assertIn("already used", result["error"])
        self.assertEqual(len(TENANT.graph_deletes()), 1)

    def test_item_changed_after_preview_is_refused(self):
        preview = self.preview()
        TENANT.touch(TENANT.by_path(self.REPORT))
        status, result = self.confirm(preview)
        self.assertIn("changed after the preview", result["error"])
        self.assert_nothing_deleted()

    def test_file_added_to_folder_after_preview_is_refused(self):
        preview = self.preview(self.FOLDER, "folder")
        TENANT.add("drive-docs", TENANT.by_path(f"{self.FOLDER}/Inner")["id"], "New.txt", size=1)
        status, result = self.confirm(preview, confirmFileCount=2)
        self.assertIn("changed after the preview", result["error"])
        self.assert_nothing_deleted()

    def test_unknown_preview_is_refused(self):
        self.refused("/api/delete", {"deleteId": "nope", "confirmName": "Report.docx",
                                     "acknowledge": "delete-to-recycle-bin"}, "expired or was already used")
        self.assert_nothing_deleted()

    def test_rename_preview_cannot_be_used_to_delete(self):
        _, rename = self.call("/api/inspect", {"siteUrl": ALPHA, "itemPath": self.REPORT,
                                               "itemType": "file", "newName": "Summary.docx"})
        time.sleep(self.WAIT)
        self.refused("/api/delete", {"deleteId": rename["inspectionId"], "confirmName": "Report.docx",
                                     "acknowledge": "delete-to-recycle-bin"}, "expired or was already used")
        self.assert_nothing_deleted()


# ---- Download ----

class DownloadTests(ServiceTest):
    def link(self, item_path, site=ALPHA):
        return self.call("/api/download-link", {"siteUrl": site, "itemPath": item_path})

    def test_file_gets_a_sharepoint_link(self):
        status, result = self.link(f"{DOCS}/Folder A/Report.docx")
        self.assertEqual(status, 200, result)
        self.assertTrue(result["url"].startswith(f"https://{HOST}/"))
        self.assertEqual(result["name"], "Report.docx")
        self.assertEqual(TENANT.graph_patches(), [])          # read-only
        # "$select" makes real Graph drop the downloadUrl annotation; "select" keeps it.
        query = [c["query"] for c in TENANT.graph_calls if "downloadUrl" in c["query"]][0]
        self.assertTrue(query.startswith("select="), query)

    def test_folder_is_refused(self):
        self.refused("/api/download-link", {"siteUrl": ALPHA, "itemPath": f"{DOCS}/Folder A"}, "Only files")

    def test_site_outside_the_list_is_refused(self):
        self.refused("/api/download-link", {"siteUrl": f"https://{HOST}/sites/Gamma", "itemPath": "/sites/Gamma/x.txt"},
                     "not in this tenant's loaded site list")


# ---- Tenant and client ID settings (no service needed) ----

class TempSettings:
    """Mixin: a temporary app folder and settings file for one test."""

    GUID = "11111111-2222-3333-4444-555555555555"

    def use_temp_settings(self):
        import tempfile
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        (root / "app").mkdir()
        self.saved_paths = (nav.APP_ROOT, nav.USER_FOLDER, nav.SETTINGS_FILE)
        nav.APP_ROOT, nav.USER_FOLDER = root / "app", root / "user"
        nav.SETTINGS_FILE = nav.USER_FOLDER / "settings.json"

    def restore_settings(self):
        nav.APP_ROOT, nav.USER_FOLDER, nav.SETTINGS_FILE = self.saved_paths
        self.temp.cleanup()


class SettingsTests(TempSettings, unittest.TestCase):
    """known_tenant and known_client_id: nothing is asked here; unknowns go to the setup screen."""

    def setUp(self):
        self.use_temp_settings()

    def tearDown(self):
        self.restore_settings()

    def test_nothing_known_at_first(self):
        self.assertIsNone(nav.known_tenant([]))
        self.assertIsNone(nav.known_client_id("contoso"))

    def test_saved_settings_are_remembered(self):
        nav.save_settings("contoso", self.GUID)
        self.assertEqual(nav.known_tenant([]), "contoso")
        self.assertEqual(nav.known_client_id("contoso"), self.GUID)

    def test_file_beside_the_app_wins(self):
        (nav.APP_ROOT / "fabrikam_clientid.txt").write_text(self.GUID + "\n", encoding="utf-8")
        nav.save_settings("contoso", "99999999-8888-7777-6666-555555555555")
        self.assertEqual(nav.known_tenant([]), "fabrikam")
        self.assertEqual(nav.known_client_id("fabrikam"), self.GUID)

    def test_command_line_tenant_is_used(self):
        self.assertEqual(nav.known_tenant(["contoso-admin.sharepoint.com"]), "contoso")

    def test_invalid_tenant_is_refused(self):
        with self.assertRaises(nav.NavigatorError):
            nav.tenant_from_input("contoso evil")


# ---- Setup screen and device-code sign-in ----

class DeviceCodeAuth(FakeAuth):
    """Not signed in yet: hands out a device code and waits until the test 'enters' it."""

    entered = threading.Event()

    def signed_in(self):
        return False

    def begin_device_flow(self):
        return {"user_code": "ABCD-1234", "verification_uri": "https://microsoft.com/devicelogin", "expires_in": 900}

    def complete_device_flow(self, flow, exit_condition=None):
        while not DeviceCodeAuth.entered.wait(0.02):
            if exit_condition and exit_condition(flow):
                raise nav.NavigatorError("Sign-in stopped.")


class ConnectTests(TempSettings, unittest.TestCase):
    """A server started with nothing known: setup screen, device code, then ready."""

    def setUp(self):
        self.use_temp_settings()
        self.saved_auth = nav.AuthSession
        nav.AuthSession = DeviceCodeAuth
        DeviceCodeAuth.entered.clear()
        nav.GraphClient, nav.SharePointRestClient = FakeGraph, FakeSharePoint
        nav.discover_sites = lambda tenant, sharepoint, graph: ([{"url": ALPHA, "title": "Alpha"}], "test site list")
        nav.webbrowser = types.SimpleNamespace(open=lambda url: None)
        os.environ["SHAREPOINT_NAVIGATOR_AUTO_STOP"] = "0"
        self.real_stdout, sys.stdout = sys.stdout, io.StringIO()
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            self.port = probe.getsockname()[1]
        self.base = f"http://127.0.0.1:{self.port}"
        self.thread = threading.Thread(target=nav.run_server, args=(self.port,), daemon=True)
        self.thread.start()
        for _ in range(100):
            try:
                page = urllib.request.urlopen(self.base + "/").read().decode("utf-8")
                break
            except OSError:
                time.sleep(0.05)
        self.token = re.search(r"serviceToken = '([^']+)'", page).group(1)

    def tearDown(self):
        self.call("/api/stop", {})
        self.thread.join(timeout=5)
        sys.stdout = self.real_stdout
        nav.AuthSession = self.saved_auth
        self.restore_settings()

    def call(self, path, body=None):
        return ServiceTest.call.__func__(self, path, body)

    def wait_for(self, phase):
        for _ in range(200):
            status = self.call("/api/status")[1]
            if status["phase"] == phase:
                return status
            time.sleep(0.02)
        self.fail(f"never reached {phase}: {status}")

    def test_setup_then_code_then_ready(self):
        self.assertEqual(self.call("/api/status")[1]["phase"], "setup")
        status, result = self.call("/api/scan", {})
        self.assertEqual(status, 409)                      # nothing works before sign-in
        self.call("/api/setup", {"tenant": "https://Contoso.sharepoint.com", "clientId": self.GUID})
        code = self.wait_for("code")
        self.assertEqual(code["code"], "ABCD-1234")
        self.assertGreater(code["expiresIn"], 0)
        DeviceCodeAuth.entered.set()
        ready = self.wait_for("ready")
        self.assertEqual((ready["tenantId"], ready["siteCount"]), ("contoso", 1))
        self.assertEqual(nav.known_client_id("contoso"), self.GUID)   # saved for next time
        self.assertEqual(self.call("/api/scan", {})[0], 202)

    def test_bad_client_id_is_refused(self):
        status, result = self.call("/api/setup", {"tenant": "contoso", "clientId": "not-a-guid"})
        self.assertEqual(status, 400)
        self.assertIn("client) ID", result["error"])
        self.assertEqual(self.call("/api/status")[1]["phase"], "setup")

    def test_change_organisation_stops_the_waiting_sign_in(self):
        self.call("/api/setup", {"tenant": "contoso", "clientId": self.GUID})
        self.wait_for("code")
        self.call("/api/setup-reset", {})
        self.assertEqual(self.call("/api/status")[1]["phase"], "setup")
        DeviceCodeAuth.entered.set()                       # the old sign-in finishing changes nothing
        time.sleep(0.2)
        self.assertEqual(self.call("/api/status")[1]["phase"], "setup")


if __name__ == "__main__":
    unittest.main()
