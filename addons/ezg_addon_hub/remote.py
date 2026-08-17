"""Tai index.json / catalog.json ve va nho trong bo nho phien lam viec.

Hub tu tai index.json thay vi doc cache noi bo cua Blender: cache do la chi tiet
cai dat co the doi giua cac ban Blender, con dinh dang index.json thi on dinh vi
chinh Blender doc no.

Moi ham deu ton trong bpy.app.online_access — Blender co che do offline va addon
khong duoc phep lam ngo dieu do.
"""

import json
import os
import urllib.error
import urllib.request

import bpy

TIMEOUT = 20

# {url: {"index": {...}, "catalog": {...}}} — chi song trong phien Blender hien tai.
_cache = {}


class RemoteError(Exception):
    pass


def online():
    return bool(bpy.app.online_access)


def _fetch_json(url, token=""):
    if not online():
        raise RemoteError("Blender dang o che do offline. Bat Preferences > System > Allow Online Access.")

    req = urllib.request.Request(url, headers={"User-Agent": "ezg-addon-hub"})
    if token:
        req.add_header("Authorization", "Bearer %s" % token)

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise RemoteError("Bi tu choi (%d). Kho dat private? Kiem tra access token." % exc.code)
        if exc.code == 404:
            raise RemoteError("Khong tim thay (404): %s" % url)
        raise RemoteError("Loi HTTP %d khi tai %s" % (exc.code, url))
    except urllib.error.URLError as exc:
        raise RemoteError("Khong ket noi duoc: %s" % exc.reason)
    except Exception as exc:
        raise RemoteError("Loi khi tai: %s" % exc)

    try:
        return json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise RemoteError("Noi dung tra ve khong phai JSON hop le: %s" % exc)


def _catalog_url(index_url):
    """catalog.json nam canh index.json trong cung thu muc."""
    return index_url.rsplit("/", 1)[0] + "/catalog.json"


def fetch(index_url, token="", force=False):
    """Tra ve (index_dict, catalog_dict). catalog co the la {} neu kho khong co."""
    url = (index_url or "").strip()
    if not url:
        raise RemoteError("Chua dat URL kho EZG trong Preferences cua hub.")

    if not force and url in _cache:
        return _cache[url]["index"], _cache[url]["catalog"]

    index = _fetch_json(url, token)

    # catalog.json la tuy chon: kho van dung duoc neu chi co index.json.
    try:
        catalog = _fetch_json(_catalog_url(url), token)
    except RemoteError:
        catalog = {}

    _cache[url] = {"index": index, "catalog": catalog}
    return index, catalog


def clear_cache():
    _cache.clear()


def index_versions(index):
    """{pkg_id: version} tu index.json."""
    out = {}
    for entry in (index or {}).get("data", []):
        pkg_id = entry.get("id")
        if pkg_id:
            out[pkg_id] = entry.get("version", "")
    return out


def index_entries(index):
    """{pkg_id: entry} tu index.json."""
    out = {}
    for entry in (index or {}).get("data", []):
        pkg_id = entry.get("id")
        if pkg_id:
            out[pkg_id] = entry
    return out


def remote_versions_for_repos(repos):
    """Tai index cua nhieu repo mot luot -> {(repo_module, pkg_id): version}.

    Loi cua mot repo khong lam hong ca lan quet: repo do bi bo qua.
    """
    out = {}
    if not online():
        return out

    for repo in repos:
        url = (getattr(repo, "remote_url", "") or "").strip()
        if not (getattr(repo, "use_remote_url", False) and url and repo.enabled):
            continue
        try:
            index = _fetch_json(url, getattr(repo, "access_token", "") or "")
        except RemoteError:
            continue
        for pkg_id, version in index_versions(index).items():
            out[(repo.module, pkg_id)] = version
    return out
