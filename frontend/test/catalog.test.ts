import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { StaticSearchCollection } from "../src/directory/catalog";
import { CatalogSearchEngine } from "../src/directory/search-engine";
import { searchTerms } from "../src/directory/query";
import type {
  SearchManifest,
  SearchRecord,
  WorkerRequest,
  WorkerResponse,
} from "../src/directory/search-types";

const fields = {
  title: { properties: ["id", "title", "aliases"], boost: 12 },
  content: { properties: ["content"], boost: 1 },
  tags: { properties: ["topics"], boost: 4 },
};

let manifest: SearchManifest;
let records: SearchRecord[];
let failBuckets: boolean;

class TestWorker {
  private engine: CatalogSearchEngine | null = null;

  addEventListener(): void {}

  postMessage(message: WorkerRequest, transfer: Transferable[]): void {
    const port = transfer[0] as MessagePort;
    queueMicrotask(() => {
      let response: WorkerResponse;
      if (message.type === "load") {
        if (failBuckets) {
          response = {
            type: "error",
            message: "Unable to load search snapshot",
          };
        } else {
          this.engine = new CatalogSearchEngine(message.manifest, records);
          response = { type: "loaded" };
        }
      } else {
        response = {
          type: "results",
          records: this.engine!.search(message.request),
        };
      }
      port.postMessage(response);
    });
  }

  terminate(): void {}
}

function makeManifest(revision = "one"): SearchManifest {
  return {
    version: 11,
    kind: "search-records",
    revision,
    count: records.length,
    min_query_length: 2,
    fields,
    exact: ["id", "title"],
    qualifiers: {
      manager: { properties: ["managers"], match: "exact" },
      name: { properties: ["id", "title", "aliases"] },
    },
    file: `records-${revision}.json`,
  };
}

beforeEach(() => {
  Object.defineProperty(globalThis, "document", {
    configurable: true,
    value: { baseURI: "https://cpp.social/", querySelector: () => null },
  });
  Object.defineProperty(globalThis, "navigator", {
    configurable: true,
    value: {},
  });
  vi.stubGlobal("Worker", TestWorker);
  records = [
    {
      id: "fmt",
      title: "fmt",
      aliases: ["fmtlib"],
      content: "Modern formatting library",
      topics: ["formatting"],
      managers: ["conan", "vcpkg"],
      published: "2026-01-01T00:00:00",
    },
    {
      id: "format-parser",
      title: "Format parser",
      content: "Parses format strings and references fmt",
      topics: ["parsing"],
      managers: ["conan"],
      published: "2026-01-02T00:00:00",
    },
    {
      id: "range-v3",
      title: "Range v3",
      content: "Range algorithms and views for modern C++",
      topics: ["algorithms"],
      managers: ["conan"],
      published: "2026-01-03T00:00:00",
    },
    {
      id: "separated-phrase",
      title: "Modern guide to effective C++",
      content: "The queried words are deliberately separated",
      published: "2026-01-04T00:00:00",
    },
  ];
  manifest = makeManifest();
  failBuckets = false;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: URL | RequestInfo) => {
      const url = String(input);
      if (failBuckets && !url.endsWith("index.json"))
        return new Response("failed", { status: 500 });
      const value = url.endsWith("index.json") ? manifest : { records };
      return new Response(JSON.stringify(value), {
        headers: { "content-type": "application/json" },
        status: 200,
      });
    }),
  );
});

afterEach(() => vi.unstubAllGlobals());

describe("terms", () => {
  it("normalizes searchable C++ tokens", () => {
    expect(searchTerms("  C++ Café, range-v3 ")).toEqual([
      "c++",
      "café",
      "range-v3",
    ]);
  });
});

describe("catalog search", () => {
  it("ranks exact primary names ahead of references in descriptions", async () => {
    const catalog = new StaticSearchCollection("/data/packages/index.json");
    expect(
      (await catalog.search({ query: "fmt" })).map(({ id }) => id),
    ).toEqual(["fmt", "format-parser"]);
  });

  it("supports phrases, Boolean operators, prefixes, and fuzzy terms", async () => {
    const catalog = new StaticSearchCollection("/data/packages/index.json");
    expect(
      (
        await catalog.search({
          query: '("modern c++" OR pars) AND NOT beginner',
        })
      ).map(({ id }) => id),
    ).toEqual(["format-parser", "range-v3"]);
    expect((await catalog.search({ query: "algoritms" }))[0].id).toBe(
      "range-v3",
    );
    expect(
      (await catalog.search({ query: 'NOT "modern c++"' })).map(({ id }) => id),
    ).toContain("separated-phrase");
  });

  it("honors fields, manager intersections, dates, and result limits", async () => {
    const catalog = new StaticSearchCollection("/data/packages/index.json");
    expect(await catalog.search({ query: "fmt", fields: ["tags"] })).toEqual(
      [],
    );
    expect(
      (
        await catalog.search({
          query: "format",
          fields: ["all"],
          after: "2026-01-01",
          before: "2026-01-01",
          resultLimit: 1,
          qualifiers: { manager: ["conan", "vcpkg"] },
        })
      )[0].id,
    ).toBe("fmt");
    expect(
      (
        await catalog.search({
          resultLimit: Infinity,
          qualifiers: { manager: ["conan", "vcpkg"] },
        })
      ).map(({ id }) => id),
    ).toEqual(["fmt"]);
  });

  it("replaces the whole snapshot on refresh, including removals", async () => {
    const catalog = new StaticSearchCollection("/data/packages/index.json");
    expect((await catalog.search({ query: "range" }))[0].id).toBe("range-v3");

    records = [
      {
        id: "catch2",
        title: "Catch2",
        content: "Unit testing framework",
        managers: ["conan", "vcpkg"],
      },
    ];
    manifest = makeManifest("two");
    await catalog.refresh();

    expect(await catalog.search({ query: "range" })).toEqual([]);
    expect((await catalog.search({ query: "catch" }))[0].id).toBe("catch2");
  });

  it("applies author qualifiers to their declared record properties", async () => {
    records = [
      { id: "range-v3", title: "Range v3", authors: ["Eric Niebler"] },
      {
        id: "cpp-templates",
        title: "C++ Templates",
        authors: ["David Vandevoorde"],
      },
    ];
    manifest = {
      ...makeManifest(),
      fields: {
        title: { properties: ["title"], boost: 10 },
        author: { properties: ["authors"], boost: 5 },
      },
      qualifiers: { author: { properties: ["authors"] } },
    };
    const catalog = new StaticSearchCollection("/data/books/index.json");
    expect(
      (
        await catalog.search({
          qualifiers: { author: ['"Eric Niebler"'] },
        })
      ).map(({ id }) => id),
    ).toEqual(["range-v3"]);
  });

  it("applies name qualifiers independently of selected fields", async () => {
    const catalog = new StaticSearchCollection("/data/packages/index.json");
    expect(
      (
        await catalog.search({
          fields: ["content"],
          qualifiers: { name: ["fmtlib"] },
        })
      ).map(({ id }) => id),
    ).toEqual(["fmt"]);
    expect(
      (
        await catalog.search({
          fields: ["content"],
          qualifiers: { name: ['"Range v3"'] },
        })
      ).map(({ id }) => id),
    ).toEqual(["range-v3"]);
  });

  it("keeps the working generation when a replacement cannot load", async () => {
    const catalog = new StaticSearchCollection("/data/packages/index.json");
    expect((await catalog.search({ query: "range" }))[0].id).toBe("range-v3");

    records = [{ id: "catch2", title: "Catch2" }];
    manifest = makeManifest("broken");
    failBuckets = true;
    await expect(catalog.refresh()).rejects.toThrow("Unable to load");

    expect((await catalog.search({ query: "range" }))[0].id).toBe("range-v3");
  });
});
