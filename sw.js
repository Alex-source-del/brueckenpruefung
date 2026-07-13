// Service Worker für Offline-Fähigkeit — Brückenprüfung KIB-Prüfer & Karten-App
// Strategie: Netzwerk-zuerst mit Cache als Rückfalloption ("network-first").
// Bei Internetverbindung wird immer zuerst versucht, die aktuelle Version zu laden —
// dadurch sind Updates sofort nach dem Hochladen sichtbar, ohne Cache-leeren oder
// mehrfaches Neuladen. Nur wenn kein Netz da ist (Baustelle/Funkloch), greift die App
// auf die zuletzt gespeicherte Version zurück — Offline-Fähigkeit bleibt also erhalten.
// (Vorher: cache-first mit Hintergrund-Aktualisierung — zeigte neue Versionen immer
// erst beim ÜBERNÄCHSTEN Laden an, das war der Grund für das Cache-Theater.)

const CACHE_NAME = 'bp-offline-v3';

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;

  event.respondWith(
    fetch(event.request)
      .then((networkResponse) => {
        if (networkResponse && networkResponse.status === 200) {
          const clone = networkResponse.clone();
          // waitUntil sorgt dafür, dass der Browser den Speichervorgang wirklich
          // abschließen lässt, statt ihn ggf. abzubrechen — sonst könnte der
          // Offline-Rückfall unzuverlässig werden, weil nichts im Cache landet.
          event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone)));
        }
        return networkResponse;
      })
      .catch(() => caches.match(event.request))
  );
});
