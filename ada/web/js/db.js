// IndexedDB: offline catalog cache and the outbox of sales made without internet.
const DB_NAME = 'ada', VERSION = 1;
let dbp;

function open() {
  dbp ??= new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains('kv')) db.createObjectStore('kv');
      if (!db.objectStoreNames.contains('outbox')) db.createObjectStore('outbox', { keyPath: 'client_ref' });
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
  return dbp;
}

async function tx(store, mode, fn) {
  const db = await open();
  return new Promise((resolve, reject) => {
    const t = db.transaction(store, mode);
    const result = fn(t.objectStore(store));
    t.oncomplete = () => resolve(result instanceof IDBRequest ? result.result : result);
    t.onerror = () => reject(t.error);
  });
}

export const kv = {
  get: (k) => tx('kv', 'readonly', s => s.get(k)),
  set: (k, v) => tx('kv', 'readwrite', s => s.put(v, k)),
  del: (k) => tx('kv', 'readwrite', s => s.delete(k)),
};

export const outbox = {
  add: (sale) => tx('outbox', 'readwrite', s => s.put(sale)),
  all: () => tx('outbox', 'readonly', s => s.getAll()),
  remove: (ref) => tx('outbox', 'readwrite', s => s.delete(ref)),
  count: () => tx('outbox', 'readonly', s => s.count()),
};

export async function wipe() {
  await tx('kv', 'readwrite', s => s.clear());
}
