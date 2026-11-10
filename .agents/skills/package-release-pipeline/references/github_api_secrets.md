# GitHub Actions Secrets Automation via API

## 1. Why Automation Is Needed
When releasing software through CI/CD pipelines (such as GitHub Actions building Windows, Linux, and macOS wheels), workflows often need credentials to upload artifacts to PyPI or npm.
Instead of requiring manual browser navigation into `Settings -> Secrets and variables -> Actions`, the agent can inject secrets programmatically via the GitHub REST API.

## 2. Encryption Mechanism: Libsodium SealedBox
GitHub requires all secret values sent to `PUT /repos/{owner}/{repo}/actions/secrets/{secret_name}` to be encrypted with the repository's public key using **Libsodium SealedBox** (`curve25519-xsalsa20-poly1305`).

### Python Implementation using `PyNaCl`:
```python
from nacl import encoding, public
import base64

def encrypt_secret(public_key_b64: str, secret_text: str) -> str:
    # 1. Decode base64 public key from GitHub
    public_key = public.PublicKey(public_key_b64.encode("utf-8"), encoding.Base64Encoder())
    # 2. Initialize SealedBox
    sealed_box = public.SealedBox(public_key)
    # 3. Encrypt secret bytes
    encrypted = sealed_box.encrypt(secret_text.encode("utf-8"))
    # 4. Encode as base64 string
    return base64.b64encode(encrypted).decode("utf-8")
```

## 3. GitHub API Flow
1. **GET Public Key**:
   `GET /repos/{owner}/{repo}/actions/secrets/public-key`
   Returns `{"key_id": "...", "key": "..."}`.
2. **Encrypt Locally**:
   Encrypt secret string with `key` into `encrypted_value`.
3. **PUT Secret**:
   `PUT /repos/{owner}/{repo}/actions/secrets/{secret_name}`
   Body: `{"encrypted_value": "...", "key_id": "..."}`.
   Response: `201 Created` or `204 No Content`.
