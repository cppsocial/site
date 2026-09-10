import MiniSearch, { type Query } from "minisearch";

import {
  fuzzyDistance,
  matchesSearch,
  normalizeText,
  parseSearchQuery,
  searchTerms,
  type SearchExpression,
} from "./query";
import type {
  CatalogSearchRequest,
  SearchFieldDefinition,
  SearchManifest,
  SearchRecord,
} from "./search-types";

function searchableValue(value: unknown): unknown {
  return typeof value === "string" && value.includes("<")
    ? value.replace(/<[^>]*>/g, " ").replace(/&(?:amp|lt|gt|quot|#39);/gi, " ")
    : value;
}

function values(record: SearchRecord, names: readonly string[]): unknown[] {
  return names.flatMap((name) => {
    const value = record[name];
    return (Array.isArray(value) ? value : [value]).map(searchableValue);
  });
}

function miniSearchQuery(expression: SearchExpression, negated = false): Query {
  if (expression.type === "term") {
    if (expression.exact && negated) return MiniSearch.wildcard;
    const query: Query = expression.exact
      ? {
          queries: searchTerms(expression.value),
          combineWith: "AND",
          prefix: false,
          fuzzy: false,
        }
      : expression.value;
    return negated
      ? { queries: [MiniSearch.wildcard, query], combineWith: "AND_NOT" }
      : query;
  }
  if (expression.type === "not")
    return miniSearchQuery(expression.child, !negated);
  return {
    queries: [
      miniSearchQuery(expression.left, negated),
      miniSearchQuery(expression.right, negated),
    ],
    combineWith: (negated
      ? expression.type === "and"
        ? "OR"
        : "AND"
      : expression.type
    ).toUpperCase() as "AND" | "OR",
  };
}

function hasPhrase(expression: SearchExpression): boolean {
  if (expression.type === "term") return expression.exact;
  if (expression.type === "not") return hasPhrase(expression.child);
  return hasPhrase(expression.left) || hasPhrase(expression.right);
}

export class CatalogSearchEngine {
  private readonly records = new Map<string, SearchRecord>();
  private readonly fields: Array<SearchFieldDefinition & { name: string }>;
  private readonly qualifierFields: Map<
    string,
    {
      name: string;
      definition: SearchManifest["qualifiers"][string];
    }
  >;
  private readonly index: MiniSearch<SearchRecord>;

  constructor(
    private readonly manifest: SearchManifest,
    records: SearchRecord[],
  ) {
    this.qualifierFields = new Map(
      Object.entries(manifest.qualifiers).map(([name, definition]) => [
        name,
        { name: `qualifier:${name}`, definition },
      ]),
    );
    this.fields = Object.entries(manifest.fields).map(([name, definition]) => ({
      name,
      ...definition,
    }));
    const fields = new Map(this.fields.map((field) => [field.name, field]));
    this.index = new MiniSearch({
      fields: [
        ...this.fields.map(({ name }) => name),
        ...[...this.qualifierFields.values()].map(({ name }) => name),
      ],
      tokenize: searchTerms,
      processTerm: normalizeText,
      extractField: (record, name) => {
        const field = fields.get(name);
        if (field) return values(record, field.properties).join(" ");
        const qualifier = this.qualifierFields.get(
          name.slice("qualifier:".length),
        );
        return qualifier
          ? values(record, qualifier.definition.properties).join(" ")
          : record[name];
      },
    });
    for (const record of records) this.records.set(record.id, record);
    this.index.addAll(records);
  }

  private selected(
    requested: readonly string[],
  ): Array<SearchFieldDefinition & { name: string }> {
    const names = new Set(requested);
    return requested.includes("all")
      ? this.fields
      : this.fields.filter(({ name }) => names.has(name));
  }

  search(request: CatalogSearchRequest): SearchRecord[] {
    const expression = parseSearchQuery(request.query);
    const selected = this.selected(request.fields);
    if (expression && !selected.length) return [];
    const queries: Query[] = [
      expression ? miniSearchQuery(expression) : MiniSearch.wildcard,
    ];
    const phraseChecks: Array<[SearchExpression, readonly string[]]> = [];
    if (expression && hasPhrase(expression))
      phraseChecks.push([
        expression,
        selected.flatMap(({ properties }) => properties),
      ]);
    for (const [name, wanted] of Object.entries(request.qualifiers)) {
      if (!wanted.length) continue;
      const field = this.qualifierFields.get(name);
      if (!field) return [];
      for (const value of wanted) {
        const parsed = parseSearchQuery(value);
        if (!parsed) continue;
        queries.push({
          queries: [miniSearchQuery(parsed)],
          fields: [field.name],
          combineWith: "AND",
          ...(field.definition.match === "exact"
            ? { prefix: false, fuzzy: false }
            : {}),
        });
        if (hasPhrase(parsed))
          phraseChecks.push([parsed, field.definition.properties]);
      }
    }
    const query: Query =
      queries.length === 1 ? queries[0] : { queries, combineWith: "AND" };
    const scored = this.index.search(query, {
      fields: selected.map(({ name }) => name),
      boost: Object.fromEntries(
        selected.map((field) => [field.name, field.boost ?? 1]),
      ),
      prefix: true,
      fuzzy: (term) => fuzzyDistance(term) || false,
      weights: { prefix: 0.7, fuzzy: 0.45 },
      boostDocument: (id, term) =>
        values(this.records.get(String(id))!, this.manifest.exact).some(
          (value) => normalizeText(value) === term,
        )
          ? 100
          : 1,
      filter: ({ id }) => {
        const record = this.records.get(String(id))!;
        return (
          (!request.after || String(record.published ?? "") >= request.after) &&
          (!request.before ||
            String(record.published ?? "") <= `${request.before}T23:59:59`)
        );
      },
    });
    const matches = scored
      .map(({ id }) => this.records.get(String(id))!)
      .filter((record) =>
        phraseChecks.every(([phrase, properties]) =>
          matchesSearch(phrase, values(record, properties)),
        ),
      );
    if (!expression)
      matches.sort(
        (left, right) =>
          String(right.published ?? "").localeCompare(
            String(left.published ?? ""),
          ) || left.id.localeCompare(right.id),
      );
    const limited = Number.isFinite(request.resultLimit)
      ? matches.slice(0, request.resultLimit)
      : matches;
    return limited;
  }
}
