const escapeRegExp = (value: string) =>
  value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

type QualifierDefinition = {
  parse: (value: string) => string | null;
  quoted?: boolean;
};

export const DIRECTORY_QUALIFIERS: Record<string, QualifierDefinition> = {
  author: {
    parse: (value) => (normalizeText(value.replace(/^"|"$/g, "")) ? value : ""),
    quoted: true,
  },
  manager: {
    parse: (value) => normalizeText(value.replace(/^"|"$/g, "")),
  },
  name: {
    parse: (value) => (normalizeText(value.replace(/^"|"$/g, "")) ? value : ""),
    quoted: true,
  },
};

export function normalizeText(value: unknown): string {
  return String(value ?? "")
    .normalize("NFKC")
    .toLocaleLowerCase()
    .trim()
    .replace(/\s+/g, " ");
}

export function searchTerms(value: unknown): string[] {
  return normalizeText(value).match(/[\p{L}\p{N}_+#.-]+/gu) ?? [];
}

export type SearchExpression =
  | { type: "term"; value: string; exact: boolean }
  | { type: "not"; child: SearchExpression }
  | { type: "and" | "or"; left: SearchExpression; right: SearchExpression };

type Token =
  | { type: "term"; value: string; exact: boolean }
  | { type: "and" | "or" | "not" | "left" | "right" };

function queryTokens(value: unknown): Token[] {
  const input = String(value ?? "");
  const result: Token[] = [];
  const pattern = /\s*("(?:[^"\\]|\\.)*"|\(|\)|[^\s()]+)/gy;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(input))) {
    const raw = match[1];
    const operator = raw.toLocaleLowerCase();
    if (raw === "(") result.push({ type: "left" });
    else if (raw === ")") result.push({ type: "right" });
    else if (["and", "or", "not"].includes(operator))
      result.push({ type: operator as "and" | "or" | "not" });
    else {
      const exact = raw.startsWith('"') && raw.endsWith('"');
      const normalized = normalizeText(
        exact ? raw.slice(1, -1).replace(/\\"/g, '"') : raw,
      );
      if (normalized)
        result.push({
          type: "term",
          value: normalized,
          exact,
        });
    }
  }
  return result;
}

export function parseSearchQuery(value: unknown): SearchExpression | null {
  const tokens = queryTokens(value);
  let offset = 0;
  const primary = (): SearchExpression | null => {
    const token = tokens[offset];
    if (!token) return null;
    if (token.type === "not") {
      offset += 1;
      const child = primary();
      return child ? { type: "not", child } : null;
    }
    if (token.type === "left") {
      offset += 1;
      const child = or();
      if (tokens[offset]?.type === "right") offset += 1;
      return child;
    }
    if (token.type === "term") {
      offset += 1;
      return token;
    }
    return null;
  };
  const and = (): SearchExpression | null => {
    let left = primary();
    while (left && offset < tokens.length) {
      const token = tokens[offset];
      if (token.type === "or" || token.type === "right") break;
      if (token.type === "and") offset += 1;
      const right = primary();
      if (!right) break;
      left = { type: "and", left, right };
    }
    return left;
  };
  const or = (): SearchExpression | null => {
    let left = and();
    while (left && tokens[offset]?.type === "or") {
      offset += 1;
      const right = and();
      if (!right) break;
      left = { type: "or", left, right };
    }
    return left;
  };
  return or();
}

export function expressionTerms(expression: SearchExpression | null): string[] {
  if (!expression) return [];
  if (expression.type === "term") return searchTerms(expression.value);
  if (expression.type === "not") return expressionTerms(expression.child);
  return [
    ...expressionTerms(expression.left),
    ...expressionTerms(expression.right),
  ];
}

export function matchesSearch(
  expression: SearchExpression | null,
  values: unknown[],
): boolean {
  if (!expression) return true;
  const haystacks = values.map(normalizeText);
  const evaluate = (node: SearchExpression): boolean => {
    if (node.type === "term") {
      if (node.exact)
        return haystacks.some((haystack) => haystack.includes(node.value));
      const wanted = searchTerms(node.value);
      const available = haystacks.flatMap(searchTerms);
      return wanted.every((term) =>
        available.some((candidate) => fuzzyTermMatch(term, candidate)),
      );
    }
    if (node.type === "not") return !evaluate(node.child);
    return node.type === "and"
      ? evaluate(node.left) && evaluate(node.right)
      : evaluate(node.left) || evaluate(node.right);
  };
  return evaluate(expression);
}

function positiveSearchTerms(
  expression: SearchExpression | null,
): SearchExpression[] {
  if (!expression) return [];
  if (expression.type === "term") return [expression];
  if (expression.type === "not") return [];
  return [
    ...positiveSearchTerms(expression.left),
    ...positiveSearchTerms(expression.right),
  ];
}

function termQuality(term: SearchExpression, values: unknown[]): number {
  if (term.type !== "term") return 99;
  const normalized = values.map(normalizeText).filter(Boolean);
  if (normalized.some((value) => value === term.value)) return 0;
  if (term.exact)
    return normalized.some((value) => value.includes(term.value)) ? 2 : 99;
  const candidates = normalized.flatMap(searchTerms);
  const wanted = searchTerms(term.value);
  if (wanted.length && wanted.every((value) => candidates.includes(value)))
    return 3;
  return wanted.length &&
    wanted.every((value) =>
      candidates.some((candidate) => fuzzyTermMatch(value, candidate)),
    )
    ? 5
    : 99;
}

/** A stable hard ranking tier for rendered, non-catalog search results. */
export function searchMatchQuality(
  expression: SearchExpression | null,
  groups: Array<{ values: unknown[]; base?: number }>,
): number {
  let best = 99;
  for (const term of positiveSearchTerms(expression)) {
    for (const group of groups) {
      best = Math.min(
        best,
        (group.base ?? 0) + termQuality(term, group.values),
      );
    }
  }
  return best;
}

function fuzzyTermMatch(term: string, candidate: string): boolean {
  if (candidate.startsWith(term)) return true;
  const allowance = fuzzyDistance(term);
  if (!allowance || Math.abs(term.length - candidate.length) > allowance)
    return false;
  let previous = Array.from(
    { length: candidate.length + 1 },
    (_, index) => index,
  );
  for (let left = 1; left <= term.length; left += 1) {
    const current = [left];
    let rowMinimum = left;
    for (let right = 1; right <= candidate.length; right += 1) {
      current[right] = Math.min(
        current[right - 1] + 1,
        previous[right] + 1,
        previous[right - 1] + Number(term[left - 1] !== candidate[right - 1]),
      );
      rowMinimum = Math.min(rowMinimum, current[right]);
    }
    if (rowMinimum > allowance) return false;
    previous = current;
  }
  return previous[candidate.length] <= allowance;
}

export function fuzzyDistance(term: string): number {
  return term.length >= 8 ? 2 : term.length >= 4 ? 1 : 0;
}

export function parseDirectoryQuery(
  value: unknown,
  definitions: Record<string, QualifierDefinition> = DIRECTORY_QUALIFIERS,
): {
  qualifiers: Record<string, string[]>;
  text: string;
} {
  const qualifiers = Object.fromEntries(
    Object.keys(definitions).map((name) => [name, [] as string[]]),
  );
  const names = Object.keys(definitions).map(escapeRegExp).join("|");
  if (!names) return { qualifiers, text: String(value ?? "").trim() };
  const text = String(value ?? "").replace(
    new RegExp(
      `(^|\\s)(${names}):("(?:[^"\\\\]|\\\\.)*"|[^\\s()]+)(?=\\s|$)`,
      "gi",
    ),
    (match, spacing: string, name: string, raw: string) => {
      const qualifier = name.toLocaleLowerCase();
      const parsed = definitions[qualifier].parse(raw);
      if (parsed === null) return match;
      if (parsed) qualifiers[qualifier].push(parsed);
      return spacing;
    },
  );
  return {
    qualifiers,
    text: text.replace(/\s+/g, " ").trim(),
  };
}

/** Add or remove an inline qualifier without hiding it from the text input. */
export function setQualifier(
  value: unknown,
  name: string,
  qualifierValue: string,
  enabled: boolean,
): string {
  const normalized = qualifierValue.toLocaleLowerCase();
  const without = String(value ?? "")
    .replace(
      new RegExp(
        `(^|\\s)${escapeRegExp(name)}:${escapeRegExp(normalized)}(?=\\s|$)`,
        "gi",
      ),
      "$1",
    )
    .replace(/\s+/g, " ")
    .trim();
  return enabled
    ? [without, `${name}:${normalized}`].filter(Boolean).join(" ")
    : without;
}
