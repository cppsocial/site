const ARTWORK_CACHE = "external-images-v2";
const DIRECTORY_CACHE = "directory-data-v8";

self.addEventListener("install", () => self.skipWaiting());

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((names) => Promise.all(
      names
        .filter((name) => (
          (name.startsWith("youtube-artwork-") || name.startsWith("external-images-"))
          && name !== ARTWORK_CACHE
        ) || (
          name.startsWith("directory-data-") && name !== DIRECTORY_CACHE
        ))
        .map((name) => caches.delete(name)),
    )).then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET") return;
  if (event.request.destination === "image" && url.origin !== self.location.origin) {
    event.respondWith(cacheArtwork(event.request));
    return;
  }
  if (url.origin === self.location.origin && url.pathname.includes("/data/")) {
    event.respondWith(url.pathname.endsWith("/index.json")
      ? refreshDirectoryData(event.request)
      : cacheDirectoryChunk(event.request));
  }
});

async function cacheArtwork(request) {
  const cache = await caches.open(ARTWORK_CACHE);
  const cached = await cache.match(request.url);
  if (cached) {
    return cached;
  }

  const response = await fetch(new Request(request.url, {
    mode: "no-cors",
    cache: "force-cache",
    credentials: "omit",
    referrerPolicy: "no-referrer",
  }));
  const contentType = response.headers.get("content-type") || "";
  if (response.type === "opaque" || response.ok && contentType.startsWith("image/")) {
    await cache.put(request.url, response.clone());
  }
  return response;
}

async function cacheDirectoryChunk(request) {
  const cache = await caches.open(DIRECTORY_CACHE);
  const cached = await cache.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  if (response.ok) await cache.put(request, response.clone());
  return response;
}

async function refreshDirectoryData(request) {
  const cache = await caches.open(DIRECTORY_CACHE);
  try {
    const response = await fetch(request);
    if (response.ok) await cache.put(request, response.clone());
    return response;
  } catch (error) {
    const cached = await cache.match(request);
    if (cached) return cached;
    throw error;
  }
}


self.addEventListener("message", (event) => {
  if (event.data?.type !== "prune-directory-data") return;
  const base = new URL(event.data.base, self.location.origin).href;
  const keep = new Set(event.data.keep.map(
    (name) => new URL(name, base).href,
  ));
  event.waitUntil(
    caches.open(DIRECTORY_CACHE).then(async (cache) => {
      const requests = await cache.keys();
      await Promise.all(requests
        .filter((request) => request.url.startsWith(base) && !keep.has(request.url))
        .map((request) => cache.delete(request)));
    }),
  );
});
