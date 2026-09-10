export const SEARCH_FORMAT_VERSION = 11;

export type SearchFieldDefinition = {
  properties: string[];
  boost?: number;
};

export type SearchManifest = {
  version: number;
  kind: "search-records";
  revision: string;
  count: number;
  min_query_length: number;
  fields: Record<string, SearchFieldDefinition>;
  file: string;
  exact: string[];
  qualifiers: Record<
    string,
    { properties: string[]; match?: "exact" | "search" }
  >;
  [key: string]: unknown;
};

export type SearchRecord = Record<string, unknown> & {
  id: string;
};

export type CatalogSearchRequest = {
  query: string;
  fields: readonly string[];
  after: string;
  before: string;
  resultLimit: number;
  qualifiers: Record<string, readonly string[]>;
};

export type WorkerRequest =
  | {
      type: "load";
      manifestUrl: string;
      manifest: SearchManifest;
    }
  | {
      type: "search";
      request: CatalogSearchRequest;
    };

export type WorkerResponse =
  | { type: "loaded" }
  | { type: "results"; records: SearchRecord[] }
  | { type: "error"; message: string };
