/// <reference lib="webworker" />

import { CatalogSearchEngine } from "../directory/search-engine";
import {
  SEARCH_FORMAT_VERSION,
  type SearchRecord,
  type WorkerRequest,
  type WorkerResponse,
} from "../directory/search-types";

const scope = self as unknown as DedicatedWorkerGlobalScope;
let engine: CatalogSearchEngine | null = null;

scope.addEventListener("message", (event: MessageEvent<WorkerRequest>) => {
  const message = event.data;
  const port = event.ports[0];
  void (async () => {
    if (message.type === "load") {
      if (
        message.manifest.version !== SEARCH_FORMAT_VERSION ||
        message.manifest.kind !== "search-records"
      )
        throw new Error("Unsupported search data format");
      const base = new URL(".", message.manifestUrl);
      const response = await fetch(new URL(message.manifest.file, base));
      if (!response.ok) throw new Error(`Unable to load ${response.url}`);
      const payload = (await response.json()) as { records?: SearchRecord[] };
      if (!Array.isArray(payload.records))
        throw new Error(`Invalid search snapshot: ${message.manifest.file}`);
      engine = new CatalogSearchEngine(message.manifest, payload.records);
      port.postMessage({ type: "loaded" } satisfies WorkerResponse);
      return;
    }
    if (!engine) throw new Error("Search index is not loaded");
    port.postMessage({
      type: "results",
      records: engine.search(message.request),
    } satisfies WorkerResponse);
  })().catch((error: unknown) => {
    port.postMessage({
      type: "error",
      message: error instanceof Error ? error.message : String(error),
    } satisfies WorkerResponse);
  });
});
