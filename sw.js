// Service Worker für Offline-Fähigkeit — Brückenprüfung KIB-Prüfer & Karten-App
// Strategie: Cache-first mit Hintergrund-Aktualisierung (stale-while-revalidate).
// Da beide Apps als einzelne HTML-Dateien mit eingebetteten Bildern/CSS/JS
// ausgeliefert werden, genügt es, genau diese eine Anfrage pro App zu cachen.

const CACHE_NAME = 'bp-offline-v2';

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
    caches.match(event.request).then((cached) => {
      const fetchPromise = fetch(event.request)
        .then((networkResponse) => {
          if (networkResponse && networkResponse.status === 200) {
            const clone = networkResponse.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
          }
          return networkResponse;
        })
        .catch(() => cached);
      // Sofort aus dem Cache antworten, falls vorhanden (schnell + offline-fähig).
      // Im Hintergrund trotzdem versuchen, eine frische Version zu laden und zu speichern.
      return cached || fetchPromise;
    })
  );
});
