# The npm Zero-Install CLI Wrapper Pattern for Python / Native Tools

## 1. Problem Statement
Scientific computing tools written in Python, Rust, or C++ often require complex manual installation steps (`pip install`, setting up virtual environments, system PATH management).
For end users and CI systems, the JavaScript/npm ecosystem provides an exceptionally low-friction distribution channel: `npx <package>`.

By publishing a lightweight Node.js wrapper to npm, users can execute the tool immediately:
```bash
npx @yangdw2024/calchem doctor
```

## 2. Architecture of the CLI Wrapper
```text
npm/
├── bin/
│   └── calchem.js      <-- Executable invoked by npx / global npm
├── index.js            <-- Exported programmatic API
├── index.d.ts          <-- TypeScript definitions
├── package.json        <-- Declares "bin" and "publishConfig"
└── README.md           <-- Documentation shown on npmjs.com
```

### Key Responsibilities of `bin/calchem.js`:
1. **Shebang**: Must start with `#!/usr/bin/env node`.
2. **Runtime Discovery**:
   - Searches standard system paths for a healthy Python 3 interpreter.
   - On Windows, checks `%LOCALAPPDATA%\Programs\Python\...`, `py -3.12`, `python3`, `python`.
   - On Unix, checks `python3`, `python`.
   - Verifies the Python runtime can actually load basic DLLs (`import sys, ctypes`).
3. **Self-Healing Bootstrap**:
   - Checks if the underlying PyPI package (e.g. `calchem-qc`) is installed.
   - If missing, automatically runs `pip install calchem-qc` on the first run.
4. **Transparent Forwarding**:
   - Forwards all command-line arguments to `python -m <module> ...args` with `{ stdio: 'inherit' }`.
   - Propagates exit codes and termination signals cleanly.

## 3. npm Registry Gotchas
1. **Scoped Packages are Private by Default**:
   Must include in `package.json`:
   ```json
   "publishConfig": { "access": "public" }
   ```
2. **Path Normalization in `bin`**:
   Use `"bin": { "calchem": "bin/calchem.js" }` rather than `./bin/calchem.js` to avoid `npm warn publish` stripping notices.
3. **Edge CDN Replication Delay**:
   npm registry uses worldwide edge caching. Newly created packages often return HTTP 404 for 60-120 seconds after a successful `npm publish`. Always poll the registry before testing or reporting completion.
