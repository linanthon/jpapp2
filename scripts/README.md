# Scripts

## 1. Upload audio fragments to MinIO/S3

File: `scripts/upload_audio_to_storage.py`

Uploads local files from `data/audio` into object storage.
Default object key format:

- `audio/fragments/<filename>`

Examples:

```powershell
# Dry-run (no upload)
python scripts/upload_audio_to_storage.py --dry-run

# Upload missing files only (idempotent)
python scripts/upload_audio_to_storage.py

# Force overwrite all files
python scripts/upload_audio_to_storage.py --overwrite
```

## 2. Clear browser HTTP cache for testing

File: `scripts/clear_browser_http_cache.ps1`

Important limitation:

- Browsers do not expose a safe CLI/API to remove cache entries for only one origin/file in normal HTTP cache.
- This script clears cache folders for one browser profile (not just this app's files).

Examples:

```powershell
# Preview + confirm prompt, change value of -Browser for different ones
powershell -ExecutionPolicy Bypass -File scripts/clear_browser_http_cache.ps1 -Browser edge -Profile Default

# Skip prompt
powershell -ExecutionPolicy Bypass -File scripts/clear_browser_http_cache.ps1 -Browser edge -Profile Default -Force
```

What is cleared:

- Chromium-based: `Cache/Cache_Data`, `Code Cache`, `GPUCache` for selected profile.
- Firefox: `cache2` for selected profile.

## Browser cache locations on Windows (common)

Edge (Default profile):

- `%LOCALAPPDATA%\Microsoft\Edge\User Data\Default\Cache\Cache_Data`
- `%LOCALAPPDATA%\Microsoft\Edge\User Data\Default\Code Cache`
- `%LOCALAPPDATA%\Microsoft\Edge\User Data\Default\GPUCache`

Chrome (Default profile):

- `%LOCALAPPDATA%\Google\Chrome\User Data\Default\Cache\Cache_Data`
- `%LOCALAPPDATA%\Google\Chrome\User Data\Default\Code Cache`
- `%LOCALAPPDATA%\Google\Chrome\User Data\Default\GPUCache`

Firefox (default profile):

- `%LOCALAPPDATA%\Mozilla\Firefox\Profiles\<profile>.default*\cache2`

Opera (Default profile):

- `%LOCALAPPDATA%\Opera Software\Opera Stable\Cache\Cache_Data`
- `%LOCALAPPDATA%\Opera Software\Opera Stable\Code Cache`
- `%LOCALAPPDATA%\Opera Software\Opera Stable\GPUCache`
