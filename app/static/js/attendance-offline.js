/**
 * Coffee Estate Offline Attendance Queue & Idempotent Sync
 * Uses IndexedDB to store offline punches and synchronizes via POST /api/attendance/sync
 */

const DB_NAME = 'CoffeeEstateAttendanceDB';
const DB_VERSION = 1;
const STORE_NAME = 'attendance_events';

let dbInstance = null;

// Initialize IndexedDB
function openDatabase() {
  return new Promise((resolve, reject) => {
    if (dbInstance) return resolve(dbInstance);

    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = (event) => {
      const db = event.target.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: 'event_uuid' });
      }
    };
    request.onsuccess = (event) => {
      dbInstance = event.target.result;
      resolve(dbInstance);
    };
    request.onerror = (event) => reject(event.target.error);
  });
}

// Add event to local offline queue
async function queueOfflineEvent(eventData) {
  const db = await openDatabase();
  return new Promise((resolve, reject) => {
    const tx = db.transaction([STORE_NAME], 'readwrite');
    const store = tx.objectStore(STORE_NAME);
    if (!eventData.event_uuid) {
      eventData.event_uuid = (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : 'offline-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
    }
    eventData.queued_at = new Date().toISOString();
    store.put(eventData);

    tx.oncomplete = () => {
      updateOfflineUI();
      resolve(eventData.event_uuid);
    };
    tx.onerror = () => reject(tx.error);
  });
}

// Retrieve all queued offline events
async function getAllQueuedEvents() {
  const db = await openDatabase();
  return new Promise((resolve, reject) => {
    const tx = db.transaction([STORE_NAME], 'readonly');
    const store = tx.objectStore(STORE_NAME);
    const req = store.getAll();
    req.onsuccess = () => resolve(req.result || []);
    req.onerror = () => reject(req.error);
  });
}

// Clear synced events
async function clearSyncedEvents(eventUuids) {
  const db = await openDatabase();
  return new Promise((resolve, reject) => {
    const tx = db.transaction([STORE_NAME], 'readwrite');
    const store = tx.objectStore(STORE_NAME);
    eventUuids.forEach(id => store.delete(id));
    tx.oncomplete = () => {
      updateOfflineUI();
      resolve();
    };
    tx.onerror = () => reject(tx.error);
  });
}

// Update offline badge in DOM
async function updateOfflineUI() {
  const badge = document.getElementById('offlineQueueBadge');
  const countSpan = document.getElementById('offlineCountSpan');
  if (!badge) return;

  const events = await getAllQueuedEvents();
  if (events.length > 0) {
    badge.classList.remove('d-none');
    if (countSpan) countSpan.innerText = events.length;
  } else {
    badge.classList.add('d-none');
  }

  const connStatus = document.getElementById('connectionStatusText');
  if (connStatus) {
    if (navigator.onLine) {
      connStatus.innerHTML = '<span class="text-success"><i class="bi bi-wifi"></i> Online</span>';
    } else {
      connStatus.innerHTML = '<span class="text-danger"><i class="bi bi-wifi-off"></i> Offline Mode</span>';
    }
  }
}

// Synchronize with server idempotently
async function syncOfflineQueue() {
  if (!navigator.onLine) {
    console.log('[OfflineSync] Device is offline; sync skipped.');
    return;
  }

  const events = await getAllQueuedEvents();
  if (events.length === 0) return;

  console.log(`[OfflineSync] Attempting sync of ${events.length} records...`);

  try {
    const response = await fetch('/api/attendance/sync', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        events: events,
        device_id: navigator.userAgent.slice(0, 50)
      })
    });

    if (response.ok) {
      const result = await response.json();
      console.log('[OfflineSync] Sync success:', result);
      const syncedIds = events.map(e => e.event_uuid);
      await clearSyncedEvents(syncedIds);

      // Show toast alert
      if (window.showSyncToast) {
        window.showSyncToast(result.synced, result.conflicts);
      }
    }
  } catch (err) {
    console.warn('[OfflineSync] Sync failed (network error). Retrying later.', err);
  }
}

// Listen for network connectivity events
window.addEventListener('online', () => {
  updateOfflineUI();
  syncOfflineQueue();
});
window.addEventListener('offline', () => {
  updateOfflineUI();
});

// Initialize on page load
window.addEventListener('DOMContentLoaded', () => {
  openDatabase().then(() => {
    updateOfflineUI();
    if (navigator.onLine) {
      syncOfflineQueue();
    }
  });
});
