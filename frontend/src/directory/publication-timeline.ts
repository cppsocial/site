import type { SearchRecord } from "./search-types";

export type PublicationSelection = {
  year?: string;
  month?: string;
  week?: string;
};

export type PublicationBucket = {
  key: string;
  label: string;
  start: string;
  end: string;
  count: number;
};

const monthFormatter = new Intl.DateTimeFormat("en", {
  month: "short",
  timeZone: "UTC",
});

function monthEnd(year: string, month: string): number {
  return new Date(Date.UTC(Number(year), Number(month), 0)).getUTCDate();
}

export function publicationBounds(selection: PublicationSelection): {
  after: string;
  before: string;
} {
  if (!selection.year) return { after: "", before: "" };
  if (!selection.month) {
    return {
      after: `${selection.year}-01-01`,
      before: `${selection.year}-12-31`,
    };
  }
  const last = String(monthEnd(selection.year, selection.month)).padStart(
    2,
    "0",
  );
  return {
    after: `${selection.year}-${selection.month}-01`,
    before: `${selection.year}-${selection.month}-${last}`,
  };
}

export function publicationBuckets(
  records: readonly SearchRecord[],
  selection: PublicationSelection,
): PublicationBucket[] {
  const counts = new Map<string, number>();
  for (const record of records) {
    const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(
      String(record.published ?? ""),
    );
    if (!match) continue;
    const [, year, month, day] = match;
    if (selection.year && year !== selection.year) continue;
    if (selection.month && month !== selection.month) continue;
    const key = !selection.year
      ? year
      : !selection.month
        ? month
        : String(Math.floor((Number(day) - 1) / 7) + 1);
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }

  return [...counts.entries()]
    .sort(([left], [right]) =>
      left.localeCompare(right, undefined, { numeric: true }),
    )
    .map(([key, count]) => {
      if (!selection.year) {
        return {
          key,
          label: key,
          start: `${key}-01-01`,
          end: `${key}-12-31`,
          count,
        };
      }
      if (!selection.month) {
        const last = String(monthEnd(selection.year, key)).padStart(2, "0");
        return {
          key,
          label: monthFormatter.format(
            new Date(Date.UTC(Number(selection.year), Number(key) - 1, 1)),
          ),
          start: `${selection.year}-${key}-01`,
          end: `${selection.year}-${key}-${last}`,
          count,
        };
      }
      const firstDay = (Number(key) - 1) * 7 + 1;
      const lastDay = Math.min(
        firstDay + 6,
        monthEnd(selection.year, selection.month),
      );
      const monthLabel = monthFormatter.format(
        new Date(
          Date.UTC(Number(selection.year), Number(selection.month) - 1, 1),
        ),
      );
      return {
        key,
        label: `${monthLabel} ${firstDay}\u2013${lastDay}`,
        start: `${selection.year}-${selection.month}-${String(firstDay).padStart(2, "0")}`,
        end: `${selection.year}-${selection.month}-${String(lastDay).padStart(2, "0")}`,
        count,
      };
    });
}
