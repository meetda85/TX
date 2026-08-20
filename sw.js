/* ==========================================================================
   Service worker de Tiempo Extra — TWR MEX

   Guarda el programa entero en el navegador para que la app instalada abra
   aunque no esté corriendo el lanzador, y aunque no haya red. Los datos que
   capturas no pasan por aquí: ésos viven en localStorage.
   ========================================================================== */
'use strict';

//: Al cambiar el programa se sube este número y se tira la caché vieja.
const CACHE = 'tx-twr-v1';

const DEL_PROGRAMA = [
  './',
  './Tiempo Extra.html',
  './manifest.webmanifest',
  './icono-192.png',
  './icono-512.png',
  './icono-512-lleno.png',
];

self.addEventListener('install', (e) => {
  //: addAll falla entero si un archivo falta; se piden uno por uno para que la
  //: instalación no se caiga por un ícono.
  e.waitUntil(caches.open(CACHE)
    .then((c) => Promise.all(DEL_PROGRAMA.map((u) => c.add(u).catch(() => null))))
    .then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys()
    .then((claves) => Promise.all(claves.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', (e) => {
  const pide = e.request;
  if (pide.method !== 'GET' || new URL(pide.url).origin !== self.location.origin) return;

  //: Primero la red, y si no hay, lo guardado. Así una versión nueva del
  //: programa se ve en cuanto el lanzador está corriendo, en vez de quedarse
  //: pegado a la copia vieja hasta que alguien limpie la caché.
  e.respondWith(
    fetch(pide)
      .then((res) => {
        if (res && res.ok) {
          const copia = res.clone();
          caches.open(CACHE).then((c) => c.put(pide, copia));
        }
        return res;
      })
      .catch(() => caches.match(pide, { ignoreSearch: true })
        .then((hit) => hit || caches.match('./Tiempo Extra.html'))));
});
