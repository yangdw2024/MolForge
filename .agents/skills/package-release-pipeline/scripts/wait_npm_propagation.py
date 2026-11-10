#!/usr/bin/env python3
"""
Poll npm registry until a newly published package or version propagates through CDN caches.
Usage:
    python wait_npm_propagation.py --package <PKG_NAME> [--expected-version <VER>]
"""

import sys
import time
import json
import argparse
import urllib.request
import urllib.error

def wait_propagation(package_name: str, expected_version: str = None, timeout_sec: int = 180):
    url = f"https://registry.npmjs.org/{package_name}"
    print(f"Polling {url} for availability (timeout: {timeout_sec}s)...")
    start_time = time.time()
    attempt = 1

    while time.time() - start_time < timeout_sec:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "PackageReleaseSkill"})
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                latest = data.get("dist-tags", {}).get("latest")
                if expected_version:
                    if latest == expected_version or expected_version in data.get("versions", {}):
                        print(f"Success: Package {package_name}@{expected_version} is now LIVE on npm!")
                        return True
                    else:
                        print(f"Attempt {attempt}: Found version {latest}, waiting for {expected_version}...")
                else:
                    print(f"Success: Package {package_name} is now LIVE on npm! (latest: {latest})")
                    return True
        except urllib.error.HTTPError as e:
            if e.code == 404:
                print(f"Attempt {attempt}: 404 Not Found (CDN cache propagating)...")
            else:
                print(f"Attempt {attempt}: HTTP {e.code}: {e.reason}")
        except Exception as e:
            print(f"Attempt {attempt}: Error: {e}")

        time.sleep(4)
        attempt += 1

    print(f"Timeout reached after {timeout_sec}s. Package may still be propagating.")
    return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Wait for npm package CDN propagation")
    parser.add_argument("--package", required=True, help="npm package name (e.g. @yangdw2024/calchem)")
    parser.add_argument("--expected-version", help="Expected version string")
    parser.add_argument("--timeout", type=int, default=180, help="Timeout in seconds")
    args = parser.parse_args()
    ok = wait_propagation(args.package, args.expected_version, args.timeout)
    sys.exit(0 if ok else 1)
