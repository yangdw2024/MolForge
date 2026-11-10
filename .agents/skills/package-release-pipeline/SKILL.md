---
name: package-release-pipeline
description: >-
  Standardized end-to-end workflow to build, verify, and publish multi-language projects across GitHub (Repositories, Releases, Actions Secrets), PyPI (Python sdist & native binary wheels), and npm (Node.js CLI wrappers & scoped packages). Use whenever releasing, publishing, deploying, or packaging software to GitHub, PyPI, or npm.
---

# Package Release Pipeline: GitHub, PyPI & npm

This skill provides an automated, reproducible, and production-tested workflow for distributing multi-language software projects (such as Python + Rust extensions) across **GitHub**, **PyPI**, and **npm**.

---

## 1. Quick Decision Matrix

| Target Ecosystem | Typical Artifacts | Core Tools | Authentication / Token Format |
|---|---|---|---|
| **GitHub** | Git Source, Tags, Release Assets, Actions CI/CD | `git`, GitHub REST API, `curl` / `Invoke-RestMethod` | Personal Access Token (`ghp_...` or fine-grained `github_pat_...`) |
| **PyPI** | `sdist` (`.tar.gz`), ABI3 binary wheels (`.whl`) | `maturin`, `setuptools`, `build`, `twine` | API Token (`pypi-AgEI...`, username `__token__`) |
| **npm** | Node.js CLI wrapper, library, WebAssembly bundle | `npm`, Node.js `spawn` | Auth Token (`npm_...` configured in `.npmrc`) |

---

## 2. GitHub Distribution Workflow

### Step 2.1: Remote Configuration & Tagging
1. Verify Git remote configuration:
   ```bash
   git remote -v
   # If remote is missing:
   git remote add origin https://github.com/<owner>/<repo>.git
   ```
2. Commit clean working state and tag release:
   ```bash
   git tag -a v<version> -m "Release v<version>"
   git push origin <branch>
   git push origin v<version>
   ```

### Step 2.2: Automated Secret Injection via GitHub API
To allow GitHub Actions workflows to push to PyPI without human intervention, inject `PYPI_API_TOKEN` via the GitHub Actions Secrets API.
GitHub requires encrypting secrets using the repository's public key with libsodium SealedBox (`PyNaCl`):
- Run helper: `python scripts/set_github_secret.py --token <GH_TOKEN> --repo <owner>/<repo> --name PYPI_API_TOKEN --value <PYPI_TOKEN>`
- See [references/github_api_secrets.md](./references/github_api_secrets.md) for details.

### Step 2.3: GitHub Release & Asset Upload
Create a formal GitHub Release and attach release binaries:
```python
# Create Release via POST https://api.github.com/repos/<owner>/<repo>/releases
# Upload assets to release's upload_url
```
Use `scripts/create_github_release.py` for automated asset attachment.

---

## 3. PyPI Publishing Workflow

### Step 3.1: Artifact Building
For Python packages with native extensions (Rust/C++):
1. **Source Distribution (`sdist`)**:
   ```bash
   python -m build --sdist --outdir dist/
   # Or via maturin:
   maturin sdist --out dist/
   ```
2. **Platform Binary Wheels (`wheel`)**:
   - For universal Linux: built via `manylinux` container or GitHub Actions runner.
   - For Windows: compiled with MSVC (`win_amd64.whl`).
   - For macOS: compiled for `x86_64` and `aarch64`.
   - Prefer Python 3 stable ABI (`abi3`) to avoid compiling per-minor-version wheels:
     `calchem_qc-0.2.0-cp310-abi3-win_amd64.whl` runs on Python 3.10, 3.11, 3.12, 3.13+.

### Step 3.2: Uploading to PyPI with Twine
1. Validate artifacts:
   ```bash
   python -m twine check dist/*
   ```
2. Upload using the API token:
   ```bash
   python -m twine upload dist/* -u __token__ -p <PYPI_API_TOKEN> --skip-existing
   ```

### Step 3.3: Verification of PyPI Indexing
Verify publication worldwide:
```bash
python -m pip index versions <package_name>
# Or install in clean environment:
python -m pip install <package_name>
```

---

## 4. npm Publishing Workflow (Node.js CLI Wrapper)

For non-JavaScript engines (Python/Rust/Go/C++), distributing via npm provides users with zero-friction `npx <package>` command line execution.

### Step 4.1: CLI Wrapper Directory Structure
```text
npm/
├── bin/
│   └── calchem.js        # Executable entry point with #!/usr/bin/env node
├── index.js              # Programmatic Node.js API
├── index.d.ts            # TypeScript definitions
├── package.json          # Package manifest with "bin" and "publishConfig"
├── README.md             # npm marketplace documentation
└── LICENSE               # MIT / Apache 2.0 License
```

### Step 4.2: Critical Manifest Rules (`package.json`)
1. **Scoped Package Visibility**:
   Scoped packages (e.g. `@yangdw2024/calchem`) are private by default on npm. You **must** specify:
   ```json
   {
     "publishConfig": {
       "access": "public"
     }
   }
   ```
2. **Executable Specification**:
   ```json
   {
     "bin": {
       "calchem": "bin/calchem.js"
     }
   }
   ```
   *Note*: Use `"bin/calchem.js"` without `./` to prevent npm normalization warnings.

### Step 4.3: Self-Healing Environment Detection in `bin/`
Ensure `bin/calchem.js`:
- Probes for available and working Python 3 runtimes on Windows, Linux, and macOS.
- Checks if the underlying PyPI package is installed (`python -c "import sys, <module>; sys.exit(0)"`).
- If missing, automatically runs `pip install <package_name>` on the first invocation.
- Forwards arguments (`process.argv.slice(2)`) directly to `python -m <module>`.

### Step 4.4: Authentication & Publishing
1. Configure credentials:
   ```bash
   npm config set //registry.npmjs.org/:_authToken <NPM_TOKEN>
   npm whoami
   ```
2. Dry-run inspection:
   ```bash
   npm pack --dry-run
   ```
3. Publish to registry:
   ```bash
   npm publish --access public
   ```
4. Handle npm CDN propagation delay:
   - A new package may return 404 for 1-2 minutes while edge caches populate.
   - Use polling script `scripts/wait_npm_propagation.py` before reporting status.

---

## 5. Verification Checklist

- [ ] **GitHub**: Tagged `v*`, Release published, Assets attached, Secrets configured.
- [ ] **PyPI**: `sdist` and multi-OS `abi3` wheels visible on `https://pypi.org/project/<pkg>/`.
- [ ] **npm**: Package page live on `https://www.npmjs.com/package/<pkg>`, `npx <pkg>` verified working.
- [ ] **Cleanliness**: Build intermediates kept in isolated build directory, zero local repository pollution.
