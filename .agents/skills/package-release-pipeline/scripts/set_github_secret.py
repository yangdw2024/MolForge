#!/usr/bin/env python3
"""
Encrypted GitHub Actions Secret Uploader using PyNaCl SealedBox.
Usage:
    python set_github_secret.py --token <GH_TOKEN> --repo <OWNER/REPO> --name <SECRET_NAME> --value <SECRET_VALUE>
"""

import sys
import argparse
import base64
import requests

try:
    from nacl import encoding, public
except ImportError:
    print("Error: pynacl is required. Run: pip install pynacl")
    sys.exit(1)

def encrypt(public_key: str, secret_value: str) -> str:
    """Encrypt a secret value using the repository public key."""
    public_key_obj = public.PublicKey(public_key.encode("utf-8"), encoding.Base64Encoder())
    sealed_box = public.SealedBox(public_key_obj)
    encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
    return base64.b64encode(encrypted).decode("utf-8")

def set_secret(token: str, repo: str, name: str, value: str):
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "PackageReleaseSkill"
    }

    # 1. Get repository public key
    key_url = f"https://api.github.com/repos/{repo}/actions/secrets/public-key"
    r = requests.get(key_url, headers=headers)
    r.raise_for_status()
    key_data = r.json()
    key_id = key_data["key_id"]
    public_key = key_data["key"]

    # 2. Encrypt secret
    encrypted_value = encrypt(public_key, value)

    # 3. Upload secret
    put_url = f"https://api.github.com/repos/{repo}/actions/secrets/{name}"
    payload = {
        "encrypted_value": encrypted_value,
        "key_id": key_id
    }
    r_put = requests.put(put_url, json=payload, headers=headers)
    if r_put.status_code in (201, 204):
        print(f"Successfully configured secret '{name}' on {repo} (HTTP {r_put.status_code})")
    else:
        print(f"Failed to set secret: HTTP {r_put.status_code}: {r_put.text}")
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Upload GitHub Actions secret")
    parser.add_argument("--token", required=True, help="GitHub Personal Access Token")
    parser.add_argument("--repo", required=True, help="owner/repo")
    parser.add_argument("--name", required=True, help="Secret name")
    parser.add_argument("--value", required=True, help="Secret value")
    args = parser.parse_args()
    set_secret(args.token, args.repo, args.name, args.value)
