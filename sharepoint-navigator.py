#!/usr/bin/env python3
"""Local SharePoint Navigator backed by Microsoft Graph and SharePoint REST.

A small local web service for a Microsoft 365 / SharePoint admin. It serves one page
(sharepoint-navigator.html) to the default browser for browsing the Documents libraries of every
site in the tenant, seeing how much storage each library and folder uses, renaming, copying,
moving or deleting files and folders, and trimming a site's old file versions. No PowerShell is required.

Why two APIs: Graph resolves sites and libraries, lists folders and does rename/copy/move, but
its folder ``size`` is current content only and its delegated getAllSites is blocked. SharePoint
REST, using the same sign-in, fills both gaps:
* Site list: the admin API GetSitePropertiesFromSharePointByFilters returns every site but needs
  the SharePoint Administrator role; Graph ``/sites?search=*`` (search-index limited) is the fallback.
* Version-inclusive sizes from folder StorageMetrics. The page shows "Size" (TotalFileStreamSize,
  current content, same as Graph's size), "Storage used" (TotalSize, including old versions and a
  little metadata) and "Old versions" (the difference).
* Version trim per site (every library in it): Site StartDeleteFileVersionsByMode, Get-
  ProgressForDeleteFileVersions and CancelDeleteFileVersions, the calls behind the SharePoint Online
  PowerShell trim cmdlets. Starting or stopping one uses an AllSites.FullControl token.
  /api/trim-queue reads every site's trim and version-policy job (GetProgressForSetVersionPolicyForDocLibs).

Delete: /api/delete-inspect takes a live snapshot (folders counted fully) under a single-use id;
/api/delete then needs the item's exact name, a folder's file count, a short wait, and an unchanged
item before Graph DELETE (If-Match) moves it to the site's recycle bin. Library roots are refused.

Download: /api/download-link returns Graph's short-lived @microsoft.graph.downloadUrl for one file.

Search: /api/search sends one Graph POST /search/query (Microsoft Search, driveItem hits) across
every site, read-only and limited to this tenant's SharePoint host. The page lists the hits and can
open each one or show it in the tree.

Sign-in: MSAL device-code flow; the token cache is encrypted by msal-extensions (Keychain/DPAPI)
in ~/.sharepoint-navigator/, and SharePoint tokens come silently from the same refresh token. The
Entra app needs public client flows and admin-consented delegated Graph Sites.Read.All and
Sites.ReadWrite.All, plus SharePoint AllSites.Read and (for version trim) AllSites.FullControl.

Update check: the page itself (not this service) asks api.github.com for the newest release's
version number, only when the person clicks Check for updates.

Second launch: if a copy already runs on the port, the same or a newer version just has its page
opened; an older one is stopped with the key it keeps in ~/.sharepoint-navigator/running-<port>.json
(this user only), and the new copy starts. Copies before 1.2.0 leave no key, so the person is told
to click Stop app in the old page.

Security: binds to 127.0.0.1 only. A random per-run token is injected into the page and required
on every API call (X-Local-Token header, or the query string for EventSource); requests with any
other Origin are refused.

Auto-stop: each tab holds GET /api/session-events open; 15 s after the last one closes with no
reconnect, the service stops. SHAREPOINT_NAVIGATOR_AUTO_STOP=0 disables it and
SHAREPOINT_NAVIGATOR_AUTO_STOP_GRACE sets the wait in seconds.

Run: ``python sharepoint-navigator.py [tenant]`` (the name before .sharepoint.com; else
SHAREPOINT_NAVIGATOR_TENANT or a prompt). The client ID is read from <tenant>_clientid.txt beside
the app; SHAREPOINT_NAVIGATOR_PORT overrides port 8765. ``--self-check`` verifies a build or
install without signing in. When frozen by PyInstaller, APP_ROOT is the executable's folder and
RESOURCE_ROOT holds the bundled page.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import sys
import threading
import time
import unicodedata
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlsplit

import msal
import requests
from msal_extensions import PersistedTokenCache, build_encrypted_persistence


# ---- Configuration ----

# App version, "vibe" scheme x.y.z: each working session raises z; a meaningful change raises y
# and resets z. The only place it is set; every change is recorded in docs/HISTORY.md.
__version__ = "1.4.0"

# User files (client ID) live in APP_ROOT; bundled files (the HTML page) in RESOURCE_ROOT.
FROZEN = bool(getattr(sys, "frozen", False))
def _app_root() -> Path:
    """The folder the app sits in, where an admin may put <tenant>_clientid.txt.

    For a macOS .app the executable is inside "Name.app/Contents/MacOS", so the folder holding
    the .app is three levels up.
    """
    if not FROZEN:
        return Path(__file__).resolve().parent
    exe = Path(sys.executable).resolve()
    if exe.parent.name == "MacOS" and exe.parents[2].suffix == ".app":
        return exe.parents[3]
    return exe.parent


APP_ROOT = _app_root()
RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", APP_ROOT))
PAGE_FILE = "sharepoint-navigator.html"
GRAPH_ROOT = "https://graph.microsoft.com/v1.0"
# Delegated Graph scopes. ReadWrite is needed for rename, copy, move and delete.
SCOPES = ["Sites.Read.All", "Sites.ReadWrite.All"]
# Extra (non-default) libraries are included only when they carry one of these names.
LIBRARY_NAMES = {"documents", "shared documents"}
# Sites the admin list returns that hold no browsable Documents library for this app.
SKIPPED_SITE_TEMPLATES = ("redirectsite#", "spsmsitehost#", "srchcen#", "appcatalog#", "spspers#")
# Warn at this count: the admin API returns one batch with no continuation marker.
ADMIN_SITE_BATCH_WARNING = 300
# Microsoft throttling guidance asks for a decorated User-Agent (NONISV|Company|App/Version).
USER_AGENT = f"NONISV|SharePointNavigator|SharePointNavigator/{__version__}"
# Stop this many seconds after the last tab disconnects (lets a page refresh reconnect).
AUTO_STOP_GRACE_SECONDS = 15
# How often the session-events stream writes a keep-alive line; a failed write reveals a closed tab.
SESSION_PING_SECONDS = 5
# Delete: the confirmation is refused if it comes sooner than this after the preview, so the page's
# countdown can't be skipped by a quick script or a double click. SHAREPOINT_NAVIGATOR_DELETE_WAIT
# overrides it (the offline tests shorten it).
DELETE_WAIT_SECONDS = 5
# Delete: how long a delete preview stays valid.
DELETE_PREVIEW_MINUTES = 3
# Characters SharePoint does not allow in file or folder names.
NAME_BAD_CHARS = set('\\/:*?"<>|')
# Per-user folder: the encrypted sign-in cache and settings.json (tenant name and client ID per tenant).
# It is outside the app and the project, so a shared copy or the public repo never holds them.
USER_FOLDER = Path.home() / ".sharepoint-navigator"
SETTINGS_FILE = USER_FOLDER / "settings.json"


def running_file(port: int) -> Path:
    """While a copy serves on ``port``, it keeps its version and stop key here (this user only).

    A newer copy started later reads it to stop the older one and take over (see take_over).
    One file per port, so the demo and tests on other ports never touch the real app's file.
    """
    return USER_FOLDER / f"running-{port}.json"
# Where an admin's Entra app setup is explained (shown when the app asks for a client ID).
SETUP_GUIDE_URL = "https://github.com/yusungchang/sharepoint-navigator#set-up-the-entra-app-once-per-organisation"
# requests timeout as (connect seconds, read seconds).
HTTP_TIMEOUT = (15, 120)


class NavigatorError(Exception):
    """An expected, user-facing failure; its message is shown to the admin as-is."""
    pass


# ---- URL and path helpers ----

def normalize_site_url(value: str) -> str:
    """Return a canonical https site URL (decoded path, no trailing slash); raise if invalid."""
    parts = urlsplit(value.strip())
    if parts.scheme != "https" or not parts.hostname:
        raise NavigatorError(f"Invalid SharePoint site URL: {value}")
    return f"https://{parts.netloc}{unquote(parts.path).rstrip('/')}"


def server_path(value: str) -> str:
    """Return the decoded server-relative path of a URL ("/" for the site root)."""
    return unquote(urlsplit(value).path).rstrip("/") or "/"


def graph_path(value: str) -> str:
    """URL-encode a drive-relative path for Graph ``root:/<path>``, keeping slashes."""
    return quote(value.strip("/"), safe="/")


# ---- Sign-in ----

class AuthSession:
    """One MSAL sign-in shared by both clients. Nothing here waits on a terminal: the service runs
    the device-code steps in the background and the page shows the code (see run_server's connect)."""

    def __init__(self, tenant: str, client_id: str):
        """Open the encrypted token cache and create the MSAL client; doesn't sign in yet."""
        self.tenant = tenant
        self.client_id = client_id
        USER_FOLDER.mkdir(parents=True, exist_ok=True)
        cache_path = USER_FOLDER / f"{tenant}-msal-cache.bin"
        # OS secret store only; there is deliberately no plaintext fallback.
        try:
            persistence = build_encrypted_persistence(str(cache_path))
            self.cache = PersistedTokenCache(persistence)
        except Exception as exc:
            raise NavigatorError(
                "Could not open the encrypted sign-in cache. Install the requirements again; "
                f"details: {exc}"
            ) from exc
        authority = f"https://login.microsoftonline.com/{tenant}.onmicrosoft.com"
        self.client = msal.PublicClientApplication(
            client_id=client_id, authority=authority, token_cache=self.cache
        )

    def _silent(self, scopes: list[str], force_refresh: bool = False) -> dict | None:
        """A token result from the cache (refreshing it if needed), or None if a new sign-in is needed."""
        result = None
        for account in self.client.get_accounts():
            result = self.client.acquire_token_silent(scopes, account=account, force_refresh=force_refresh)
            if result and result.get("access_token"):
                return result
        return result if result and result.get("access_token") else None

    def signed_in(self) -> bool:
        """True if an earlier sign-in can be reused without asking the person again."""
        return self._silent(SCOPES) is not None

    def begin_device_flow(self) -> dict:
        """Start a device-code sign-in; the result holds user_code, verification_uri and expires_in."""
        flow = self.client.initiate_device_flow(scopes=SCOPES)
        if "user_code" not in flow:
            detail = flow.get("error_description") or flow.get("error") or json.dumps(flow)
            raise NavigatorError(
                "Could not start the Microsoft sign-in. Check the tenant name and client ID, and that the "
                f"Entra app allows public client flows. Details: {str(detail)[:400]}"
            )
        return flow

    def complete_device_flow(self, flow: dict, exit_condition=None) -> None:
        """Wait until the person has entered the code (or it expires, or exit_condition() says stop)."""
        result = self.client.acquire_token_by_device_flow(
            flow, exit_condition=exit_condition or (lambda flow: False))
        if not result or not result.get("access_token"):
            detail = (result or {}).get("error_description") or (result or {}).get("error") or "Sign-in failed."
            raise NavigatorError(str(detail).split("\r\n", 1)[0][:400])

    def token(self) -> str:
        """Return a current Graph access token from the cache; never prompts."""
        result = self._silent(SCOPES)
        if result:
            return result["access_token"]
        raise NavigatorError("The Microsoft sign-in has expired. Close SharePoint Navigator and open it again to sign in.")

    def token_for(self, scopes: list[str], force_refresh: bool = False) -> str:
        """Get a SharePoint token silently from the Graph sign-in's refresh token.

        Never prompts; raises NavigatorError if no silent token is available (usually missing admin
        consent for SharePoint AllSites.Read). ``force_refresh`` skips the cached token after a 401.
        """
        result = None
        for account in self.client.get_accounts():
            result = self.client.acquire_token_silent(scopes, account=account, force_refresh=force_refresh)
            if result and result.get("access_token"):
                return result["access_token"]
        detail = (result or {}).get("error_description") or "no cached sign-in"
        raise NavigatorError(
            f"Could not get a SharePoint token for {scopes[0].rsplit('/', 1)[0]} without a new sign-in. "
            f"Check that the Entra app has admin-consented SharePoint delegated {scopes[0].rsplit('/', 1)[-1]}. "
            f"Details: {str(detail)[:400]}"
        )


# ---- SharePoint REST ----

class SharePointRestClient:
    """SharePoint REST calls (site list, StorageMetrics) that reuse the Graph sign-in.

    Each host (tenant and -admin) needs its own token, obtained silently via AuthSession.token_for.
    """

    def __init__(self, auth: AuthSession):
        """Keep the shared sign-in and a reusable HTTP session."""
        self.auth = auth
        self.session = requests.Session()

    @staticmethod
    def _scopes(url: str, write: bool = False) -> list[str]:
        """Return the URL host's delegated scope; refuse non-SharePoint hosts so the token never leaks.

        Reads ask for AllSites.Read; ``write`` asks for AllSites.FullControl, which starting or
        stopping a version trim needs.
        """
        host = (urlsplit(url).hostname or "").lower()
        if not host.endswith(".sharepoint.com"):
            raise NavigatorError(f"Not a SharePoint Online URL: {url}")
        return [f"https://{host}/{'AllSites.FullControl' if write else 'AllSites.Read'}"]

    def request(self, method: str, url: str, *, json_body=None, write: bool = False):
        """Send one SharePoint REST request (odata=nometadata) and return parsed JSON (``{}`` if empty).

        ``write`` uses the AllSites.FullControl token (see _scopes).

        429/503 are retried up to 5 times, honouring Retry-After (max 60 s) or else backing off from
        1 s, doubling to 30 s. 401 is retried once with a force-refreshed token. Other failures raise
        NavigatorError with SharePoint's message.
        """
        scopes = self._scopes(url, write)
        headers = {
            "Authorization": f"Bearer {self.auth.token_for(scopes)}",
            "Accept": "application/json;odata=nometadata",
            "User-Agent": USER_AGENT,
        }
        if json_body is not None:
            headers["Content-Type"] = "application/json;odata=nometadata"
        refreshed = False
        for attempt in range(6):
            response = self.session.request(method, url, headers=headers, json=json_body, timeout=HTTP_TIMEOUT)
            if response.status_code in (429, 503) and attempt < 5:
                retry_after = response.headers.get("Retry-After")
                delay = min(int(retry_after), 60) if retry_after and retry_after.isdigit() else min(2**attempt, 30)
                time.sleep(delay)
                continue
            if response.status_code == 401 and not refreshed:
                refreshed = True
                headers["Authorization"] = f"Bearer {self.auth.token_for(scopes, force_refresh=True)}"
                continue
            if not response.ok:
                # With odata=nometadata, errors arrive as {"odata.error": {"message": {"value": ...}}}.
                try:
                    error = response.json().get("odata.error", {})
                    message = (error.get("message") or {}).get("value") or response.text
                except Exception:
                    message = response.text
                raise NavigatorError(f"SharePoint returned HTTP {response.status_code}: {str(message)[:900]}")
            if response.status_code == 204 or not response.content:
                return {}
            return response.json()
        raise NavigatorError("SharePoint kept throttling the request. Try again later.")

    @staticmethod
    def _api_root(site_url: str) -> str:
        """Return the site's REST root, ``https://<host>/<encoded site path>/_api``."""
        parts = urlsplit(normalize_site_url(site_url))
        return f"https://{parts.netloc}{quote(parts.path, safe='/')}/_api"

    @staticmethod
    def _folder_literal(server_relative_path: str) -> str:
        """Encode a server-relative path for use inside ``decodedurl='...'``."""
        # OData string literal: double single quotes, then URL-encode (# and % included).
        return quote(server_relative_path.replace("'", "''"), safe="/")

    def folder_metric(self, site_url: str, server_relative_path: str) -> dict:
        """Return StorageMetrics for one folder (keys as in parse_storage_metric).

        GetFolderByServerRelativePath(decodedurl=...) is used because, unlike ...Url, it handles # and %.
        """
        url = (f"{self._api_root(site_url)}/web/GetFolderByServerRelativePath(decodedurl='"
               f"{self._folder_literal(server_relative_path)}')?$select=StorageMetrics&$expand=StorageMetrics")
        return parse_storage_metric(self.request("GET", url).get("StorageMetrics"))

    def subfolder_metrics(self, site_url: str, server_relative_path: str) -> dict[str, dict]:
        """Return Storage Metrics for every direct subfolder in one request, keyed by casefolded name."""
        url = (f"{self._api_root(site_url)}/web/GetFolderByServerRelativePath(decodedurl='"
               f"{self._folder_literal(server_relative_path)}')/Folders"
               "?$select=Name,StorageMetrics&$expand=StorageMetrics&$top=5000")
        return {
            str(folder.get("Name") or "").casefold(): parse_storage_metric(folder.get("StorageMetrics"))
            for folder in self.request("GET", url).get("value", [])
        }

    # -- Version trim (site level: covers every library in the site) --
    # These are the REST forms of the CSOM Site methods that New-SPOSiteFileVersionBatchDeleteJob and
    # Get-SPOSiteFileVersionBatchDeleteJobProgress call, so no PowerShell module is needed.

    def trim_progress(self, site_url: str) -> dict:
        """Return the site's latest version-trim job, parsed by parse_trim_progress.

        SharePoint answers with a JSON object encoded as a string; {"Status": "NoRequestFound"}
        means the site has never had one.
        """
        raw = self.request("POST", f"{self._api_root(site_url)}/site/GetProgressForDeleteFileVersions").get("value")
        try:
            data = json.loads(raw) if raw else {}
        except ValueError:
            data = {"Status": str(raw)}
        return parse_trim_progress(data if isinstance(data, dict) else {})

    def version_policy_progress(self, site_url: str) -> dict:
        """Return the site's latest version-policy job (parse_policy_progress).

        Setting a site's version limits for all its libraries (Set-SPOSite -EnableAutoExpirationVersionTrim
        and similar, or the admin center) runs as this separate job, and it can trim versions too.
        """
        raw = self.request("POST", f"{self._api_root(site_url)}/site/GetProgressForSetVersionPolicyForDocLibs").get("value")
        try:
            data = json.loads(raw) if raw else {}
        except ValueError:
            data = {"Status": str(raw)}
        return parse_policy_progress(data if isinstance(data, dict) else {})

    def site_collection_url(self, site_url: str) -> str:
        """Return the URL of the site collection that ``site_url`` belongs to.

        ``/_api/site`` always means the whole site collection, so for a subsite this is its parent.
        """
        return normalize_site_url(str(self.request("GET", f"{self._api_root(site_url)}/site?$select=Url").get("Url") or ""))

    def start_trim(self, site_url: str, parameters: dict) -> None:
        """Queue a permanent version-trim job for every library in the site (see trim_parameters)."""
        self.request("POST", f"{self._api_root(site_url)}/site/StartDeleteFileVersionsByMode",
                     json_body={"batchDeleteParameters": parameters}, write=True)

    def cancel_trim(self, site_url: str) -> None:
        """Stop the site's queued or running trim job. Versions already deleted stay deleted."""
        self.request("POST", f"{self._api_root(site_url)}/site/CancelDeleteFileVersions", write=True)


def parse_storage_metric(value) -> dict:
    """Convert SharePoint StorageMetrics into the page's dict; missing or negative numbers become 0.

    totalSize is TotalSize ("Storage used", includes old versions); totalFileStreamSize is
    TotalFileStreamSize ("Size", current content); lastModified is passed through.
    """
    metric = value or {}
    return {
        "totalSize": max(0, int(metric.get("TotalSize") or 0)),
        "totalFileStreamSize": max(0, int(metric.get("TotalFileStreamSize") or 0)),
        "totalFileCount": max(0, int(metric.get("TotalFileCount") or 0)),
        "lastModified": metric.get("LastModified"),
    }


# ---- Version trim helpers ----

# SharePoint's FileVersionBatchDeleteMode values (read from the official CSOM library, since the
# REST parameter is a plain Int32): 0 older-than-days, 1 count limits, 2 automatic.
TRIM_MODES = {"days": 0, "count": 1, "automatic": 2}
# Guard rails for the rule values. 30 days is the floor the earlier PowerShell script used.
TRIM_MIN_DAYS, TRIM_MAX_DAYS = 30, 36500
TRIM_MAX_VERSIONS = 50000
# Job states after which nothing is left to stop; anything else counts as queued or running.
TRIM_FINISHED_PREFIXES = ("norequestfound", "complete", "fail", "cancel")


def trim_parameters(payload: dict) -> tuple[dict, str]:
    """Validate the page's trim rule and return (SharePoint parameters, plain description).

    Values a rule doesn't use are -1, as SharePoint's own tools send them. SyncListPolicy stays
    false so the libraries' version settings are left as they are; only existing versions change.
    Raises NavigatorError for an unknown rule or an out-of-range number.
    """
    mode = str(payload.get("mode") or "").strip().lower()
    if mode not in TRIM_MODES:
        raise NavigatorError("Choose a trim rule: Automatic, older than a number of days, or a version count.")

    def whole(name: str, low: int, high: int) -> int:
        """Read one whole-number field and check it is within [low, high]."""
        try:
            value = int(str(payload.get(name)).strip())
        except (TypeError, ValueError):
            raise NavigatorError(f"Enter a whole number from {low} to {high}.") from None
        if not low <= value <= high:
            raise NavigatorError(f"Enter a whole number from {low} to {high}.")
        return value

    days = major = minor = -1
    if mode == "days":
        days = whole("days", TRIM_MIN_DAYS, TRIM_MAX_DAYS)
        description = f"delete versions older than {days} days"
    elif mode == "count":
        major = whole("majorVersions", 1, TRIM_MAX_VERSIONS)
        minor = whole("minorVersions", 0, major)
        description = f"keep at most {major} versions per file (minor versions kept for the newest {minor})"
    else:
        description = "automatic"
    parameters = {
        "BatchDeleteMode": TRIM_MODES[mode],
        "DeleteOlderThanDays": days,
        "MajorVersionLimit": major,
        "MajorWithMinorVersionsLimit": minor,
        "SyncListPolicy": False,
        "BypassSiteLock": False,
    }
    return parameters, description


# How SharePoint names each mode in its progress report, by mode number.
TRIM_MODE_NAMES = {0: "DeleteOlderThanDays", 1: "CountLimits", 2: "AutomaticTrim"}


def trim_matches(job: dict, parameters: dict) -> bool:
    """True if a job SharePoint reports has the rule that was sent (mode and its numbers).

    For older-than-days, SharePoint stores a cutoff date (request time minus the days), so the
    difference is compared with a day of slack for rounding.
    """
    mode = parameters["BatchDeleteMode"]
    if job.get("mode") != TRIM_MODE_NAMES.get(mode):
        return False
    if mode == TRIM_MODES["days"]:
        try:
            requested = datetime.fromisoformat(str(job.get("requested")).replace("Z", "+00:00"))
            cutoff = datetime.fromisoformat(str(job.get("deleteOlderThan")).replace("Z", "+00:00"))
        except ValueError:
            return False
        return abs((requested - cutoff).total_seconds() / 86400 - parameters["DeleteOlderThanDays"]) <= 1
    if mode == TRIM_MODES["count"]:
        return (job.get("majorVersionLimit") == parameters["MajorVersionLimit"]
                and job.get("majorWithMinorVersionsLimit") == parameters["MajorWithMinorVersionsLimit"])
    return True


def trim_time(value) -> str | None:
    """Turn SharePoint's "MM/DD/YYYY HH:MM:SS" UTC text into ISO 8601 (Z); None if blank or year 1."""
    try:
        parsed = datetime.strptime(str(value or "").strip(), "%m/%d/%Y %H:%M:%S")
    except ValueError:
        return None
    return None if parsed.year < 2000 else parsed.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def parse_policy_progress(data: dict) -> dict:
    """Convert a version-policy job report into the page's dict (state and times only).

    Uses the same state names and running rule as parse_trim_progress.
    """
    status = str(data.get("Status") or "NoRequestFound").strip()
    return {
        "status": status,
        "exists": status.lower() != "norequestfound",
        "running": not status.lower().startswith(TRIM_FINISHED_PREFIXES),
        "requested": trim_time(data.get("RequestTimeInUTC")),
        "completed": trim_time(data.get("CompleteTimeInUTC")),
        "error": str(data.get("ErrorMessage") or ""),
    }


def parse_trim_progress(data: dict) -> dict:
    """Convert SharePoint's trim progress (all values are strings) into the page's dict.

    ``status`` is SharePoint's raw state (NoRequestFound, New, InProgress, CompleteSuccess, ...);
    ``running`` is true while a job can still be stopped. Numbers default to 0 and times to None.
    """
    def number(key: str) -> int:
        """Read one counter; blanks and junk become 0, negatives (unused limits) become -1."""
        try:
            return max(-1, int(str(data.get(key) or "0").strip()))
        except ValueError:
            return 0

    status = str(data.get("Status") or "NoRequestFound").strip()
    return {
        "status": status,
        "workItemId": str(data.get("WorkItemId") or ""),
        "exists": status.lower() != "norequestfound",
        "running": not status.lower().startswith(TRIM_FINISHED_PREFIXES),
        "mode": str(data.get("BatchDeleteMode") or ""),
        "deleteOlderThan": trim_time(data.get("DeleteOlderThan")),
        "majorVersionLimit": number("MajorVersionLimit"),
        "majorWithMinorVersionsLimit": number("MajorWithMinorVersionsLimit"),
        "requested": trim_time(data.get("RequestTimeInUTC")),
        "lastProcessed": trim_time(data.get("LastProcessTimeInUTC")),
        "completed": trim_time(data.get("CompleteTimeInUTC")),
        "librariesProcessed": number("ListsProcessed"),
        "filesProcessed": number("FilesProcessed"),
        "versionsProcessed": number("VersionsProcessed"),
        "versionsDeleted": number("VersionsDeleted"),
        "versionsFailed": number("VersionsFailed"),
        "storageReleasedBytes": number("StorageReleased"),
        "error": str(data.get("ErrorMessage") or ""),
    }


# ---- Microsoft Graph ----

class GraphClient:
    """Thin Microsoft Graph v1.0 client with throttling retries and paging."""

    def __init__(self, auth: AuthSession):
        """Keep the shared sign-in and a reusable HTTP session."""
        self.auth = auth
        self.session = requests.Session()

    def request(self, method: str, url_or_path: str, *, json_body=None, headers=None,
                return_response: bool = False):
        """Send one Graph request (path below GRAPH_ROOT or full URL) and return parsed JSON.

        ``return_response`` returns the raw Response (copy needs its 202 status). 429/503/504 are
        retried up to 5 times, honouring Retry-After (max 60 s) or else backing off from 1 s,
        doubling to 30 s. 401 is retried once with a fresh token. Failures raise NavigatorError.
        """
        url = url_or_path if url_or_path.startswith("https://") else GRAPH_ROOT + url_or_path
        request_headers = {"Authorization": f"Bearer {self.auth.token()}", "Accept": "application/json"}
        if json_body is not None:
            request_headers["Content-Type"] = "application/json"
        if headers:
            request_headers.update(headers)
        for attempt in range(6):
            response = self.session.request(
                method, url, headers=request_headers, json=json_body, timeout=HTTP_TIMEOUT
            )
            if response.status_code in (429, 503, 504) and attempt < 5:
                retry_after = response.headers.get("Retry-After")
                delay = min(int(retry_after), 60) if retry_after and retry_after.isdigit() else min(2**attempt, 30)
                time.sleep(delay)
                continue
            if response.status_code == 401:
                request_headers["Authorization"] = f"Bearer {self.auth.token()}"
                response = self.session.request(
                    method, url, headers=request_headers, json=json_body, timeout=HTTP_TIMEOUT
                )
            if not response.ok:
                try:
                    error = response.json().get("error", {})
                    message = error.get("message") or response.text
                except Exception:
                    message = response.text
                raise NavigatorError(f"Microsoft Graph returned HTTP {response.status_code}: {message[:900]}")
            if return_response:
                return response
            if response.status_code == 204 or not response.content:
                return {}
            return response.json()
        raise NavigatorError("Microsoft Graph kept throttling the request. Try again later.")

    def get(self, path: str):
        """GET a Graph path or full URL and return the parsed JSON."""
        return self.request("GET", path)

    def pages(self, path: str):
        """Yield every item of a collection across all pages (sites, drives; not folder views)."""
        next_url = path
        while next_url:
            page = self.get(next_url)
            yield from page.get("value", [])
            next_url = page.get("@odata.nextLink")

    def patch(self, path: str, body: dict, etag: str | None = None):
        """PATCH a Graph item, optionally guarded by its eTag.

        With ``etag``, If-Match makes Graph refuse (HTTP 412) if the item changed since it was read.
        """
        headers = {"If-Match": etag} if etag else None
        return self.request("PATCH", path, json_body=body, headers=headers)


# ---- Site discovery ----

def site_from_admin_record(record: dict):
    """Turn an admin-API record into ``{"url", "title"}``, or None for OneDrive or skipped templates."""
    url = str(record.get("Url") or "").strip()
    template = str(record.get("Template") or "").lower()
    if not url or "-my.sharepoint.com" in url.lower() or template.startswith(SKIPPED_SITE_TEMPLATES):
        return None
    try:
        normalized = normalize_site_url(url)
    except NavigatorError:
        return None
    title = str(record.get("Title") or "").strip()
    return {"url": normalized, "title": title or urlsplit(normalized).path.rsplit("/", 1)[-1] or normalized}


def discover_sites(tenant: str, sharepoint: SharePointRestClient, graph: GraphClient):
    """Return (sites, source) from the SharePoint admin site list, else Graph search.

    Sites are ``{"url", "title"}``, de-duplicated and sorted by URL. The admin API needs the
    SharePoint Administrator role; Graph search depends on the search index and can miss sites.
    Raises NavigatorError if neither finds any.
    """
    admin_api = (f"https://{tenant}-admin.sharepoint.com/_api/Microsoft.Online.SharePoint."
                 "TenantAdministration.Tenant/GetSitePropertiesFromSharePointByFilters")
    found: dict[str, dict] = {}
    # IncludePersonalSite=0 leaves out OneDrive sites.
    try:
        records = sharepoint.request(
            "POST", admin_api, json_body={"speFilter": {"IncludePersonalSite": 0, "IncludeDetail": False}}
        ).get("value", [])
        for record in records:
            site = site_from_admin_record(record)
            if site:
                found.setdefault(site["url"].lower(), site)
        # No continuation marker, so truncation shows only through the result size.
        if len(records) >= ADMIN_SITE_BATCH_WARNING:
            print(f"Warning: the admin site list returned {len(records)} entries, which may be one batch of a "
                  "larger tenant. Some sites could be missing.", flush=True)
        if found:
            return sorted(found.values(), key=lambda s: s["url"].lower()), "SharePoint admin site list"
        print("Warning: the SharePoint admin site list returned no usable sites.", flush=True)
    except (NavigatorError, requests.RequestException) as exc:
        print(f"SharePoint admin site list unavailable ({exc}).", flush=True)
    # Fallback: Graph search, whose results also include OneDrive and /contentstorage/ entries.
    print("Falling back to Microsoft Graph site search. It lists only sites your account can find, "
          "so some sites may be missing. The SharePoint Administrator role gives the full list.", flush=True)
    for item in graph.pages("/sites?search=*&$select=webUrl,displayName&$top=200"):
        url = str(item.get("webUrl") or "")
        if not url or "-my.sharepoint.com" in url.lower() or "/contentstorage/" in url.lower():
            continue
        try:
            normalized = normalize_site_url(url)
        except NavigatorError:
            continue
        found.setdefault(normalized.lower(), {"url": normalized, "title": item.get("displayName") or normalized})
    if not found:
        raise NavigatorError("No SharePoint sites were found. Check the Entra app permissions and your site access.")
    return sorted(found.values(), key=lambda s: s["url"].lower()), "Microsoft Graph site search (may be incomplete)"


# ---- Inventory (sites, libraries, folders) ----

def site_graph_path(site_url: str) -> str:
    """Return the Graph path for a site, e.g. ``/sites/contoso.sharepoint.com:/sites/Finance``."""
    parts = urlsplit(site_url)
    encoded_path = quote(parts.path.strip("/"), safe="/")
    return f"/sites/{parts.netloc}:/{encoded_path}" if encoded_path else f"/sites/{parts.netloc}:/"


def folder_children(graph: GraphClient, drive_id: str, item_id: str):
    """Yield all direct children of a folder across pages (used only by Inventory.stats)."""
    return graph.pages(f"/drives/{quote(drive_id, safe='')}/items/{quote(item_id, safe='')}/children?$top=200")


def drive_root(graph: GraphClient, drive_id: str):
    """Return a drive's root folder item."""
    return graph.get(f"/drives/{quote(drive_id, safe='')}/root?$select=id,name,webUrl,folder,size,eTag,cTag,lastModifiedDateTime")


def item_path_from_url(item: dict, fallback: str) -> str:
    """Decoded server-relative path from an item's webUrl, or `fallback`.

    For Office documents (Word, Excel, PowerPoint) Graph's webUrl is a viewer link,
    /_layouts/15/Doc.aspx?sourcedoc=..., not the file's own path, so it can't be used.
    """
    path = server_path(item["webUrl"]) if item.get("webUrl") else ""
    return fallback if not path or "/_layouts/" in path.lower() else path


def item_web_path(item: dict, parent_path: str) -> str:
    """Decoded server-relative path of a child item: its parent's path plus its name.

    Built from the name rather than webUrl, which for Office documents is a viewer link
    (that bug showed every Excel/Word/PowerPoint file as "Doc.aspx").
    """
    name = item.get("name")
    if name:
        return parent_path.rstrip("/") + "/" + name
    return item_path_from_url(item, parent_path)


# ---- Search (Microsoft Search API, POST /search/query) ----
# One request searches every site's libraries through SharePoint's search index; it never walks
# folders. Results are trimmed to what the signed-in user can open.

# Results per request ("Load more" asks for the next block).
SEARCH_PAGE_SIZE = 50
# Graph refuses very deep paging; stop offering "Load more" past this many results.
SEARCH_MAX_FROM = 1000
# Type filter -> KQL. Folders are found by IsContainer: a folder hit still carries a "file" facet.
SEARCH_TYPES = {
    "all": "",
    "folders": "IsContainer:true",
    "files": "IsContainer:false",
    "office": "(filetype:docx OR filetype:doc OR filetype:xlsx OR filetype:xls OR filetype:xlsm "
              "OR filetype:csv OR filetype:pptx OR filetype:ppt)",
    "pdf": "filetype:pdf",
    "images": "(filetype:jpg OR filetype:jpeg OR filetype:png OR filetype:gif OR filetype:heic "
              "OR filetype:bmp OR filetype:tif OR filetype:tiff OR filetype:svg)",
    "video": "(filetype:mp4 OR filetype:mov OR filetype:avi OR filetype:wmv OR filetype:mkv "
             "OR filetype:m4v OR filetype:webm OR filetype:mp3 OR filetype:wav OR filetype:m4a)",
    "archives": "(filetype:zip OR filetype:7z OR filetype:rar OR filetype:tar OR filetype:gz OR filetype:tgz)",
}
# Size filter -> minimum bytes.
SEARCH_SIZES = {"any": 0, "10mb": 10 * 1024**2, "100mb": 100 * 1024**2, "1gb": 1024**3}
# Modified filter -> (comparison, days back).
SEARCH_MODIFIED = {"any": None, "30d": (">=", 30), "1y": ("<", 365), "3y": ("<", 3 * 365)}
# Sort choice -> Graph sortProperties (relevance sends none).
SEARCH_SORTS = {
    "relevance": [],
    "size": [{"name": "Size", "isDescending": True}],
    "newest": [{"name": "LastModifiedTime", "isDescending": True}],
    "oldest": [{"name": "LastModifiedTime", "isDescending": False}],
}
# Fields asked for on every hit. Asking for fields replaces the default set, so name, webUrl, size
# and date are listed too; the managed properties come back under resource.listItem.fields.
SEARCH_FIELDS = ["name", "webUrl", "size", "lastModifiedDateTime", "IsContainer", "SPWebUrl", "SiteTitle", "FileType"]


def search_choice(table: dict, value, what: str):
    """Look up a filter or sort choice from the page; an unknown value is refused, not ignored."""
    key = str(value or next(iter(table))).strip().lower()
    if key not in table:
        raise NavigatorError(f"Unknown search {what}: {key}")
    return table[key]


def search_scope_kql(tenant: str, site_url: str | None) -> str:
    """KQL that keeps hits inside this tenant's SharePoint sites (OneDrive is a different host).

    A site scope ends in "/" so /sites/Alpha doesn't also match /sites/AlphaBeta. The tenant's home
    site has no path of its own, so it is "the host minus /sites/ and /teams/".
    """
    host = f"https://{tenant}.sharepoint.com"
    if not site_url:
        return f'path:"{host}/"'
    site = normalize_site_url(site_url)
    if urlsplit(site).path.strip("/"):
        return f'path:"{site}/"'
    return f'path:"{host}/" -path:"{host}/sites/" -path:"{host}/teams/"'


def search_kql(text: str, tenant: str, *, item_type="all", size="any", modified="any",
               site_url: str | None = None, today: date | None = None) -> str:
    """Build the KQL query string from the search box and filters.

    The typed text is passed through as KQL (wrapped in brackets), so terms like filetype:pdf also
    work. Text or at least one filter is required: a bare scope would list the whole tenant.
    """
    text = " ".join(str(text or "").split())[:300]
    parts = [f"({text})"] if text else []
    type_kql = search_choice(SEARCH_TYPES, item_type, "type")
    min_bytes = search_choice(SEARCH_SIZES, size, "size")
    age = search_choice(SEARCH_MODIFIED, modified, "date")
    if type_kql:
        parts.append(type_kql)
    if min_bytes:
        parts.append(f"Size>={min_bytes}")
    if age:
        operator, days = age
        cutoff = (today or date.today()) - timedelta(days=days)
        parts.append(f"LastModifiedTime{operator}{cutoff.isoformat()}")
    if not parts:
        raise NavigatorError("Type something to search for, or choose a filter.")
    return " ".join(parts + [search_scope_kql(tenant, site_url)])


def search_item_path(web_url: str) -> str:
    """Server-relative path of a search hit's webUrl.

    Search returns webUrl unencoded ("/Shared Documents/a b.docx"), so it is not parsed as a URL:
    a "#" in a name would be cut off as a fragment. It is decoded only if it looks encoded.
    """
    path = re.sub(r"^https://[^/]+", "", web_url) or "/"
    if " " not in path and re.search(r"%[0-9A-Fa-f]{2}", path):
        path = unquote(path)
    return path.rstrip("/") or "/"


def parse_search_hit(hit: dict, sites) -> dict | None:
    """Turn one search hit into a result row for the page, or None if it is unusable.

    ``siteUrl`` is the deepest loaded site containing the item (so a subsite wins over its parent),
    spelled as in the site list, so the page can find its library in the tree. ``inSiteList`` is
    False when the hit's site isn't one the app loaded.
    """
    resource = hit.get("resource") or {}
    fields = {str(k).lower(): v for k, v in ((resource.get("listItem") or {}).get("fields") or {}).items()}
    web_url = str(resource.get("webUrl") or "")
    if not web_url.startswith("https://"):
        return None
    item_path = search_item_path(web_url)
    host = urlsplit(web_url.split("#", 1)[0]).netloc.lower()
    best = None
    for site in sites:
        parts = urlsplit(site["url"])
        site_path = unquote(parts.path).rstrip("/")
        if parts.netloc.lower() != host:
            continue
        if site_path and not item_path.lower().startswith(site_path.lower() + "/"):
            continue
        if best is None or len(site_path) > len(best[1]):
            best = (site, site_path)
    is_folder = str(fields.get("iscontainer", "")).lower() == "true"
    name = str(resource.get("name") or item_path.rsplit("/", 1)[-1])
    return {
        "name": name,
        "isFolder": is_folder,
        "itemPath": item_path,
        "webUrl": web_url,
        "siteUrl": best[0]["url"] if best else str(fields.get("spweburl") or ""),
        "siteTitle": (best[0].get("title") if best else "") or str(fields.get("sitetitle") or ""),
        "inSiteList": best is not None,
        # A folder's size in the search index is 0, so it is left out rather than shown as 0 B.
        "sizeBytes": None if is_folder else int(resource.get("size") or fields.get("size") or 0),
        "lastModified": str(resource.get("lastModifiedDateTime") or ""),
        "fileType": str(fields.get("filetype") or ""),
    }


def run_search(graph: "GraphClient", tenant: str, sites, payload: dict, allowed_sites: set[str]) -> dict:
    """Run one search request for the page and return {rows, total, moreAvailable, nextFrom}.

    Read-only: one POST /search/query. ``siteUrl`` (optional) limits it to one loaded site.
    """
    site_url = str(payload.get("siteUrl") or "").strip() or None
    if site_url and normalize_site_url(site_url).lower() not in allowed_sites:
        raise NavigatorError("The selected site is not in this tenant's loaded site list.")
    try:
        start = max(0, int(payload.get("from") or 0))
    except (TypeError, ValueError):
        start = 0
    if start >= SEARCH_MAX_FROM:
        raise NavigatorError(f"Only the first {SEARCH_MAX_FROM:,} results can be shown. Narrow the search.")
    kql = search_kql(str(payload.get("query") or ""), tenant, item_type=payload.get("type"),
                     size=payload.get("size"), modified=payload.get("modified"), site_url=site_url)
    request = {"entityTypes": ["driveItem"], "query": {"queryString": kql}, "from": start,
               "size": SEARCH_PAGE_SIZE, "fields": SEARCH_FIELDS}
    sort = search_choice(SEARCH_SORTS, payload.get("sort"), "order")
    if sort:
        request["sortProperties"] = sort
    response = graph.request("POST", "/search/query", json_body={"requests": [request]})
    containers = [c for answer in response.get("value", []) for c in answer.get("hitsContainers", [])]
    hits = [hit for container in containers for hit in container.get("hits", [])]
    rows = [row for row in (parse_search_hit(hit, sites) for hit in hits) if row]
    total = sum(int(c.get("total") or 0) for c in containers)
    more = any(c.get("moreResultsAvailable") for c in containers)
    next_from = start + len(hits)
    return {"rows": rows, "total": total, "moreAvailable": bool(more and hits and next_from < SEARCH_MAX_FROM),
            "nextFrom": next_from}


class Inventory:
    """Graph view of sites, libraries and folder contents; site and drive lookups are cached."""

    def __init__(self, graph: GraphClient, tenant: str, sites):
        """Keep the Graph client, tenant name and discovered site list."""
        self.graph = graph
        self.tenant = tenant
        self.sites = sites
        # Both caches are keyed by the normalized, lower-cased site URL.
        self._site_cache: dict[str, dict] = {}
        self._drive_cache: dict[str, list[dict]] = {}

    def resolve_site(self, site_url: str):
        """Return the Graph site object (id, displayName, webUrl) for a site URL, cached."""
        normalized = normalize_site_url(site_url)
        key = normalized.lower()
        if key not in self._site_cache:
            site = self.graph.get(site_graph_path(normalized) + "?$select=id,displayName,webUrl")
            self._site_cache[key] = site
        return self._site_cache[key]

    def drives_for_site(self, site_url: str):
        """Return all drives (libraries) of a site, cached. Commas in the site id stay unencoded."""
        key = normalize_site_url(site_url).lower()
        if key not in self._drive_cache:
            site = self.resolve_site(site_url)
            self._drive_cache[key] = list(
                self.graph.pages(f"/sites/{quote(site['id'], safe=',')}/drives?$select=id,name,webUrl,driveType")
            )
        return self._drive_cache[key]

    def drive_for_item(self, site_url: str, item_path: str):
        """Return (drive, relative path) for an item path; the longest matching library root wins."""
        target = item_path.rstrip("/").lower()
        candidates = []
        for drive in self.drives_for_site(site_url):
            root = server_path(drive.get("webUrl", "")).lower()
            if root and (target == root or target.startswith(root + "/")):
                candidates.append((len(root), drive, root))
        if not candidates:
            raise NavigatorError("Could not map this item path to a document library in Graph.")
        _, drive, root_path = max(candidates, key=lambda item: item[0])
        relative = unquote(item_path).rstrip("/")[len(root_path):].strip("/")
        return drive, relative

    def name_taken(self, site_url: str, item_path: str, new_name: str) -> bool:
        """True if the item's folder already holds something named new_name (used by inspect and rename).

        Asks Graph for the would-be path: found means taken, HTTP 404 means free, and any other
        error is raised, so a rename never goes ahead on a failed check.
        """
        drive, relative = self.drive_for_item(site_url, item_path)
        parent = relative.rsplit("/", 1)[0] if "/" in relative else ""
        candidate = f"{parent}/{new_name}".strip("/")
        try:
            self.graph.get(f"/drives/{quote(drive['id'], safe='')}/root:/{graph_path(candidate)}?$select=id,name")
        except NavigatorError as exc:
            if "HTTP 404" in str(exc):
                return False
            raise
        return True

    def get_item_by_path(self, site_url: str, item_path: str):
        """Return (drive, item) for a server-relative path; item includes eTag/cTag and parentReference."""
        drive, relative = self.drive_for_item(site_url, item_path)
        drive_id = quote(drive["id"], safe="")
        if relative:
            path = f"/drives/{drive_id}/root:/{graph_path(relative)}"
        else:
            path = f"/drives/{drive_id}/root"
        item = self.graph.get(path + "?$select=id,name,size,webUrl,file,folder,eTag,cTag,lastModifiedDateTime,parentReference")
        return drive, item

    def stats(self, drive_id: str, item: dict, item_path: str, rows: list | None = None,
              site=None, library_name: str | None = None):
        """Recursively total current bytes and files; returns (size_bytes, file_count).

        One Graph call per folder page, so it is used only for the item being renamed. If ``rows``
        is a list, a row per file and folder is appended; "__library_root__" omits the start row.
        """
        if item.get("file") is not None:
            size = int(item.get("size") or 0)
            if rows is not None:
                rows.append(self.row(site, library_name, "File", item_path, size, 1, item.get("lastModifiedDateTime")))
            return size, 1
        total_size = 0
        file_count = 0
        if item.get("folder") is not None:
            for child in folder_children(self.graph, drive_id, item["id"]):
                child_path = item_web_path(child, item_path)
                size, count = self.stats(drive_id, child, child_path, rows, site, library_name)
                total_size += size
                file_count += count
        if rows is not None and item.get("folder") is not None and item_path != "__library_root__":
            rows.append(self.row(site, library_name, "Folder", item_path, total_size, file_count, item.get("lastModifiedDateTime")))
        return total_size, file_count

    @staticmethod
    def row(site, library, item_type, path, size, count, modified, has_children=False, child_count=0):
        """Build one row in the shape the page expects.

        The page sends ``path`` back to identify the item. Folder listings pass size 0 and set
        CurrentBytes separately.
        """
        return {
            "SiteTitle": site["title"], "SiteUrl": site["url"], "Library": library,
            "ItemType": item_type, "FolderPath": path,
            "SizeBytes": int(size), "SizeMB": round(int(size) / (1024 * 1024), 2),
            "FileCount": int(count), "LastModified": modified or "",
            "HasChildren": bool(has_children), "ChildCount": int(child_count or 0),
        }

    def children_page(self, site_url: str, folder_path: str, context=None, next_url=None):
        """Return (rows, next_url, context) for one page (up to 200) of a folder's direct children.

        The first call (``context`` None) resolves the folder and builds the context; later calls
        pass it back with the previous page's ``@odata.nextLink``.
        """
        if context is None:
            drive, parent = self.get_item_by_path(site_url, folder_path)
            if parent.get("folder") is None:
                raise NavigatorError("The selected SharePoint item is not a folder.")
            site_data = self.resolve_site(site_url)
            context = {
                "site": {"url": normalize_site_url(site_url), "title": site_data.get("displayName") or site_url},
                "library": drive.get("name") or "Documents",
                "childrenUrl": f"/drives/{quote(drive['id'], safe='')}/items/{quote(parent['id'], safe='')}/children?$top=200",
            }
            page_url = context["childrenUrl"]
        else:
            page_url = next_url
            # The link is sent with the Graph bearer token, so it must point at Graph.
            if not page_url or not page_url.startswith(GRAPH_ROOT + "/"):
                raise NavigatorError("The Graph continuation link is missing or invalid.")
        page = self.graph.get(page_url)
        site = context["site"]
        library = context["library"]
        rows = []
        for child in page.get("value", []):
            child_path = item_web_path(child, folder_path)
            is_folder = child.get("folder") is not None
            facet = child.get("folder") or {}
            child_count = int(facet.get("childCount") or 0)
            item_type = "Folder" if is_folder else "File"
            row = self.row(
                site, library, item_type, child_path,
                0 if is_folder else int(child.get("size") or 0),
                0 if is_folder else 1,
                child.get("lastModifiedDateTime"),
                has_children=is_folder,
                child_count=child_count,
            )
            if is_folder:
                # Graph's folder size equals Storage Metrics TotalFileStreamSize (current content).
                row["CurrentBytes"] = int(child.get("size") or 0)
            rows.append(row)
        return rows, page.get("@odata.nextLink"), context

    def scan(self, on_site_start=None, on_site_complete=None):
        """Load library roots (default library plus any named Documents/Shared Documents) of every site.

        Callbacks report per-site progress. Returns (rows, errors); failing sites are recorded and
        skipped. Raises NavigatorError only if no site produced a library.
        """
        rows = []
        errors = []
        for index, listed_site in enumerate(self.sites, 1):
            site_url = listed_site["url"]
            print(f"[{index}/{len(self.sites)}] Graph scan: {site_url}", flush=True)
            if on_site_start:
                on_site_start(index, site_url)
            site_rows = []
            site_error = None
            try:
                site_data = self.resolve_site(site_url)
                site = {"url": site_url, "title": site_data.get("displayName") or listed_site["title"]}
                # Fetch the default library explicitly: its name may be localized or customized.
                default_drive = self.graph.get(
                    f"/sites/{quote(site_data['id'], safe=',')}/drive?$select=id,name,webUrl,driveType"
                )
                selected_drives = {default_drive["id"]: default_drive}
                # Also keep extra libraries named Documents or Shared Documents.
                site_drives = self.drives_for_site(site_url)
                # Let drive_for_item map the default library even if the drives listing omitted it.
                if not any(drive.get("id") == default_drive.get("id") for drive in site_drives):
                    site_drives.insert(0, default_drive)
                    self._drive_cache[site_url.lower()] = site_drives
                for drive in site_drives:
                    name = (drive.get("name") or "").strip()
                    if drive.get("id") != default_drive.get("id") and name.lower() not in LIBRARY_NAMES:
                        continue
                    selected_drives[drive["id"]] = drive
                for drive in selected_drives.values():
                    name = (drive.get("name") or "Documents").strip()
                    root = drive_root(self.graph, drive["id"])
                    root_path = server_path(root.get("webUrl") or drive.get("webUrl", ""))
                    site_rows.append(self.row(
                        site, name, "Library root", root_path, 0, 0,
                        root.get("lastModifiedDateTime"), has_children=True,
                    ))
            except Exception as exc:
                message = f"{site_url}: {exc}"
                errors.append(message)
                site_error = str(exc)
                print("Warning: " + message, flush=True)
            rows.extend(site_rows)
            if on_site_complete:
                on_site_complete(index, site_url, site_rows, site_error)
        if not rows:
            raise NavigatorError("Graph returned no default Documents libraries. Check Graph permissions and your site access.")
        return rows, errors

    def snapshot(self, site_url: str, item_path: str):
        """Capture one item's live state (folders walked fully) for the rename preview and re-check.

        eTag changes with the item or its metadata, cTag with its content.
        """
        drive, item = self.get_item_by_path(site_url, item_path)
        resolved_path = item_path_from_url(item, item_path)
        if item.get("folder") is not None:
            size, count = self.stats(drive["id"], item, resolved_path)
            item_type = "folder"
        elif item.get("file") is not None:
            size, count, item_type = int(item.get("size") or 0), 1, "file"
        else:
            raise NavigatorError("The selected item is not a file or folder.")
        return {
            "siteUrl": normalize_site_url(site_url), "driveId": drive["id"], "itemId": item["id"],
            "itemType": item_type, "name": item.get("name", ""), "path": resolved_path,
            "sizeBytes": size, "fileCount": count,
            "modified": item.get("lastModifiedDateTime", ""), "etag": item.get("eTag", ""),
            "ctag": item.get("cTag", ""),
        }

    def snapshot_by_id(self, inspection: dict):
        """Re-snapshot an item by Graph id, so a move or rename shows up as a changed path."""
        drive_id = quote(inspection["driveId"], safe="")
        item_id = quote(inspection["itemId"], safe="")
        item = self.graph.get(
            f"/drives/{drive_id}/items/{item_id}?$select=id,name,size,webUrl,file,folder,eTag,cTag,lastModifiedDateTime,parentReference"
        )
        return self.snapshot(inspection["siteUrl"], item_path_from_url(item, inspection["path"]))


# ---- Tenant and client ID settings ----
# Where they come from, first match wins:
#   tenant:    command line, SHAREPOINT_NAVIGATOR_TENANT, the only <tenant>_clientid.txt beside the
#              app, the tenant saved last time.
#   client ID: <tenant>_clientid.txt beside the app (an admin can ship it with the app, so staff are
#              never asked), else the ID saved for that tenant.
# Anything missing is asked on the page's setup screen (/api/setup), which saves it. --setup, or
# "Change organisation" on the page, shows that screen again.

GUID_PATTERN = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"


def load_settings() -> dict:
    """Return the saved settings ({"tenant", "clientIds": {tenant: id}}), or {} if none or unreadable."""
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_settings(tenant: str, client_id: str | None = None) -> None:
    """Remember the tenant (and its client ID) for next time; readable by this user only."""
    data = load_settings()
    data["tenant"] = tenant
    if client_id:
        ids = data.get("clientIds") if isinstance(data.get("clientIds"), dict) else {}
        ids[tenant] = client_id
        data["clientIds"] = ids
    USER_FOLDER.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        SETTINGS_FILE.chmod(0o600)
    except OSError:
        pass


def tenant_from_input(value: str) -> str:
    """Accept "contoso", "contoso.sharepoint.com" or a full SharePoint URL; return "contoso"."""
    value = value.strip().lower()
    if "://" in value:
        value = urlsplit(value).hostname or ""
    value = value.split("/", 1)[0].removesuffix(".sharepoint.com").removesuffix("-admin")
    # The tenant ends up in URLs and file names, so only a plain DNS label is accepted.
    if not re.fullmatch(TENANT_PATTERN, value):
        raise NavigatorError("Enter only the tenant name before .sharepoint.com, for example contoso.")
    return value


def client_id_from_file(tenant: str) -> str | None:
    """The client ID in ``<tenant>_clientid.txt`` beside the app, or None (utf-8-sig tolerates a BOM)."""
    path = APP_ROOT / f"{tenant}_clientid.txt"
    if not path.is_file():
        return None
    client_id = path.read_text(encoding="utf-8-sig").strip()
    if not re.fullmatch(GUID_PATTERN, client_id):
        raise NavigatorError(f"{path.name} must contain the Entra Application (client) ID GUID on one line.")
    return client_id


def known_client_id(tenant: str) -> str | None:
    """The tenant's client ID from the file beside the app or the saved settings, or None."""
    from_file = client_id_from_file(tenant)
    if from_file:
        return from_file
    saved = (load_settings().get("clientIds") or {}).get(tenant)
    return str(saved) if saved and re.fullmatch(GUID_PATTERN, str(saved)) else None


def known_tenant(args: list[str]) -> str | None:
    """The tenant named on the command line or in the environment, by the only client ID file, or saved."""
    given = next((arg for arg in args if not arg.startswith("-")), "")
    given = given or os.environ.get("SHAREPOINT_NAVIGATOR_TENANT", "")
    if given.strip():
        return tenant_from_input(given)
    known = tenants_with_client_id()
    if len(known) == 1:
        return known[0]
    saved = str(load_settings().get("tenant") or "")
    try:
        return tenant_from_input(saved) if saved else None
    except NavigatorError:
        return None


def site_relative_folder(site_url: str, folder_path: str) -> str:
    """Validate a folder path from the browser and return it site-relative, with backslashes.

    The result (e.g. "Shared Documents\\Finance") is also a cache key. The path must be inside the
    site, name at least a library, and contain no "." or ".." segments or line breaks.
    """
    site_path = unquote(urlsplit(normalize_site_url(site_url)).path).rstrip("/")
    raw_path = urlsplit(folder_path).path if "://" in folder_path else folder_path
    item_path = unquote(raw_path).rstrip("/")
    if not item_path.startswith("/"):
        item_path = "/" + item_path
    if site_path:
        if item_path == site_path:
            relative = ""
        elif item_path.startswith(site_path + "/"):
            relative = item_path[len(site_path) + 1:]
        else:
            raise NavigatorError("The selected folder is outside its SharePoint site.")
    else:
        # The tenant root site has an empty path, so everything below "/" is site-relative.
        relative = item_path.lstrip("/")
    parts = [part for part in relative.split("/") if part]
    if not parts or any(part in (".", "..") or "\r" in part or "\n" in part for part in parts):
        raise NavigatorError("The selected path is not a valid library or folder path.")
    return "\\".join(parts)


def server_relative_folder(site_url: str, folder_path: str) -> str:
    """Return the validated, decoded server-relative folder path (chr(92) is a backslash)."""
    site_path = unquote(urlsplit(normalize_site_url(site_url)).path).rstrip("/")
    return f"{site_path}/{site_relative_folder(site_url, folder_path).replace(chr(92), '/')}"


# ---- Local web service ----

def _safe_known_client_id(tenant: str) -> str | None:
    """known_client_id that treats a bad tenant name or unreadable file as unknown."""
    try:
        return known_client_id(tenant_from_input(tenant))
    except NavigatorError:
        return None


def run_server(port: int, tenant: str | None = None, client_id: str | None = None,
               force_setup: bool = False, open_browser: bool = True):
    """Serve the page and API on 127.0.0.1 at once, then set up and sign in in the background.

    Stages, shown by the page from /api/status: "setup" (tenant or client ID unknown, or
    force_setup) → "connecting" → "code" (the person signs in with a device code) → "connecting"
    (finding sites) → "ready"; or "error". Routes that need SharePoint answer 409 until "ready".
    All shared state lives in this scope, captured by the nested functions and Handler. Returns
    after Ctrl+C, POST /api/stop or auto-stop.
    """
    # ---- Connection: filled in by connect() once signed in ----
    tenant = (tenant or "").lower() or None
    auth = graph = sharepoint = inventory = None
    sites: list[dict] = []
    site_source = ""
    # Requests may only touch sites from the discovered list, whatever the browser sends.
    allowed_sites: set[str] = set()
    # What the page shows while not ready. "generation" goes up on every new connect or setup, so a
    # sign-in still waiting from before (e.g. after "Change organisation") stops and is ignored.
    connect_lock = threading.Lock()
    connect_state = {"phase": "setup", "generation": 0, "code": "", "verificationUri": "",
                     "expiresAt": 0.0, "error": "", "step": ""}

    # ---- Shared state ----
    # Per-run secret injected into the page; every API call must present it.
    token = secrets.token_urlsafe(32)
    # Rename previews awaiting confirmation, keyed by inspection id (see /api/inspect).
    pending: dict[str, dict] = {}
    pending_lock = threading.Lock()
    # Delete previews awaiting confirmation, keyed by id (see /api/delete-inspect). Kept apart from
    # rename previews so one can never be used as the other. Guarded by pending_lock too.
    pending_deletes: dict[str, dict] = {}
    try:
        delete_wait = max(0.0, float(os.environ.get("SHAREPOINT_NAVIGATOR_DELETE_WAIT", DELETE_WAIT_SECONDS)))
    except ValueError:
        delete_wait = float(DELETE_WAIT_SECONDS)
    # Storage Metrics per folder, keyed "<site url lower>|<site-relative path casefolded>".
    storage_metric_cache: dict[str, dict] = {}
    storage_metric_lock = threading.Lock()
    # Bounds bursts of concurrent REST lookups from the browser.
    storage_metric_slot = threading.Semaphore(4)
    # Pages of folder children, same key; each entry is {"pages": [...], "context": ...}.
    folder_children_cache: dict[str, dict] = {}
    folder_children_lock = threading.Lock()
    # Trim start and stop run one at a time, so a double click can't queue two jobs.
    trim_lock = threading.Lock()
    scan_lock = threading.Lock()

    # ---- Auto-stop ----
    auto_stop = os.environ.get("SHAREPOINT_NAVIGATOR_AUTO_STOP", "1").strip() != "0"
    try:
        grace_seconds = float(os.environ.get("SHAREPOINT_NAVIGATOR_AUTO_STOP_GRACE", AUTO_STOP_GRACE_SECONDS))
    except ValueError:
        grace_seconds = AUTO_STOP_GRACE_SECONDS
    session_lock = threading.Lock()
    session_state = {"open": 0, "timer": None}
    # Set once shutdown begins; also ends the keep-alive loops of open event streams.
    stopping = threading.Event()
    # Set once the server exists, so stop_service can reach it.
    server_holder: dict = {}

    def stop_service(reason: str):
        """Shut the server down once. shutdown() blocks until serve_forever returns, so use a thread."""
        if stopping.is_set():
            return
        stopping.set()
        print(reason, flush=True)
        threading.Thread(target=server_holder["server"].shutdown, daemon=True).start()

    def session_opened():
        """Count a newly connected tab and cancel any pending auto-stop timer (a refresh)."""
        with session_lock:
            session_state["open"] += 1
            if session_state["timer"] is not None:
                session_state["timer"].cancel()
                session_state["timer"] = None

    def session_closed():
        """Count a disconnected tab; when none remain, start the grace-period stop timer."""
        with session_lock:
            session_state["open"] = max(0, session_state["open"] - 1)
            if auto_stop and session_state["open"] == 0 and not stopping.is_set():
                def stop_if_still_closed():
                    """Timer callback: stop only if no tab reconnected during the grace period."""
                    with session_lock:
                        still_closed = session_state["open"] == 0
                    if still_closed:
                        stop_service("The browser tab was closed, so SharePoint Navigator is stopping.")
                timer = threading.Timer(grace_seconds, stop_if_still_closed)
                timer.daemon = True
                session_state["timer"] = timer
                timer.start()

    # ---- Setup and sign-in (background) ----

    def set_connect(generation: int, **values) -> bool:
        """Update the page-visible stage, unless a newer connect or setup has replaced this one."""
        with connect_lock:
            if generation != connect_state["generation"]:
                return False
            connect_state.update(values)
            return True

    def connect(new_tenant: str, new_client_id: str):
        """Sign in (reusing the saved sign-in, or with a device code the page shows), then find
        the sites, on a background thread. On success the routes switch to the new tenant."""
        with connect_lock:
            connect_state["generation"] += 1
            generation = connect_state["generation"]
            connect_state.update(phase="connecting", step="signin", code="", verificationUri="",
                                 expiresAt=0.0, error="")

        def worker():
            nonlocal tenant, auth, graph, sharepoint, inventory, sites, site_source, allowed_sites
            try:
                new_auth = AuthSession(new_tenant, new_client_id)
                if not new_auth.signed_in():
                    flow = new_auth.begin_device_flow()
                    print(f"Sign-in code for Microsoft: {flow['user_code']} at {flow.get('verification_uri')}", flush=True)
                    set_connect(generation, phase="code", code=flow["user_code"],
                                verificationUri=flow.get("verification_uri") or "https://microsoft.com/devicelogin",
                                expiresAt=time.time() + int(flow.get("expires_in") or 900))
                    # Stops waiting when the app stops or the page starts a different setup.
                    new_auth.complete_device_flow(flow, exit_condition=lambda flow: stopping.is_set()
                                                  or connect_state["generation"] != generation)
                    if connect_state["generation"] != generation:
                        return
                if not set_connect(generation, phase="connecting", step="sites"):
                    return
                new_graph = GraphClient(new_auth)
                new_sharepoint = SharePointRestClient(new_auth)
                found, source = discover_sites(new_tenant, new_sharepoint, new_graph)
                print(f"Found {len(found)} SharePoint sites from the {source}.", flush=True)
                with connect_lock:
                    if generation != connect_state["generation"]:
                        return
                    tenant, auth, graph, sharepoint = new_tenant, new_auth, new_graph, new_sharepoint
                    sites, site_source = found, source
                    inventory = Inventory(new_graph, new_tenant, found)
                    allowed_sites = {normalize_site_url(site["url"]).lower() for site in found}
                    connect_state.update(phase="ready", step="", code="", error="")
                # A new tenant starts with empty caches and no previews.
                with storage_metric_lock:
                    storage_metric_cache.clear()
                with folder_children_lock:
                    folder_children_cache.clear()
                with pending_lock:
                    pending.clear()
            except Exception as exc:
                print(f"Sign-in or site discovery failed: {exc}", flush=True)
                set_connect(generation, phase="error", error=str(exc), code="")

        threading.Thread(target=worker, daemon=True).start()

    def show_setup():
        """Back to the setup screen; any sign-in still waiting stops (its generation is now old)."""
        with connect_lock:
            connect_state["generation"] += 1
            connect_state.update(phase="setup", step="", code="", verificationUri="", expiresAt=0.0, error="")

    def status_payload() -> dict:
        """What /api/status returns: the stage, plus the tenant and sites once ready."""
        with connect_lock:
            state = dict(connect_state)
        ready = state["phase"] == "ready"
        suggested = tenant or str(load_settings().get("tenant") or "")
        return {
            "ok": True, "version": __version__, "phase": state["phase"], "step": state["step"],
            "connected": ready, "tenantId": tenant if ready else "",
            "siteCount": len(sites) if ready else 0, "siteSource": site_source if ready else "",
            "code": state["code"], "verificationUri": state["verificationUri"],
            "expiresIn": max(0, int(state["expiresAt"] - time.time())) if state["code"] else 0,
            "error": state["error"], "suggestedTenant": suggested,
            # The client ID question can be skipped when a file beside the app or the settings know it.
            "clientIdKnown": bool(suggested and _safe_known_client_id(suggested)),
        }

    # ---- Library scan (site and library roots only) ----
    # Read by /api/progress, written by the scan worker; always under scan_lock.
    scan_state = {
        "running": False, "status": "idle", "rows": [], "completedSites": 0,
        "totalSites": len(sites), "currentSite": "", "errors": [], "error": "",
    }

    def start_scan():
        """Start the library-root scan on a background thread, unless one is running.

        Clears both folder caches so "Reload libraries" shows fresh data; the page polls /api/progress.
        """
        with scan_lock:
            if scan_state["running"]:
                return
            scan_state.update({
                "running": True, "status": "scanning", "rows": [], "completedSites": 0,
                "totalSites": len(sites), "currentSite": "", "errors": [], "error": "",
            })
        with storage_metric_lock:
            storage_metric_cache.clear()
        with folder_children_lock:
            folder_children_cache.clear()

        def on_site_start(index, site_url):
            """Record which site is being scanned, for the progress display."""
            with scan_lock:
                scan_state["currentSite"] = site_url
                scan_state["completedSites"] = index - 1

        def on_site_complete(index, site_url, site_rows, error):
            """Publish a finished site's rows and any error for the next poll."""
            with scan_lock:
                scan_state["rows"].extend(site_rows)
                scan_state["completedSites"] = index
                scan_state["currentSite"] = site_url
                if error:
                    scan_state["errors"].append({"siteUrl": site_url, "message": error})

        def worker():
            """Run Inventory.scan and record the final status ("complete" or "error")."""
            try:
                rows, errors = inventory.scan(on_site_start, on_site_complete)
                with scan_lock:
                    scan_state["running"] = False
                    scan_state["status"] = "complete"
                    scan_state["currentSite"] = ""
                print(f"Graph scan finished: {len(rows):,} libraries; {len(errors)} site errors.", flush=True)
            except Exception as exc:
                with scan_lock:
                    scan_state["running"] = False
                    scan_state["status"] = "error"
                    scan_state["currentSite"] = ""
                    scan_state["error"] = str(exc)
                print(f"Graph scan failed: {exc}", flush=True)

        # Daemon thread, so an unfinished scan never keeps the process alive.
        threading.Thread(target=worker, name="SharePointGraphScan", daemon=True).start()

    # ---- Folder data: Storage Metrics and children, with caches ----

    def get_cached_storage_metric(site_url: str, folder_path: str) -> dict:
        """Return a folder's Storage Metrics from the cache or SharePoint REST.

        The lock is never held during the network call; at most 4 run at once, and the cache is
        re-checked after getting a slot in case another request fetched the same folder.
        """
        normalized_site = normalize_site_url(site_url)
        if normalized_site.lower() not in allowed_sites:
            raise NavigatorError("The selected site is not in this tenant's loaded site list.")
        relative_path = site_relative_folder(normalized_site, folder_path)
        cache_key = f"{normalized_site.lower()}|{relative_path.casefold()}"
        with storage_metric_lock:
            cached = storage_metric_cache.get(cache_key)
        if cached is not None:
            return cached
        with storage_metric_slot:
            with storage_metric_lock:
                cached = storage_metric_cache.get(cache_key)
            if cached is not None:
                return cached
            metric = sharepoint.folder_metric(normalized_site, server_relative_folder(normalized_site, folder_path))
            with storage_metric_lock:
                storage_metric_cache[cache_key] = metric
            return metric

    def attach_subfolder_metrics(site_url: str, folder_path: str, rows: list[dict]):
        """Attach "StorageMetric" to folder rows from one REST call, and cache each metric.

        Used only when the folder fits on one page. Rows match by casefolded name; on failure it
        logs and returns, and the page then asks per folder.
        """
        try:
            metrics = sharepoint.subfolder_metrics(site_url, server_relative_folder(site_url, folder_path))
        except Exception as exc:
            print(f"Subfolder Storage Metrics failed for {site_url} / {folder_path}: {exc}", flush=True)
            return
        for row in rows:
            if row["ItemType"] != "Folder":
                continue
            metric = metrics.get(row["FolderPath"].rstrip("/").rsplit("/", 1)[-1].casefold())
            if metric is None:
                continue
            row["StorageMetric"] = metric
            # Same key format as get_cached_storage_metric.
            key = f"{site_url.lower()}|{site_relative_folder(site_url, row['FolderPath']).casefold()}"
            with storage_metric_lock:
                storage_metric_cache[key] = metric

    def get_cached_folder_children(site_url: str, folder_path: str, load_more: bool = False,
                                  loaded_count: int = 0) -> dict:
        """Return one page of a folder's children, caching every page fetched.

        ``loaded_count`` (rows the page already shows) selects the next cached page, so reopening a
        folder replays the cache instead of calling Graph. The lock is held across Graph calls: this
        serializes listings but guarantees one fetch per page despite overlapping requests.
        """
        normalized_site = normalize_site_url(site_url)
        if normalized_site.lower() not in allowed_sites:
            raise NavigatorError("The selected site is not in this tenant's loaded site list.")
        relative_path = site_relative_folder(normalized_site, folder_path)
        cache_key = f"{normalized_site.lower()}|{relative_path.casefold()}"
        with folder_children_lock:
            cached = folder_children_cache.get(cache_key)
            # First visit: fetch page one; attach subfolder metrics only if it is the only page.
            if cached is None:
                rows, next_url, context = inventory.children_page(normalized_site, folder_path)
                if not next_url and any(row["ItemType"] == "Folder" for row in rows):
                    attach_subfolder_metrics(normalized_site, folder_path, rows)
                cached = {"pages": [], "context": context}
                folder_children_cache[cache_key] = cached
                cached["pages"].append({"rows": rows, "nextUrl": next_url})
            if not load_more:
                page = cached["pages"][0]
                return {
                    "rows": page["rows"], "nextPageAvailable": bool(page["nextUrl"]),
                    "loadedCount": len(page["rows"]),
                }

            # Load more within the cache: return the page starting right after the browser's rows.
            pages = cached["pages"]
            total_cached = sum(len(page["rows"]) for page in pages)
            if loaded_count < total_cached:
                cumulative = 0
                for index, page in enumerate(pages[:-1]):
                    cumulative += len(page["rows"])
                    if cumulative == loaded_count:
                        next_page = pages[index + 1]
                        return {
                            "rows": next_page["rows"], "nextPageAvailable": bool(next_page["nextUrl"]),
                            "loadedCount": loaded_count + len(next_page["rows"]),
                        }
                raise NavigatorError("The folder page position changed. Collapse and reopen the folder to reload it.")

            # "Load more" past the cached pages: fetch the next page from Graph and cache it.
            last_page = pages[-1]
            if not last_page["nextUrl"]:
                return {"rows": [], "nextPageAvailable": False, "loadedCount": total_cached}
            rows, next_url, _ = inventory.children_page(
                normalized_site, folder_path, cached["context"], last_page["nextUrl"]
            )
            next_page = {"rows": rows, "nextUrl": next_url}
            pages.append(next_page)
            return {
                "rows": rows,
                "nextPageAvailable": bool(next_url),
                "loadedCount": loaded_count + len(rows),
            }

    # ---- HTTP request handler ----

    class Handler(BaseHTTPRequestHandler):
        """Serves the page and JSON API, one instance per request on its own thread.

        GET / and /api/session-events check access themselves; other routes require authorized().
        Route errors become HTTP 400 ``{"ok": false, "error"}``.
        """

        server_version = "SharePointNavigatorGraph/1.0"

        def log_request(self, code="-", size="-"):
            """Print a request line only when it failed; successful requests stay quiet.

            Changes (copy, move, rename, delete, trim) print their own plain line instead, and failed size
            and folder lookups print their own details, so their request lines are skipped too.
            """
            try:
                failed = int(getattr(code, "value", code)) >= 400
            except (TypeError, ValueError):
                failed = False
            if not failed or self.path in ("/api/storage-metric", "/api/folder-children"):
                return
            # Strip the query string: it can carry the page token (session-events stream).
            print(f"HTTP {int(getattr(code, 'value', code))}: {self.command} {self.path.split('?', 1)[0]}", flush=True)

        def log_message(self, fmt, *args):
            """Print the server's own error messages (bad requests, dropped connections)."""
            print("HTTP: " + fmt % args, flush=True)

        def send_json(self, status, value):
            """Send ``value`` as a UTF-8 JSON response that the browser must not cache."""
            body = json.dumps(value, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def send_bytes(self, status, content_type, body, extra=None):
            """Send raw bytes with the given content type and optional extra headers."""
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def body_json(self):
            """Read and parse the JSON request body (empty means ``{}``), max 100 KB."""
            length = int(self.headers.get("Content-Length", "0"))
            if length > 100_000:
                raise NavigatorError("Request body is too large.")
            return json.loads(self.rfile.read(length) or b"{}")

        def stream_session_events(self):
            """Hold an event stream open while the tab is open; this drives auto-stop.

            EventSource can't send headers, so the token comes in the query string. ``retry: 2000``
            makes the browser reconnect after a drop (e.g. refresh). The loop ends when a write
            fails or the service stops.
            """
            origin = self.headers.get("Origin")
            supplied = (parse_qs(urlsplit(self.path).query).get("token") or [""])[0]
            # compare_digest avoids leaking the token through response timing.
            if (origin and origin != f"http://127.0.0.1:{port}") or not secrets.compare_digest(supplied, token):
                self.send_json(403, {"ok": False, "error": "Local session token is missing or invalid."})
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            session_opened()
            try:
                self.wfile.write(b"retry: 2000\n\n")
                self.wfile.flush()
                # A write fails soon after the tab closes.
                while not stopping.wait(SESSION_PING_SECONDS):
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            finally:
                session_closed()

        def authorized(self):
            """Check Origin and X-Local-Token; on failure send 403 and return False.

            A missing Origin is allowed (browsers omit it on some same-origin requests); the token
            is the real gate.
            """
            origin = self.headers.get("Origin")
            if origin and origin != f"http://127.0.0.1:{port}":
                self.send_json(403, {"ok": False, "error": "Origin not allowed."})
                return False
            if self.headers.get("X-Local-Token") != token:
                self.send_json(403, {"ok": False, "error": "Local session token is missing or invalid."})
                return False
            return True

        def do_GET(self):
            """Handle GET /, /api/session-events, /api/status and /api/progress."""
            # The page needs no token (it delivers it); same-origin policy stops other sites reading it.
            if self.path == "/":
                html = (RESOURCE_ROOT / PAGE_FILE).read_text(encoding="utf-8")
                html = html.replace("__LOCAL_SERVICE_TOKEN__", token).replace("__APP_VERSION__", __version__)
                html = html.encode("utf-8")
                self.send_bytes(200, "text/html; charset=utf-8", html)
                return
            # Browsers ask for /favicon.ico anyway; 204 avoids a spurious 403.
            if self.path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
                return
            # Checks its own token, from the query string.
            if self.path.startswith("/api/session-events"):
                self.stream_session_events()
                return
            if not self.authorized():
                return
            try:
                if self.path == "/api/status":
                    self.send_json(200, status_payload())
                    return
                # ?cursor=N returns only rows the page has not received, plus nextCursor.
                if self.path.startswith("/api/progress"):
                    from urllib.parse import parse_qs
                    query = parse_qs(urlsplit(self.path).query)
                    try:
                        cursor = max(0, int(query.get("cursor", ["0"])[0]))
                    except ValueError:
                        cursor = 0
                    with scan_lock:
                        state = dict(scan_state)
                        state["rows"] = state["rows"][cursor:]
                        state["errors"] = list(scan_state["errors"])
                        state["nextCursor"] = cursor + len(state["rows"])
                    self.send_json(200, state)
                    return
                self.send_json(404, {"ok": False, "error": "Not found."})
            except Exception as exc:
                self.send_json(400, {"ok": False, "error": str(exc)})

        def do_POST(self):
            """Handle the POST API routes; all require authorized()."""
            if not self.authorized():
                return
            try:
                # -- /api/stop: reply first, then shut down on another thread (shutdown() would block).
                if self.path == "/api/stop":
                    self.send_json(200, {"ok": True, "stopping": True})
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                    return
                payload = self.body_json()
                # -- /api/setup: tenant and client ID from the setup screen; saved, then sign in.
                if self.path == "/api/setup":
                    new_tenant = tenant_from_input(str(payload.get("tenant") or ""))
                    new_client_id = str(payload.get("clientId") or "").strip() or known_client_id(new_tenant)
                    if not new_client_id or not re.fullmatch(GUID_PATTERN, new_client_id):
                        raise NavigatorError("Enter the Application (client) ID. It looks like "
                                             "00000000-0000-0000-0000-000000000000.")
                    # Only a typed ID is saved; one from a file beside the app stays in that file.
                    save_settings(new_tenant, new_client_id if payload.get("clientId") else None)
                    connect(new_tenant, new_client_id)
                    self.send_json(200, status_payload())
                    return
                # -- /api/setup-reset: show the setup screen again ("Change organisation").
                if self.path == "/api/setup-reset":
                    show_setup()
                    self.send_json(200, status_payload())
                    return
                # -- /api/connect-retry: try the same sign-in again after an error or an expired code.
                if self.path == "/api/connect-retry":
                    retry_tenant = str(payload.get("tenant") or "") or tenant or str(load_settings().get("tenant") or "")
                    retry_tenant = tenant_from_input(retry_tenant)
                    retry_client_id = known_client_id(retry_tenant)
                    if not retry_client_id:
                        show_setup()
                    else:
                        connect(retry_tenant, retry_client_id)
                    self.send_json(200, status_payload())
                    return
                # Everything below needs a signed-in connection.
                with connect_lock:
                    ready = connect_state["phase"] == "ready"
                if not ready:
                    self.send_json(409, {"ok": False, "error": "Not signed in to SharePoint yet.", "notReady": True})
                    return
                # -- /api/scan: start (or join) the background library-root scan.
                if self.path == "/api/scan":
                    start_scan()
                    with scan_lock:
                        self.send_json(202, {"ok": True, "running": scan_state["running"], "status": scan_state["status"]})
                    return
                # -- /api/storage-metric: Storage Metrics for one folder (cached).
                if self.path == "/api/storage-metric":
                    site_url = str(payload.get("siteUrl") or "")
                    folder_path = str(payload.get("folderPath") or "")
                    if not site_url or not folder_path:
                        raise NavigatorError("The selected folder information is incomplete.")
                    metric = get_cached_storage_metric(site_url, folder_path)
                    self.send_json(200, {"ok": True, **metric})
                    return
                # -- /api/folder-children: one page of a folder's direct children (cached).
                if self.path == "/api/folder-children":
                    site_url = str(payload.get("siteUrl") or "")
                    folder_path = str(payload.get("folderPath") or "")
                    if not site_url or not folder_path:
                        raise NavigatorError("The selected folder information is incomplete.")
                    page = get_cached_folder_children(
                        site_url, folder_path, bool(payload.get("loadMore")),
                        int(payload.get("loadedCount") or 0),
                    )
                    self.send_json(200, {"ok": True, **page})
                    return
                # -- /api/search: one block of search results across the loaded sites (read-only).
                if self.path == "/api/search":
                    self.send_json(200, {"ok": True, **run_search(graph, tenant, sites, payload, allowed_sites)})
                    return
                # -- /api/download-link: a short-lived download address for one file (read-only).
                # Graph's @microsoft.graph.downloadUrl is pre-authorised for about an hour, so the
                # browser can fetch the file without being signed in to SharePoint itself.
                if self.path == "/api/download-link":
                    site_url = normalize_site_url(str(payload.get("siteUrl") or ""))
                    item_path = str(payload.get("itemPath") or "")
                    if site_url.lower() not in allowed_sites:
                        raise NavigatorError("The selected site is not in this tenant's loaded site list.")
                    if not item_path:
                        raise NavigatorError("The selected file information is incomplete.")
                    drive, item = inventory.get_item_by_path(site_url, item_path)
                    if item.get("file") is None:
                        raise NavigatorError("Only files can be downloaded.")
                    # "select", not "$select": with "$select" Graph silently drops the downloadUrl
                    # annotation (checked against a real tenant in 0.6.1).
                    found = graph.get(f"/drives/{quote(drive['id'], safe='')}/items/{quote(item['id'], safe='')}"
                                      "?select=id,name,@microsoft.graph.downloadUrl")
                    url = str(found.get("@microsoft.graph.downloadUrl") or "")
                    # Only ever hand the browser a SharePoint https address.
                    host = (urlsplit(url).hostname or "").lower()
                    if not url.startswith("https://") or not (host.endswith(".sharepoint.com") or host.endswith(".sharepoint.us")):
                        raise NavigatorError("SharePoint didn't return a download address for this file.")
                    self.send_json(200, {"ok": True, "url": url, "name": found.get("name") or item.get("name") or ""})
                    return
                # -- /api/transfer: copy or move a file or folder within one site.
                if self.path == "/api/transfer":
                    operation = str(payload.get("operation") or "").strip().lower()
                    site_url = normalize_site_url(str(payload.get("siteUrl") or ""))
                    source_path = str(payload.get("itemPath") or "")
                    destination_path = str(payload.get("destinationPath") or "")
                    if operation not in ("copy", "move"):
                        raise NavigatorError("Choose Copy or Move.")
                    if not source_path or not destination_path:
                        raise NavigatorError("The source or destination folder information is missing.")
                    if site_url.lower() not in allowed_sites:
                        raise NavigatorError("The selected site is not in this tenant's loaded site list.")

                    # Resolve both paths live against the same site; this keeps transfers within one site.
                    source_drive, source_item = inventory.get_item_by_path(site_url, source_path)
                    destination_drive, destination_item = inventory.get_item_by_path(site_url, destination_path)
                    if source_item.get("file") is None and source_item.get("folder") is None:
                        raise NavigatorError("The selected source is not a file or folder.")
                    if destination_item.get("folder") is None:
                        raise NavigatorError("The receiving location is not a folder.")

                    # Refuse to put a folder inside itself or its subtree (case-insensitive, like SharePoint).
                    source_actual_path = item_path_from_url(source_item, source_path)
                    destination_actual_path = item_path_from_url(destination_item, destination_path)
                    source_key = source_actual_path.rstrip("/").casefold()
                    destination_key = destination_actual_path.rstrip("/").casefold()
                    if source_item.get("folder") is not None and (
                        destination_key == source_key or destination_key.startswith(source_key + "/")
                    ):
                        raise NavigatorError("A folder cannot be copied or moved into itself or one of its descendants.")

                    # Refuse if the item no longer matches what the page showed (modified time, size).
                    expected_modified = str(payload.get("expectedModified") or "")
                    current_modified = str(source_item.get("lastModifiedDateTime") or "")
                    if expected_modified and current_modified and expected_modified != current_modified:
                        raise NavigatorError("The item changed since it was displayed. Refresh its folder, then try again.")
                    expected_size = payload.get("expectedSizeBytes")
                    if expected_size is not None and int(source_item.get("size") or 0) != int(expected_size):
                        raise NavigatorError("The file size changed since it was displayed. Refresh its folder, then try again.")

                    source_id = quote(source_item["id"], safe="")
                    destination_id = quote(destination_item["id"], safe="")
                    source_drive_id = quote(source_drive["id"], safe="")
                    destination_drive_id = quote(destination_drive["id"], safe="")
                    if operation == "move":
                        # Graph moves by PATCHing parentReference, which works only within one drive;
                        # a cross-library move would need copy + delete, which this app avoids.
                        if source_drive["id"] != destination_drive["id"]:
                            raise NavigatorError("SharePoint Move works only inside the same document library. Choose a folder in the source library.")
                        source_parent = str((source_item.get("parentReference") or {}).get("id") or "")
                        if source_parent == destination_item["id"]:
                            raise NavigatorError("The item is already in that folder.")
                        # If-Match with the eTag just read: Graph refuses the move if the item changed.
                        # With no conflict rule set, Graph also refuses (HTTP 409) when the destination
                        # already holds that name, so nothing is overwritten; only the wording is ours.
                        try:
                            graph.patch(
                                f"/drives/{source_drive_id}/items/{source_id}",
                                {"parentReference": {"driveId": source_drive["id"], "id": destination_item["id"]}},
                                source_item.get("eTag") or None,
                            )
                        except NavigatorError as exc:
                            if "HTTP 409" in str(exc):
                                raise NavigatorError(
                                    "An item with that name is already in the destination folder. Nothing was moved."
                                ) from exc
                            raise
                        result = {"queued": False, "itemName": source_item.get("name", "")}
                    else:
                        # Copy stays in the item's own library (the picker offers no other); conflictBehavior=rename
                        # avoids overwriting by saving as "name 1". Graph usually answers 202 and copies in the
                        # background ("queued").
                        response = graph.request(
                            "POST",
                            f"/drives/{source_drive_id}/items/{source_id}/copy?@microsoft.graph.conflictBehavior=rename",
                            json_body={"parentReference": {
                                "driveId": destination_drive["id"], "id": destination_item["id"],
                            }},
                            return_response=True,
                        )
                        result = {
                            "queued": response.status_code == 202,
                            "itemName": source_item.get("name", ""),
                        }

                    # A plain record of the change in the terminal.
                    if operation == "move":
                        print(f"Moved {source_actual_path} to {destination_actual_path} ({site_url}).", flush=True)
                    else:
                        verb = "Copy submitted" if result["queued"] else "Copied"
                        print(f"{verb}: {source_actual_path} to {destination_actual_path} ({site_url}).", flush=True)
                    # Both locations changed; clearing all caches is simpler and safer than targeting entries.
                    with storage_metric_lock:
                        storage_metric_cache.clear()
                    with folder_children_lock:
                        folder_children_cache.clear()
                    self.send_json(200, {"ok": True, "operation": operation, **result})
                    return
                # -- /api/trim-queue: every site's trim and version-policy job, checked 6 at a time.
                # Read-only. A site that can't be checked (403 and so on) gets an error and the rest go on.
                if self.path == "/api/trim-queue":
                    def check(site: dict) -> dict:
                        """Return one site's two job states, or its error."""
                        url = normalize_site_url(site["url"])
                        try:
                            # A subsite would report its parent's jobs, so it is marked instead.
                            collection_url = sharepoint.site_collection_url(url)
                            if collection_url.lower() != url.lower():
                                return {"siteUrl": url, "error": f"Part of the site {collection_url}."}
                            return {"siteUrl": url, "trim": sharepoint.trim_progress(url),
                                    "policy": sharepoint.version_policy_progress(url)}
                        except (NavigatorError, requests.RequestException) as exc:
                            return {"siteUrl": url, "error": str(exc)}
                    with ThreadPoolExecutor(max_workers=6) as pool:
                        results = list(pool.map(check, sites))
                    checked = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                    self.send_json(200, {"ok": True, "checked": checked, "sites": results})
                    return
                # -- /api/trim-status, /api/trim-start, /api/trim-cancel: site-level version trim.
                # Each acts on one site from the loaded list and answers with its latest job.
                if self.path in ("/api/trim-status", "/api/trim-start", "/api/trim-cancel"):
                    site_url = normalize_site_url(str(payload.get("siteUrl") or ""))
                    if site_url.lower() not in allowed_sites:
                        raise NavigatorError("The selected site is not in this tenant's loaded site list.")
                    # /_api/site is the whole site collection. If this URL were a subsite, every call
                    # would act on its parent site, so only a site collection's own URL is accepted.
                    collection_url = sharepoint.site_collection_url(site_url)
                    if collection_url.lower() != site_url.lower():
                        raise NavigatorError(f"{site_url} is part of the site {collection_url}, so a trim here would "
                                             "cover that whole site. Nothing was changed.")
                    if self.path == "/api/trim-start":
                        # Validate first, so a bad rule never reaches SharePoint.
                        parameters, description = trim_parameters(payload)
                        with trim_lock:
                            before = sharepoint.trim_progress(site_url)
                            # SharePoint allows one trim per site at a time; say so plainly.
                            if before["running"]:
                                raise NavigatorError("A trim is already queued or running for this site. "
                                                     "Wait for it to finish, or stop it first.")
                            # A version-policy job can trim too; don't stack a trim on top of one.
                            if sharepoint.version_policy_progress(site_url)["running"]:
                                raise NavigatorError("A version-limit change is being applied to this site's libraries. "
                                                     "Wait for it to finish, then try again.")
                            sharepoint.start_trim(site_url, parameters)
                            print(f"Version trim queued for {site_url}: {description}.", flush=True)
                            # Read back what SharePoint recorded (a new job id) for a few seconds.
                            after = before
                            for _ in range(6):
                                after = sharepoint.trim_progress(site_url)
                                if after["exists"] and after["workItemId"] != before["workItemId"]:
                                    break
                                time.sleep(1.5)
                            # Safety net: a job whose rule differs from the request, or that can't be
                            # seen, is stopped at once. Trims run in later batches, so stopping now
                            # comes before any version is deleted.
                            new_job = after["exists"] and after["workItemId"] != before["workItemId"]
                            if not new_job or not trim_matches(after, parameters):
                                try:
                                    sharepoint.cancel_trim(site_url)
                                    stopped = "The app stopped it right away."
                                except NavigatorError as exc:
                                    stopped = f"The app could not stop it ({exc}); stop it now with Stop trim."
                                print(f"Version trim on {site_url} failed the read-back check "
                                      f"(new job: {new_job}, recorded mode: {after['mode'] or 'none'}). {stopped}", flush=True)
                                raise NavigatorError(
                                    ("SharePoint recorded a different rule than the one requested. " if new_job else
                                     "The app couldn't confirm the trim SharePoint recorded. ") + stopped +
                                    " Select Check again to see the site's status.")
                    elif self.path == "/api/trim-cancel":
                        with trim_lock:
                            sharepoint.cancel_trim(site_url)
                        print(f"Version trim stop requested for {site_url}.", flush=True)
                    self.send_json(200, {"ok": True, "trim": sharepoint.trim_progress(site_url),
                                         "policy": sharepoint.version_policy_progress(site_url)})
                    return
                # -- /api/inspect: rename step 1. Validate the name, snapshot the item, and hold it
                # under a single-use inspection id.
                if self.path == "/api/inspect":
                    site_url = str(payload.get("siteUrl") or "")
                    item_path = str(payload.get("itemPath") or "")
                    item_type = str(payload.get("itemType") or "").lower()
                    new_name = str(payload.get("newName") or "").strip()
                    if not site_url or not item_path or item_type not in ("folder", "file"):
                        raise NavigatorError("The selected item is missing details. Select Reload libraries and try again.")
                    # SharePoint rejects these characters and names ending in a dot or space.
                    if not new_name or any(char in NAME_BAD_CHARS for char in new_name) or new_name.endswith((".", " ")):
                        raise NavigatorError("The new name is empty or contains a SharePoint-invalid character.")
                    snapshot = inventory.snapshot(site_url, item_path)
                    if snapshot["itemType"] != item_type:
                        raise NavigatorError("The item changed type since it was shown. Reopen its folder and try again.")
                    if new_name == snapshot["name"]:
                        raise NavigatorError("The new name is the same as the current name.")
                    if inventory.name_taken(site_url, item_path, new_name):
                        raise NavigatorError("An item with the requested name already exists in this folder.")
                    inspection_id = secrets.token_hex(16)
                    # A mismatch with what the page showed doesn't block; the page warns before confirming.
                    expected_modified = str(payload.get("expectedModified") or "")
                    expected_size_raw = payload.get("expectedSizeBytes")
                    expected_count_raw = payload.get("expectedFileCount")
                    expected_size = int(expected_size_raw) if expected_size_raw is not None else None
                    expected_count = int(expected_count_raw) if expected_count_raw is not None else None
                    changed = bool(
                        (expected_modified and snapshot["modified"] and expected_modified != snapshot["modified"])
                        or (expected_size is not None and expected_size != snapshot["sizeBytes"])
                        or (item_type == "folder" and expected_count is not None and expected_count != snapshot["fileCount"])
                    )
                    # Valid for 5 minutes and single use; unused entries stay in memory until exit.
                    with pending_lock:
                        pending[inspection_id] = {
                            "snapshot": snapshot, "newName": new_name,
                            "expires": datetime.now(timezone.utc) + timedelta(minutes=5),
                        }
                    self.send_json(200, {
                        "ok": True, "inspectionId": inspection_id, "itemType": item_type,
                        "name": snapshot["name"], "path": snapshot["path"],
                        "modified": snapshot["modified"], "sizeBytes": snapshot["sizeBytes"],
                        "fileCount": snapshot["fileCount"], "changedSinceReport": changed,
                    })
                    return
                # -- /api/rename: rename step 2; runs only for a fresh, unused, unchanged inspection.
                if self.path == "/api/rename":
                    inspection_id = str(payload.get("inspectionId") or "")
                    # pop() makes each inspection id single-use, even with concurrent requests.
                    with pending_lock:
                        inspection = pending.pop(inspection_id, None)
                    if not inspection:
                        raise NavigatorError("The live preview expired or was already used. Inspect the item again.")
                    if datetime.now(timezone.utc) > inspection["expires"]:
                        raise NavigatorError("The live preview expired. Inspect the item again before renaming.")
                    if str(payload.get("newName") or "") != inspection["newName"]:
                        raise NavigatorError("The requested name does not match the preview. Inspect it again.")
                    # Re-snapshot by item id and require every tracked field to be unchanged.
                    before = inspection["snapshot"]
                    current = inventory.snapshot_by_id(before)
                    for field in ("itemId", "path", "modified", "sizeBytes", "fileCount", "etag", "ctag"):
                        if current.get(field) != before.get(field):
                            raise NavigatorError("The item changed after the preview. Nothing was renamed; inspect it again.")
                    # Repeat the name check; the name may have been taken since the preview.
                    if inventory.name_taken(before["siteUrl"], before["path"], inspection["newName"]):
                        raise NavigatorError("An item with the requested name now exists. Nothing was renamed.")
                    # If-Match with the previewed eTag: Graph returns 412 if the item changed since.
                    graph.patch(
                        f"/drives/{quote(before['driveId'], safe='')}/items/{quote(before['itemId'], safe='')}",
                        {"name": inspection["newName"]}, before.get("etag") or None,
                    )
                    # Renaming a folder changes the paths (cache keys) of everything below it.
                    with storage_metric_lock:
                        storage_metric_cache.clear()
                    with folder_children_lock:
                        folder_children_cache.clear()
                    new_path = before["path"].rsplit("/", 1)[0] + "/" + inspection["newName"]
                    print(f"Renamed {before['path']} to {inspection['newName']} ({before['siteUrl']}).", flush=True)
                    self.send_json(200, {"ok": True, "newName": inspection["newName"], "newPath": new_path, "itemType": before["itemType"]})
                    return
                # -- /api/delete-inspect: delete step 1. Take a live snapshot of the item (a folder is
                # counted all the way down) and hold it under a single-use id. Changes nothing.
                if self.path == "/api/delete-inspect":
                    site_url = normalize_site_url(str(payload.get("siteUrl") or ""))
                    item_path = str(payload.get("itemPath") or "")
                    item_type = str(payload.get("itemType") or "").lower()
                    if site_url.lower() not in allowed_sites:
                        raise NavigatorError("The selected site is not in this tenant's loaded site list.")
                    if not item_path or item_type not in ("folder", "file"):
                        raise NavigatorError("The selected item is missing details. Select Reload libraries and try again.")
                    # A library's own root is never deleted from here; only files and folders inside one.
                    _, relative = inventory.drive_for_item(site_url, item_path)
                    if not relative:
                        raise NavigatorError("A whole library can't be deleted from this app. Nothing was changed.")
                    snapshot = inventory.snapshot(site_url, item_path)
                    if snapshot["itemType"] != item_type:
                        raise NavigatorError("The item changed type since it was shown. Reopen its folder and try again.")
                    # Same check as rename: tell the page if what it showed is out of date.
                    expected_modified = str(payload.get("expectedModified") or "")
                    expected_size_raw = payload.get("expectedSizeBytes")
                    expected_count_raw = payload.get("expectedFileCount")
                    changed = bool(
                        (expected_modified and snapshot["modified"] and expected_modified != snapshot["modified"])
                        or (expected_size_raw is not None and int(expected_size_raw) != snapshot["sizeBytes"])
                        or (item_type == "folder" and expected_count_raw is not None
                            and int(expected_count_raw) != snapshot["fileCount"])
                    )
                    delete_id = secrets.token_hex(16)
                    now = datetime.now(timezone.utc)
                    with pending_lock:
                        pending_deletes[delete_id] = {
                            "snapshot": snapshot,
                            "notBefore": now + timedelta(seconds=delete_wait),
                            "expires": now + timedelta(minutes=DELETE_PREVIEW_MINUTES),
                        }
                    self.send_json(200, {
                        "ok": True, "deleteId": delete_id, "itemType": item_type, "siteUrl": snapshot["siteUrl"],
                        "name": snapshot["name"], "path": snapshot["path"], "modified": snapshot["modified"],
                        "sizeBytes": snapshot["sizeBytes"], "fileCount": snapshot["fileCount"],
                        "changedSinceReport": changed, "waitSeconds": delete_wait,
                        "expiresMinutes": DELETE_PREVIEW_MINUTES,
                    })
                    return
                # -- /api/delete: delete step 2. Every check must pass, or nothing is deleted.
                if self.path == "/api/delete":
                    delete_id = str(payload.get("deleteId") or "")
                    # pop() makes each preview single-use: any refusal below means starting over.
                    with pending_lock:
                        pending_delete = pending_deletes.pop(delete_id, None)
                    if not pending_delete:
                        raise NavigatorError("The delete preview expired or was already used. Nothing was deleted; start again.")
                    now = datetime.now(timezone.utc)
                    if now > pending_delete["expires"]:
                        raise NavigatorError("The delete preview expired. Nothing was deleted; start again.")
                    if now < pending_delete["notBefore"]:
                        raise NavigatorError("The delete was confirmed too quickly after the preview. Nothing was deleted; start again.")
                    before = pending_delete["snapshot"]
                    # The page must send back what the person typed: the exact name (case matters)
                    # and, for a folder, how many files it holds, plus the fixed acknowledgement.
                    if payload.get("acknowledge") != "delete-to-recycle-bin":
                        raise NavigatorError("The delete wasn't acknowledged. Nothing was deleted.")
                    # NFC on both sides: names uploaded from a Mac can be stored decomposed (common for
                    # Korean), which looks the same but can't be typed back. Case and spaces still count.
                    typed_name = unicodedata.normalize("NFC", str(payload.get("confirmName") or ""))
                    if typed_name != unicodedata.normalize("NFC", before["name"]):
                        raise NavigatorError("The typed name doesn't match the item's name exactly. Nothing was deleted.")
                    if before["itemType"] == "folder":
                        try:
                            typed_count = int(str(payload.get("confirmFileCount")).replace(",", "").strip())
                        except (TypeError, ValueError):
                            typed_count = -1
                        if typed_count != before["fileCount"]:
                            raise NavigatorError("The typed file count doesn't match the folder. Nothing was deleted.")
                    # Re-snapshot by id (a folder is walked again) and require every tracked field to be unchanged.
                    current = inventory.snapshot_by_id(before)
                    for field in ("itemId", "path", "name", "modified", "sizeBytes", "fileCount", "etag", "ctag"):
                        if current.get(field) != before.get(field):
                            raise NavigatorError("The item changed after the preview. Nothing was deleted; check it again.")
                    # If-Match with the previewed eTag: Graph refuses (412) if the item changed in between.
                    # Graph's DELETE moves the item to the site's recycle bin; it is not a permanent delete.
                    graph.request(
                        "DELETE",
                        f"/drives/{quote(before['driveId'], safe='')}/items/{quote(before['itemId'], safe='')}",
                        headers={"If-Match": before["etag"]} if before.get("etag") else None,
                    )
                    # Sizes and listings above the item changed.
                    with storage_metric_lock:
                        storage_metric_cache.clear()
                    with folder_children_lock:
                        folder_children_cache.clear()
                    contents = f", {before['fileCount']} files inside" if before["itemType"] == "folder" else ""
                    print(f"Deleted (to the recycle bin) {before['itemType']} {before['path']}{contents} ({before['siteUrl']}).", flush=True)
                    self.send_json(200, {"ok": True, "name": before["name"], "path": before["path"], "itemType": before["itemType"]})
                    return
                self.send_json(404, {"ok": False, "error": "Not found."})
            except Exception as exc:
                # These requests' log lines are suppressed (see log_message), so print the failing
                # site and folder. `payload` is unset if the body itself was bad.
                if self.path in ("/api/storage-metric", "/api/folder-children"):
                    details = locals().get("payload") or {}
                    what = "Storage Metrics" if self.path == "/api/storage-metric" else "Folder listing"
                    print(f"{what} failed for {details.get('siteUrl', '(unknown site)')} / "
                          f"{details.get('folderPath', '(unknown folder)')}: {exc}", flush=True)
                elif self.path == "/api/download-link":
                    # The request line alone doesn't say why; the reason is short and has no token.
                    print(f"Download link failed: {exc}", flush=True)
                self.send_json(400, {"ok": False, "error": str(exc)})

    # ---- Start serving ----
    # 127.0.0.1 only. Daemon request threads let the process exit with event streams still open.
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    server_holder["server"] = server
    # The port is ours now: leave the version and stop key for a newer copy (see take_over).
    # Created readable by this user only, like the settings file beside it; a failure here only
    # means a newer copy will ask the person to stop this one by hand.
    marker = running_file(port)
    try:
        USER_FOLDER.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump({"version": __version__, "port": port, "token": token, "pid": os.getpid()}, handle)
    except OSError as exc:
        print(f"Couldn't write {marker.name} ({exc}); a newer copy can't take over from this one.", flush=True)
    base_url = f"http://127.0.0.1:{port}/"
    # Known tenant and client ID: sign in right away; otherwise the page shows the setup screen.
    if tenant and client_id and not force_setup:
        connect(tenant, client_id)
    print(f"\nSharePoint Navigator {__version__} is running: {base_url}", flush=True)
    if auto_stop:
        print("Closing the browser tab stops the app. Press Ctrl+C to stop it sooner.", flush=True)
    else:
        print("Press Ctrl+C to stop.", flush=True)
    try:
        if open_browser:
            webbrowser.open(base_url)
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        # Ends the keep-alive loops of any open event streams.
        stopping.set()
        # Remove our file while the port is still held, so a copy waiting to take over can't
        # write its own first and lose it here. Only our own file (same token) is removed.
        try:
            if json.loads(marker.read_text(encoding="utf-8")).get("token") == token:
                marker.unlink()
        except (OSError, ValueError):
            pass
        server.server_close()
        print("SharePoint Navigator service stopped.")


# ---- Entry point ----

# A DNS label: letters, digits and hyphens, 2-63 characters, no hyphen at either end.
TENANT_PATTERN = r"[A-Za-z0-9][A-Za-z0-9-]{0,61}[A-Za-z0-9]"


def tenants_with_client_id() -> list[str]:
    """Return the tenant names that have a ``<tenant>_clientid.txt`` file in APP_ROOT, sorted."""
    suffix = "_clientid.txt"
    return sorted(p.name[: -len(suffix)] for p in APP_ROOT.glob("*" + suffix)
                  if re.fullmatch(TENANT_PATTERN, p.name[: -len(suffix)]))


def self_check() -> int:
    """Check that a build or install can start, without signing in; return 0 if usable, else 1.

    Prints Python and library versions, whether the page exists with its token placeholder, the
    data folder, and the tenants with client ID files.
    """
    page = RESOURCE_ROOT / PAGE_FILE
    page_ok = page.is_file() and "__LOCAL_SERVICE_TOKEN__" in page.read_text(encoding="utf-8")
    print(f"SharePoint Navigator {__version__}")
    print(f"Python {sys.version.split()[0]} on {sys.platform}; packaged={FROZEN}")
    print(f"msal {msal.__version__}; requests {requests.__version__}")
    print(f"Page file: {'OK' if page_ok else 'MISSING'} ({page})")
    print(f"Data folder: {APP_ROOT}")
    tenants = tenants_with_client_id()
    print(f"Client ID files found for: {', '.join(tenants) if tenants else 'none (the app asks on first run)'}")
    saved = load_settings()
    print(f"Saved settings: {saved.get('tenant') or 'none'} ({SETTINGS_FILE})")
    return 0 if page_ok else 1


def has_console() -> bool:
    """True when started from a terminal; False for the windowless Windows app and the macOS .app."""
    return sys.stdout is not None and hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def use_log_file() -> None:
    """Without a terminal, send all output to ~/.sharepoint-navigator/app.log (kept under 1 MB).

    The windowless Windows build has no stdout at all, and messages are still worth keeping for
    troubleshooting. Each start begins a fresh section; an oversized log is started over.
    """
    # Source runs keep their output (it may be piped to a file on purpose); the packaged app
    # without a terminal, and anything with no stdout at all, write to the log.
    if has_console() or (not FROZEN and sys.stdout is not None):
        return
    try:
        USER_FOLDER.mkdir(parents=True, exist_ok=True)
        log = USER_FOLDER / "app.log"
        mode = "w" if log.is_file() and log.stat().st_size > 1_000_000 else "a"
        stream = open(log, mode, encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = stream
        print(f"\n---- {datetime.now().isoformat(timespec='seconds')} SharePoint Navigator {__version__} ----")
    except OSError:
        pass


def show_fatal(message: str) -> None:
    """Show a start-up error the person can see: the terminal if there is one, else a system dialog."""
    print(f"\nSharePoint Navigator could not start: {message}", flush=True)
    if has_console():
        if FROZEN:
            # A double-clicked console window would otherwise close before the error is read.
            try:
                input("Press Enter to close.")
            except EOFError:
                pass
        return
    try:
        if sys.platform == "win32":
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, message, "SharePoint Navigator", 0x10)
        elif sys.platform == "darwin":
            import subprocess
            subprocess.run(["osascript", "-e", "on run argv", "-e",
                            'display alert "SharePoint Navigator could not start" message (item 1 of argv) as critical',
                            "-e", "end run", message], check=False, timeout=600)
    except Exception:
        pass


def show_notice(message: str) -> None:
    """Tell the person something that isn't an error: the terminal if there is one, else a system dialog."""
    print(message, flush=True)
    if has_console():
        return
    try:
        if sys.platform == "win32":
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, message, "SharePoint Navigator", 0x40)
        elif sys.platform == "darwin":
            import subprocess
            subprocess.run(["osascript", "-e", "on run argv", "-e",
                            'display alert "SharePoint Navigator" message (item 1 of argv)',
                            "-e", "end run", message], check=False, timeout=600)
    except Exception:
        pass


def parse_version(value: str):
    """Turn "1.2.3" (or "v1.2.3") into (1, 2, 3); anything else into None."""
    match = re.fullmatch(r"v?(\d{1,4})\.(\d{1,4})\.(\d{1,4})", str(value or "").strip())
    return tuple(int(part) for part in match.groups()) if match else None


def running_version(port: int):
    """The version of the copy serving on the port, read from its page (every version puts it
    there), or None if it can't be read."""
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=3) as response:
            page = response.read(400_000).decode("utf-8", "replace")
    except Exception:
        return None
    match = re.search(r'id="appVersion"[^>]*>\s*v?([0-9.]+)\s*<', page)
    return parse_version(match.group(1)) if match else None


def take_over(port: int) -> bool:
    """A copy already serves on the port. Return True if this copy should start in its place.

    Same version, a newer one, or one whose version can't be read: open its page and stop here
    (False). An older one is asked to stop with the key it left in running_file; once the port is
    free, this copy starts (True). Versions before 1.2.0 leave no key, and a key that doesn't
    work is the same case: open the old page and tell the person to click Stop app there.
    """
    import urllib.request
    base_url = f"http://127.0.0.1:{port}/"
    mine, theirs = parse_version(__version__), running_version(port)
    if theirs is None or mine is None or theirs >= mine:
        print(f"SharePoint Navigator is already running; opening {base_url}", flush=True)
        webbrowser.open(base_url)
        return False
    old = ".".join(map(str, theirs))
    stopped = False
    try:
        info = json.loads(running_file(port).read_text(encoding="utf-8"))
        # The key must belong to the copy that answers: same port and the version it reports.
        if info.get("port") == port and parse_version(info.get("version")) == theirs and info.get("token"):
            print(f"SharePoint Navigator {old} is running; this is {__version__}. Stopping the older copy.", flush=True)
            request = urllib.request.Request(base_url + "api/stop", data=b"{}", method="POST",
                                             headers={"Content-Type": "application/json",
                                                      "X-Local-Token": str(info["token"])})
            with urllib.request.urlopen(request, timeout=5):
                pass
            # Wait until the old copy has let go of the port (it shuts down on its own thread).
            for _ in range(60):
                if not already_running(port):
                    stopped = True
                    break
                time.sleep(0.25)
    except (OSError, ValueError):
        stopped = False
    if stopped:
        print(f"Stopped SharePoint Navigator {old}; starting {__version__}.", flush=True)
        return True
    # Couldn't stop it (it predates 1.2.0, or didn't answer): send the person to its page.
    webbrowser.open(base_url)
    show_notice(f"SharePoint Navigator {old} is still running, so this copy ({__version__}) can't start. "
                "Click Stop app at the top of its page (now open in your browser), then open the app again.")
    return False


def already_running(port: int) -> bool:
    """True if this app already answers on the port (checked by its Server header)."""
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/favicon.ico", timeout=2) as response:
            return "SharePointNavigator" in (response.headers.get("Server") or "")
    except Exception:
        return False


def main():
    """Parse arguments and environment, then run the service or the self-check."""
    args = sys.argv[1:]
    if "--version" in args:
        print(__version__)
        raise SystemExit(0)
    if "--self-check" in args:
        raise SystemExit(self_check())
    try:
        port = int(os.environ.get("SHAREPOINT_NAVIGATOR_PORT", "8765"))
    except ValueError as exc:
        raise NavigatorError("SHAREPOINT_NAVIGATOR_PORT must be a number.") from exc
    # Opened again while running: bring that page back, or take over from an older version.
    if already_running(port) and not take_over(port):
        return
    # Whatever isn't known yet (tenant, client ID) is asked on the page's setup screen.
    # --setup shows that screen even when both are known (e.g. to switch organisation).
    tenant = known_tenant(args)
    client_id = known_client_id(tenant) if tenant else None
    run_server(port, tenant, client_id, force_setup="--setup" in args)


if __name__ == "__main__":
    use_log_file()
    # Expected failures show a short message instead of a traceback.
    try:
        main()
    except (NavigatorError, OSError, requests.RequestException) as exc:
        show_fatal(str(exc))
        raise SystemExit(1)
