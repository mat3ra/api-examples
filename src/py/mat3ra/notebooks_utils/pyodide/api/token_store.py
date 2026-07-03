"""IndexedDB-based OIDC token cache for Pyodide Web Workers."""

import json

from pyodide.code import run_js  # type: ignore

_idb = run_js(
    """
(function() {
    const open = () => new Promise(resolve => {
        const req = indexedDB.open("mat3ra", 1);
        req.onupgradeneeded = () => req.result.createObjectStore("tokens");
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => resolve(null);
    });
    return {
        get: async () => {
            const db = await open();
            if (!db) return null;
            return new Promise(resolve => {
                const g = db.transaction("tokens").objectStore("tokens").get("oidc_cache");
                g.onsuccess = () => { db.close(); resolve(g.result || null); };
                g.onerror = () => { db.close(); resolve(null); };
            });
        },
        set: async (data) => {
            const db = await open();
            if (!db) return;
            const tx = db.transaction("tokens", "readwrite");
            tx.objectStore("tokens").put(data, "oidc_cache");
            return new Promise(resolve => { tx.oncomplete = () => { db.close(); resolve(); }; });
        }
    };
})()
"""
)


async def read() -> dict:
    result = await _idb.get()
    return json.loads(str(result)) if result else {}


async def write(cache: dict) -> None:
    await _idb.set(json.dumps(cache))
