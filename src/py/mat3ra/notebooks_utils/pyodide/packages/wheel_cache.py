"""IndexedDB-based wheel cache for Pyodide package installations.

Caches downloaded wheel files in IndexedDB so they persist across kernel
restarts. On subsequent installs, wheels are loaded from cache and written
to emfs for local installation (no network download needed).
"""

import json

try:
    from pyodide.code import run_js  # type: ignore
    from pyodide.ffi import to_js  # type: ignore

    _HAS_PYODIDE = True
except ImportError:
    run_js = None  # type: ignore
    to_js = None  # type: ignore
    _HAS_PYODIDE = False


_cache = (
    run_js(
        """
(function() {
    const DB_NAME = "mat3ra";
    const DB_VERSION = 2;
    const MANIFEST_STORE = "wheel_manifest";
    const WHEEL_STORE = "wheel_data";

    const open = () => new Promise((resolve, reject) => {
        const req = indexedDB.open(DB_NAME, DB_VERSION);
        req.onupgradeneeded = (event) => {
            const db = event.target.result;
            if (!db.objectStoreNames.contains("tokens")) {
                db.createObjectStore("tokens");
            }
            if (!db.objectStoreNames.contains(MANIFEST_STORE)) {
                db.createObjectStore(MANIFEST_STORE);
            }
            if (!db.objectStoreNames.contains(WHEEL_STORE)) {
                db.createObjectStore(WHEEL_STORE);
            }
        };
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
    });

    return {
        getManifest: async () => {
            const db = await open();
            return new Promise(resolve => {
                const tx = db.transaction(MANIFEST_STORE);
                const req = tx.objectStore(MANIFEST_STORE).get("manifest");
                req.onsuccess = () => { db.close(); resolve(req.result || null); };
                req.onerror = () => { db.close(); resolve(null); };
            });
        },

        setManifest: async (data) => {
            const db = await open();
            const tx = db.transaction(MANIFEST_STORE, "readwrite");
            tx.objectStore(MANIFEST_STORE).put(data, "manifest");
            return new Promise(resolve => {
                tx.oncomplete = () => { db.close(); resolve(); };
            });
        },

        getWheel: async (key) => {
            const db = await open();
            return new Promise(resolve => {
                const tx = db.transaction(WHEEL_STORE);
                const req = tx.objectStore(WHEEL_STORE).get(key);
                req.onsuccess = () => { db.close(); resolve(req.result || null); };
                req.onerror = () => { db.close(); resolve(null); };
            });
        },

        putWheel: async (key, data) => {
            const db = await open();
            const tx = db.transaction(WHEEL_STORE, "readwrite");
            tx.objectStore(WHEEL_STORE).put(data, key);
            return new Promise(resolve => {
                tx.oncomplete = () => { db.close(); resolve(); };
            });
        },

        clear: async () => {
            const db = await open();
            const tx = db.transaction([MANIFEST_STORE, WHEEL_STORE], "readwrite");
            tx.objectStore(MANIFEST_STORE).clear();
            tx.objectStore(WHEEL_STORE).clear();
            return new Promise(resolve => {
                tx.oncomplete = () => { db.close(); resolve(); };
            });
        }
    };
})()
"""
    )
    if _HAS_PYODIDE
    else None
)


async def read_manifest() -> dict:
    """
    Read the cache manifest from IndexedDB.

    The manifest maps cache keys (wheel URLs) to metadata (filename, size, cached_at).
    It also stores the '_requirements_hash' of the currently installed packages profile,
    which survives kernel restarts and lets us skip running micropip if unchanged.
    """
    result = await _cache.getManifest()
    return json.loads(str(result)) if result else {}


async def write_manifest(manifest: dict) -> None:
    """
    Write the cache manifest back to IndexedDB as a JSON string.
    """
    await _cache.setManifest(json.dumps(manifest))


async def get_cached_wheel(cache_key: str):
    """
    Retrieve cached wheel bytes from IndexedDB, or None if not cached.

    Returns standard Python bytes by converting the JS Uint8Array proxy object
    using .to_bytes() for high-performance memory translation.
    """
    result = await _cache.getWheel(cache_key)
    if result is None:
        return None
    return result.to_bytes()


async def put_cached_wheel(cache_key: str, wheel_bytes: bytes) -> None:
    """
    Store wheel bytes in IndexedDB.

    Converts Python bytes to a JS Uint8Array using to_js() to ensure
    zero-copy buffer transfer and avoid slow byte-by-byte duplication.
    """
    await _cache.putWheel(cache_key, to_js(wheel_bytes))


async def clear_cache() -> None:
    """
    Wipe all cached wheels and the manifest from IndexedDB.
    """
    await _cache.clear()
