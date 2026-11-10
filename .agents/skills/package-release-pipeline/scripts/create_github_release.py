#!/usr/bin/env python3
"""
Create GitHub Release and attach release assets.
Usage:
    python create_github_release.py --token <GH_TOKEN> --repo <OWNER/REPO> --tag <TAG> --dist <DIST_DIR>
"""

import os
import sys
import argparse
import requests

def create_release_and_upload(token: str, repo: str, tag: str, dist_dir: str, title: str = None, notes: str = None):
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "PackageReleaseSkill"
    }

    # 1. Check or create release
    rel_url = f"https://api.github.com/repos/{repo}/releases/tags/{tag}"
    r = requests.get(rel_url, headers=headers)
    if r.status_code == 200:
        rel = r.json()
        print(f"Release already exists: {rel['html_url']}")
    else:
        payload = {
            "tag_name": tag,
            "name": title or f"Release {tag}",
            "body": notes or f"Automated multi-platform release {tag}.",
            "draft": False,
            "prerelease": False
        }
        r = requests.post(f"https://api.github.com/repos/{repo}/releases", json=payload, headers=headers)
        r.raise_for_status()
        rel = r.json()
        print(f"Created release: {rel['html_url']}")

    upload_url_base = rel["upload_url"].split("{")[0]
    existing_assets = {a["name"]: a["id"] for a in rel.get("assets", [])}

    # 2. Upload all assets from dist_dir
    if not os.path.exists(dist_dir):
        print(f"Warning: dist directory {dist_dir} does not exist.")
        return

    for fname in os.listdir(dist_dir):
        fpath = os.path.join(dist_dir, fname)
        if not os.path.isfile(fpath):
            continue
        if fname in existing_assets:
            print(f"Asset {fname} already uploaded, skipping.")
            continue

        print(f"Uploading asset {fname}...")
        mime = "application/zip" if fname.endswith(".whl") else "application/gzip"
        with open(fpath, "rb") as f:
            data = f.read()

        u_headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": mime,
            "User-Agent": "PackageReleaseSkill"
        }
        ur = requests.post(f"{upload_url_base}?name={fname}", headers=u_headers, data=data)
        if ur.status_code in (200, 201):
            print(f"Uploaded {fname} successfully.")
        else:
            print(f"Failed to upload {fname}: {ur.status_code} {ur.text}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create GitHub release and upload assets")
    parser.add_argument("--token", required=True, help="GitHub Token")
    parser.add_argument("--repo", required=True, help="owner/repo")
    parser.add_argument("--tag", required=True, help="v0.2.0")
    parser.add_argument("--dist", required=True, help="Directory containing dist files")
    parser.add_argument("--title", help="Release title")
    parser.add_argument("--notes", help="Release notes markdown")
    args = parser.parse_args()
    create_release_and_upload(args.token, args.repo, args.tag, args.dist, args.title, args.notes)
