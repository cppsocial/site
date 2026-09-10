import { TemplateDialogController } from "../shared/dialog";
import { parseJsonScript, queryRequired } from "../shared/dom";
import { initStoredChoice } from "../shared/choice";

type Rating = { average: number; count: number; status: string };
type BookCopy = Record<string, string>;

type BookRecord = Record<string, unknown> & {
  id: string;
  title?: string;
  authors?: string[];
  subjects?: string[];
};

const value = (input: unknown): string => String(input ?? "");

function optionalText(root: ParentNode, selector: string, text: string): void {
  const element = queryRequired<HTMLElement>(root, selector);
  if (!text) element.remove();
  else
    (element.querySelector<HTMLElement>("dd, p") ?? element).textContent = text;
}

export function createBookCard(record: BookRecord): HTMLElement {
  const source = queryRequired<HTMLTemplateElement>(
    document,
    "[data-book-card-template]",
  );
  const fragment = source.content.cloneNode(true) as DocumentFragment;
  const card = queryRequired<HTMLElement>(fragment, "article");
  const title = value(record.title);
  const isbn = value(record.isbn_13 || record.id);
  const authors = record.authors?.join(", ") ?? "";
  const cover = value(record.cover_url);
  const publisher = value(record.publisher);
  const publishDate = value(record.publish_date);
  const published = value(record.published);
  const url = value(record.url);
  const workKey = value(record.work_key);
  const subjects = record.subjects?.slice(0, 8).join(", ") ?? "";
  const subtitle = value(record.subtitle);
  const description = value(record.description);
  const isbn10 = value(record.isbn_10);
  const pages = value(record.pages);
  const rating = Number(record.rating);
  const ratingCount = Number(record.rating_count);
  const retailerIsbn = encodeURIComponent(String(record.isbn_13 || record.id));

  queryRequired<HTMLElement>(card, "[data-book-title]").textContent = title;
  queryRequired<HTMLElement>(card, "[data-book-authors]").textContent = authors;
  queryRequired<HTMLElement>(card, "[data-book-isbn]").append(` ${isbn}`);
  const opener = queryRequired<HTMLElement>(card, "[data-book-open]");
  opener.setAttribute("aria-label", `${opener.dataset.label} ${title}`);
  optionalText(card, "[data-book-subtitle]", subtitle);
  optionalText(card, "[data-book-description]", description);
  optionalText(card, "[data-book-card-publisher]", publisher);
  const publishedRow = queryRequired<HTMLElement>(
    card,
    "[data-book-card-published]",
  );
  if (publishDate) {
    const cardTime = queryRequired<HTMLTimeElement>(publishedRow, "time");
    cardTime.textContent = publishDate;
    cardTime.dateTime = published;
  } else publishedRow.remove();

  const cardCover = queryRequired<HTMLImageElement>(
    card,
    "[data-book-card-cover]",
  );
  const noCover = queryRequired<HTMLElement>(card, "[data-book-no-cover]");
  if (cover) {
    cardCover.src = cover;
    cardCover.alt = `${cardCover.dataset.label} ${title}`;
    noCover.remove();
  } else cardCover.remove();

  const detailsTemplate = queryRequired<HTMLTemplateElement>(
    card,
    "[data-book-details]",
  );
  const detail = queryRequired<HTMLElement>(
    detailsTemplate.content,
    ".book-detail",
  );
  detail.dataset.workKey = workKey;
  detail.dataset.isbn = isbn;
  detail.dataset.openLibraryUrl = url;
  if (Number.isFinite(rating)) {
    detail.dataset.openLibraryRating = String(rating);
    detail.dataset.openLibraryCount = String(ratingCount);
  }
  queryRequired<HTMLElement>(detail, "[data-book-detail-title]").textContent =
    title;
  queryRequired<HTMLElement>(detail, "[data-book-detail-authors]").append(
    ` ${authors}`,
  );
  queryRequired<HTMLElement>(detail, "[data-book-detail-isbn]").textContent =
    isbn;
  optionalText(detail, "[data-book-detail-subtitle]", subtitle);
  optionalText(detail, "[data-book-detail-isbn-10]", isbn10);
  optionalText(detail, "[data-book-detail-publisher]", publisher);
  optionalText(detail, "[data-book-detail-published]", publishDate);
  optionalText(detail, "[data-book-detail-pages]", pages);
  optionalText(detail, "[data-book-detail-subjects]", subjects);

  const detailCover = queryRequired<HTMLImageElement>(
    detail,
    "[data-book-detail-cover]",
  );
  const coverFallback = queryRequired<HTMLElement>(
    detail,
    "[data-book-cover-fallback]",
  );
  if (cover) {
    detailCover.src = cover;
    detailCover.alt = `${detailCover.dataset.label} ${title}`;
    coverFallback.remove();
  } else detailCover.remove();

  for (const link of detail.querySelectorAll<HTMLAnchorElement>(
    "[data-book-url]",
  ))
    link.href = url;
  const retailers = {
    amazon: `https://www.amazon.com/s?k=${retailerIsbn}&i=stripbooks`,
    bookshop: `https://bookshop.org/search?keywords=${retailerIsbn}`,
    barnesNoble: `https://www.barnesandnoble.com/s/${retailerIsbn}`,
    abebooks: `https://www.abebooks.com/servlet/SearchResults?isbn=${retailerIsbn}`,
  };
  for (const [name, href] of Object.entries(retailers))
    queryRequired<HTMLAnchorElement>(detail, `[data-retailer="${name}"]`).href =
      href;
  const retailerNav = queryRequired<HTMLElement>(
    detail,
    "[data-book-retailers]",
  );
  retailerNav.setAttribute(
    "aria-label",
    `${retailerNav.dataset.label} ${title}`,
  );
  return card;
}

async function loadRating(
  detail: HTMLElement,
  copy: BookCopy,
): Promise<Rating> {
  const cached = {
    average: Number(detail.dataset.openLibraryRating),
    count: Number(detail.dataset.openLibraryCount),
  };
  try {
    if (!detail.dataset.workKey) throw new Error("No Open Library work key");
    const response = await fetch(
      `https://openlibrary.org${detail.dataset.workKey}/ratings.json`,
    );
    if (!response.ok)
      throw new Error(`Open Library returned ${response.status}`);
    const result = (await response.json()) as {
      summary?: { average?: number; count?: number };
    };
    return {
      average: Number(result.summary?.average),
      count: Number(result.summary?.count),
      status: copy.retrieved_live,
    };
  } catch (error) {
    console.warn("Could not refresh Open Library rating", error);
    return Number.isFinite(cached.average) && cached.count
      ? { ...cached, status: copy.cached_rating }
      : { average: 0, count: 0, status: copy.unavailable };
  }
}

async function refreshRating(
  detail: HTMLElement,
  copy: BookCopy,
): Promise<void> {
  const rating = await loadRating(detail, copy);
  const container = detail.querySelector<HTMLElement>(
    "[data-book-rating-sources]",
  );
  const value = container?.querySelector<HTMLElement>(
    "[data-book-rating-value]",
  );
  if (!container || !value || !detail.isConnected) return;
  value.textContent = rating.count
    ? [
        `${rating.average.toFixed(1)} / 5 · ${rating.count.toLocaleString()} ${copy.ratings_suffix}`,
        rating.status,
      ].join(" · ")
    : rating.status || copy.no_public_ratings;
  container.removeAttribute("aria-busy");
}

function initBookDialog(): TemplateDialogController | null {
  const dialog =
    document.querySelector<HTMLDialogElement>("[data-book-dialog]");
  const content = dialog?.querySelector<HTMLElement>(
    "[data-book-dialog-content]",
  );
  if (!dialog || !content) return null;
  const copy = parseJsonScript<BookCopy>(document, "[data-book-copy]");
  return new TemplateDialogController({
    cardSelector: "[data-book-card]",
    closeSelector: "[data-book-close]",
    content,
    dialog,
    documentClass: "has-book-dialog",
    openSelector: "[data-book-open]",
    templateSelector: "[data-book-details]",
    afterOpen: ({ content: dialogContent }) => {
      const detail = dialogContent.querySelector<HTMLElement>(".book-detail");
      if (detail) void refreshRating(detail, copy);
    },
  });
}

type BookLayout = "cards" | "list";

function initBookLayout(): void {
  const catalog = document.querySelector<HTMLElement>(".books-catalog");
  const buttons = [
    ...document.querySelectorAll<HTMLButtonElement>("[data-book-view]"),
  ];
  if (!catalog || !buttons.length) return;

  initStoredChoice<BookLayout>({
    apply: (layout) => (catalog.dataset.bookLayout = layout),
    buttons,
    initial: "cards",
    storageKey: "book-layout",
    value: (button) => (button.dataset.bookView === "list" ? "list" : "cards"),
  });
}

export function initBooks(): void {
  initBookLayout();
  initBookDialog();
}
