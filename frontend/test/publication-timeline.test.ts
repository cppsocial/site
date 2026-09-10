import { describe, expect, it } from "vitest";

import {
  publicationBounds,
  publicationBuckets,
} from "../src/directory/publication-timeline";

const records = [
  { id: "one", published: "2024-01-03" },
  { id: "two", published: "2024-01-12" },
  { id: "three", published: "2024-02-29" },
  { id: "four", published: "2023-06-01" },
];

describe("publication timeline", () => {
  it("drills from years into months and seven-day ranges", () => {
    expect(
      publicationBuckets(records, {}).map(({ key, count }) => [key, count]),
    ).toEqual([
      ["2023", 1],
      ["2024", 3],
    ]);
    expect(
      publicationBuckets(records, { year: "2024" }).map(({ key, count }) => [
        key,
        count,
      ]),
    ).toEqual([
      ["01", 2],
      ["02", 1],
    ]);
    expect(
      publicationBuckets(records, { year: "2024", month: "01" }).map(
        ({ label, start, end, count }) => [label, start, end, count],
      ),
    ).toEqual([
      ["Jan 1\u20137", "2024-01-01", "2024-01-07", 1],
      ["Jan 8\u201314", "2024-01-08", "2024-01-14", 1],
    ]);
  });

  it("uses the selected parent period when refreshing a level", () => {
    expect(publicationBounds({})).toEqual({ after: "", before: "" });
    expect(publicationBounds({ year: "2024" })).toEqual({
      after: "2024-01-01",
      before: "2024-12-31",
    });
    expect(publicationBounds({ year: "2024", month: "02", week: "2" })).toEqual(
      { after: "2024-02-01", before: "2024-02-29" },
    );
  });
});
