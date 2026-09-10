import {
  SEARCH_FORMAT_VERSION,
  type CatalogSearchRequest,
  type SearchManifest,
  type SearchRecord,
  type WorkerRequest,
  type WorkerResponse,
} from "./search-types";

const KEYED_FORMAT_VERSION = 8;
const RESULT_LIMIT = 1000;

function searchWorkerUrl(): string {
  const configured = document.querySelector<HTMLElement>("[data-search-worker]")
    ?.dataset.searchWorker;
  return (
    configured || new URL("/assets/search-worker.js", document.baseURI).href
  );
}

class SearchWorkerClient {
  private readonly rejectPending = new Set<(reason: unknown) => void>();
  private readonly worker: Worker;

  constructor(url: string) {
    this.worker = new Worker(url);
    this.worker.addEventListener("error", (event) => {
      const error = new Error(event.message || "Search worker failed");
      for (const reject of this.rejectPending) reject(error);
      this.rejectPending.clear();
    });
  }

  private send<T>(
    message: WorkerRequest,
    signal: AbortSignal | null = null,
  ): Promise<T> {
    return new Promise<T>((resolve, reject) => {
      const channel = new MessageChannel();
      const finish = (callback: () => void) => {
        signal?.removeEventListener("abort", abort);
        this.rejectPending.delete(reject);
        channel.port1.close();
        callback();
      };
      const abort = () => {
        finish(() =>
          reject(signal?.reason ?? new DOMException("Aborted", "AbortError")),
        );
      };
      if (signal?.aborted) return abort();
      signal?.addEventListener("abort", abort, { once: true });
      this.rejectPending.add(reject);
      channel.port1.onmessage = ({ data }: MessageEvent<WorkerResponse>) =>
        finish(() =>
          data.type === "error"
            ? reject(new Error(data.message))
            : resolve(
                (data.type === "results" ? data.records : undefined) as T,
              ),
        );
      this.worker.postMessage(message, [channel.port2]);
    });
  }

  load(manifestUrl: string, manifest: SearchManifest): Promise<void> {
    return this.send({ type: "load", manifestUrl, manifest });
  }

  search(
    request: CatalogSearchRequest,
    signal: AbortSignal | null,
  ): Promise<SearchRecord[]> {
    return this.send({ type: "search", request }, signal);
  }

  close(): void {
    this.worker.terminate();
    const error = new Error("Search worker was closed");
    for (const reject of this.rejectPending) reject(error);
    this.rejectPending.clear();
  }
}

export class StaticSearchCollection {
  readonly manifestUrl: URL;
  private manifestPromise: Promise<SearchManifest> | null = null;
  private preparedPromise: Promise<void> | null = null;
  private client: SearchWorkerClient | null = null;

  constructor(manifestUrl: string | URL) {
    this.manifestUrl = new URL(manifestUrl, document.baseURI);
  }

  private async fetchManifest(): Promise<SearchManifest> {
    const response = await fetch(this.manifestUrl, { cache: "no-cache" });
    if (!response.ok) throw new Error(`Unable to load ${response.url}`);
    const manifest = (await response.json()) as SearchManifest;
    if (
      manifest.version !== SEARCH_FORMAT_VERSION ||
      manifest.kind !== "search-records"
    )
      throw new Error("Unsupported search data format");
    return manifest;
  }

  manifest(): Promise<SearchManifest> {
    if (!this.manifestPromise) {
      this.manifestPromise = this.fetchManifest().catch((error: unknown) => {
        this.manifestPromise = null;
        throw error;
      });
    }
    return this.manifestPromise;
  }

  async refresh(): Promise<SearchManifest> {
    const current = await this.manifest();
    const next = await this.fetchManifest();
    if (next.revision === current.revision) {
      this.manifestPromise = Promise.resolve(next);
      return next;
    }
    if (!this.preparedPromise) {
      this.manifestPromise = Promise.resolve(next);
      return next;
    }
    await this.preparedPromise;
    const client = await this.createClient(next);
    const previousClient = this.client;
    this.client = client;
    this.manifestPromise = Promise.resolve(next);
    this.preparedPromise = Promise.resolve();
    previousClient?.close();
    this.prune(next);
    return next;
  }

  private async createClient(
    manifest: SearchManifest,
  ): Promise<SearchWorkerClient> {
    const client = new SearchWorkerClient(searchWorkerUrl());
    try {
      await client.load(this.manifestUrl.href, manifest);
      return client;
    } catch (error) {
      client.close();
      throw error;
    }
  }

  private prune(manifest: SearchManifest): void {
    navigator.serviceWorker?.controller?.postMessage({
      type: "prune-directory-data",
      base: new URL(".", this.manifestUrl).href,
      keep: ["index.json", manifest.file],
    });
  }

  private async prepare(): Promise<void> {
    if (!this.preparedPromise) {
      this.preparedPromise = (async () => {
        const manifest = await this.manifest();
        this.client = await this.createClient(manifest);
        this.prune(manifest);
      })().catch((error: unknown) => {
        this.client?.close();
        this.client = null;
        this.preparedPromise = null;
        throw error;
      });
    }
    return this.preparedPromise;
  }

  async search(
    {
      query = "",
      fields = ["all"],
      after = "",
      before = "",
      resultLimit = RESULT_LIMIT,
      qualifiers = {},
    }: Partial<CatalogSearchRequest> = {},
    signal: AbortSignal | null = null,
  ): Promise<SearchRecord[]> {
    await this.prepare();
    signal?.throwIfAborted();
    const request = {
      query,
      fields,
      after,
      before,
      resultLimit,
      qualifiers,
    };
    return this.client!.search(request, signal);
  }
}

type KeyedManifest = {
  version: number;
  kind: "keyed-records";
  bucket_count: number;
  buckets: Array<{ index: number; file: string }>;
  bucketMap?: Map<number, { index: number; file: string }>;
};

export class StaticRecordCollection {
  readonly manifestUrl: URL;
  private manifestPromise: Promise<KeyedManifest> | null = null;
  private bucketPromises = new Map<
    string,
    Promise<{ records?: Record<string, object> }>
  >();
  private encoder = new TextEncoder();

  constructor(manifestUrl: string | URL) {
    this.manifestUrl = new URL(manifestUrl, document.baseURI);
  }

  refresh(): Promise<KeyedManifest> {
    this.manifestPromise = null;
    this.bucketPromises.clear();
    return this.manifest();
  }

  manifest(): Promise<KeyedManifest> {
    if (!this.manifestPromise) {
      this.manifestPromise = fetch(this.manifestUrl, {
        cache: "no-cache",
      }).then(async (response) => {
        if (!response.ok) throw new Error(`Unable to load ${response.url}`);
        const manifest = (await response.json()) as KeyedManifest;
        if (
          manifest.version !== KEYED_FORMAT_VERSION ||
          manifest.kind !== "keyed-records"
        )
          throw new Error("Unsupported keyed record format");
        manifest.bucketMap = new Map(
          manifest.buckets.map((bucket) => [bucket.index, bucket]),
        );
        navigator.serviceWorker?.controller?.postMessage({
          type: "prune-directory-data",
          base: new URL(".", this.manifestUrl).href,
          keep: ["index.json", ...manifest.buckets.map(({ file }) => file)],
        });
        return manifest;
      });
    }
    return this.manifestPromise;
  }

  private bucketIndex(value: string, count: number): number {
    let hash = 0x811c9dc5;
    for (const byte of this.encoder.encode(value))
      hash = Math.imul(hash ^ byte, 0x01000193) >>> 0;
    return hash % count;
  }

  async record(id: string): Promise<Record<string, unknown> | null> {
    const manifest = await this.manifest();
    const descriptor = manifest.bucketMap!.get(
      this.bucketIndex(id, manifest.bucket_count),
    );
    if (!descriptor) return null;
    if (!this.bucketPromises.has(descriptor.file)) {
      this.bucketPromises.set(
        descriptor.file,
        fetch(new URL(descriptor.file, this.manifestUrl)).then(
          async (response) => {
            if (!response.ok) throw new Error(`Unable to load ${response.url}`);
            return (await response.json()) as {
              records?: Record<string, object>;
            };
          },
        ),
      );
    }
    const encoded = (await this.bucketPromises.get(descriptor.file)!).records?.[
      id
    ];
    return encoded ? { id, ...encoded } : null;
  }
}
