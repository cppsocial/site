import { describe, expect, it } from "vitest";

import {
  DIRECTORY_QUALIFIERS,
  normalizeText,
  parseDirectoryQuery,
  parseSearchQuery,
  matchesSearch,
  searchMatchQuality,
  searchTerms,
  setQualifier,
} from "../src/directory/query";

describe("directory query parsing", () => {
  it("normalizes Unicode and preserves C++-specific token characters", () => {
    expect(normalizeText("  CAFÉ   C++ ")).toBe("café c++");
    expect(searchTerms("range-v3 C++ foo_bar")).toEqual([
      "range-v3",
      "c++",
      "foo_bar",
    ]);
  });

  it("supports exact phrases, fuzzy prefixes, and boolean expressions", () => {
    const query = parseSearchQuery(
      '("modern c++" OR template) AND NOT beginner',
    );
    expect(matchesSearch(query, ["Modern C++ Design"])).toBe(true);
    expect(matchesSearch(query, ["Template metaprogramming"])).toBe(true);
    expect(matchesSearch(query, ["Modern C++ for beginners"])).toBe(false);
    expect(
      matchesSearch(parseSearchQuery("metaprog"), ["metaprogramming"]),
    ).toBe(true);
    expect(
      matchesSearch(parseSearchQuery("metaprogrmming"), ["metaprogramming"]),
    ).toBe(true);
    expect(
      matchesSearch(parseSearchQuery('"meta prog"'), ["metaprogramming"]),
    ).toBe(false);
  });

  it("extracts manager qualifiers without duplicating catalog validation", () => {
    const result = parseDirectoryQuery(
      "json manager:Conan manager:unknown manager:vcpkg",
    );
    expect(result.qualifiers.manager).toEqual(["conan", "unknown", "vcpkg"]);
    expect(result.text).toBe("json");
  });

  it("extracts field-scoped author qualifiers including exact names", () => {
    const result = parseDirectoryQuery(
      'reflection author:"Jason Turner" author:cppweekly',
    );
    expect(result.text).toBe("reflection");
    expect(result.qualifiers.author).toEqual(['"Jason Turner"', "cppweekly"]);
    expect(parseDirectoryQuery('author:""').qualifiers.author).toEqual([]);
  });

  it("accepts catalog-specific qualifier registries", () => {
    const result = parseDirectoryQuery("tag:templates author:name", {
      tag: { parse: (value) => value },
      author: DIRECTORY_QUALIFIERS.author,
    });
    expect(result.qualifiers).toEqual({ tag: ["templates"], author: ["name"] });
    expect(result.text).toBe("");
  });

  it("keeps manager qualifiers inline when controls toggle them", () => {
    expect(setQualifier("json", "manager", "conan", true)).toBe(
      "json manager:conan",
    );
    expect(setQualifier("json manager:conan", "manager", "conan", false)).toBe(
      "json",
    );
  });

  it("ranks title matches ahead of description-only references", () => {
    const expression = parseSearchQuery("fmt");
    expect(
      searchMatchQuality(expression, [
        { values: ["fmt"] },
        { values: ["formatting"], base: 8 },
      ]),
    ).toBeLessThan(
      searchMatchQuality(expression, [
        { values: ["parser"] },
        { values: ["mentions fmt"], base: 8 },
      ]),
    );
  });
});
