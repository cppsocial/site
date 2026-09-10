const ARTWORK_CACHE = "external-images-v2";
const DIRECTORY_CACHE = "directory-data-v11";
const worker = self as unknown as ServiceWorkerGlobalScope;

worker.addEventListener("install", () => worker.skipWaiting());

worker.addEventListener("activate", (event: ExtendableEvent) => {
  event.waitUntil(
    caches
      .keys()
      .then((names) =>
        Promise.all(
          names
            .filter(
              (name) =>
                ((name.startsWith("youtube-artwork-") ||
                  name.startsWith("external-images-")) &&
                  name !== ARTWORK_CACHE) ||
                (name.startsWith("directory-data-") &&
                  name !== DIRECTORY_CACHE),
            )
            .map((name) => caches.delete(name)),
        ),
      )
      .then(() => worker.clients.claim()),
  );
});

worker.addEventListener("fetch", (event: FetchEvent) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET") return;
  if (
    event.request.mode === "navigate" &&
    url.origin === worker.location.origin
  ) {
    const scope = new URL(worker.registration.scope);
    event.respondWith(
      fetchDocument(event.request, url.pathname === scope.pathname),
    );
    return;
  }
  if (
    event.request.destination === "image" &&
    url.origin !== worker.location.origin
  ) {
    event.respondWith(cacheArtwork(event.request));
    return;
  }
  if (
    url.origin === worker.location.origin &&
    url.pathname.includes("/data/")
  ) {
    event.respondWith(
      url.pathname.endsWith("/index.json")
        ? refreshDirectoryData(event.request)
        : cacheDirectoryChunk(event.request),
    );
  }
});

async function fetchDocument(
  request: Request,
  isolate: boolean,
): Promise<Response> {
  const response = await fetch(request);
  const headers = new Headers(response.headers);
  if (isolate) {
    headers.set("Cross-Origin-Embedder-Policy", "credentialless");
    headers.set("Cross-Origin-Opener-Policy", "same-origin");
  } else {
    headers.delete("Cross-Origin-Embedder-Policy");
    headers.delete("Cross-Origin-Opener-Policy");
  }
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

async function cacheArtwork(request: Request): Promise<Response> {
  const cache = await caches.open(ARTWORK_CACHE);
  let cached: Response | undefined;
  try {
    cached = await cache.match(request.url);
  } catch (error) {
    console.warn("Could not read cached artwork", request.url, error);
  }
  if (cached) {
    return cached;
  }

  const response = await fetch(
    new Request(request.url, {
      mode: "no-cors",
      cache: "force-cache",
      credentials: "omit",
      referrerPolicy: "no-referrer",
    }),
  );
  const contentType = response.headers.get("content-type") || "";
  if (
    response.type === "opaque" ||
    (response.ok && contentType.startsWith("image/"))
  ) {
    try {
      await cache.put(request.url, response.clone());
    } catch (error) {
      console.warn("Could not cache artwork", request.url, error);
    }
  }
  return response;
}

async function cacheDirectoryChunk(request: Request): Promise<Response> {
  const cache = await caches.open(DIRECTORY_CACHE);
  const cached = await cache.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  if (response.ok) await cache.put(request, response.clone());
  return response;
}

async function refreshDirectoryData(request: Request): Promise<Response> {
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

interface PruneMessage {
  base: string;
  keep: string[];
  type: "prune-directory-data";
}

worker.addEventListener("message", (event: ExtendableMessageEvent) => {
  const message = event.data as Partial<PruneMessage>;
  if (
    message.type !== "prune-directory-data" ||
    typeof message.base !== "string" ||
    !Array.isArray(message.keep)
  )
    return;
  const base = new URL(message.base, worker.location.origin).href;
  const keep = new Set(message.keep.map((name) => new URL(name, base).href));
  event.waitUntil(
    caches.open(DIRECTORY_CACHE).then(async (cache) => {
      const requests = await cache.keys();
      await Promise.all(
        requests
          .filter(
            (request) => request.url.startsWith(base) && !keep.has(request.url),
          )
          .map((request) => cache.delete(request)),
      );
    }),
  );
});
