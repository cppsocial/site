import { createFeedCards } from "./feed-cards";
import { createPackageCatalog } from "./package-details";
import { StaticSearchCollection } from "./catalog";
import {
  DIRECTORY_QUALIFIERS,
  expressionTerms,
  matchesSearch,
  parseDirectoryQuery,
  parseSearchQuery,
  searchMatchQuality,
  setQualifier,
} from "./query";
import { createBookCard } from "./books";
import { createText, eventElement } from "../shared/dom";
import {
  publicationBounds,
  publicationBuckets,
  type PublicationSelection,
} from "./publication-timeline";

export function initDirectory(): void {
  "use strict";

  const directory = document.querySelector<HTMLElement>("[data-directory]");
  const input = document.querySelector<HTMLInputElement>(
    "[data-directory-input]",
  );
  const clear = document.querySelector<HTMLButtonElement>(
    "[data-directory-clear]",
  );
  const searchHighlight = document.querySelector<HTMLElement>(
    "[data-search-highlight]",
  );
  const status = document.querySelector<HTMLElement>("[data-directory-status]");
  const packageMatchSummary = document.querySelector<HTMLElement>(
    "[data-package-match-summary]",
  );
  if (!directory || !input || !clear || !status) return;

  const directoryCopy = JSON.parse(
    directory.querySelector("[data-directory-copy]").textContent,
  );
  const copy = directoryCopy.search;
  const cardCopy = directoryCopy.cards;
  const packageCopyNode = directory.querySelector("[data-package-copy]");
  const packageCopy = packageCopyNode
    ? JSON.parse(packageCopyNode.textContent)
    : {};
  const sections = Array.from(
    directory.querySelectorAll<HTMLElement>("[data-directory-section]"),
  );
  const hasPackageSection = sections.some(
    (section) => section.dataset.deferredKind === "package",
  );
  const deferred = new Map();
  const fieldInputs = Array.from(
    document.querySelectorAll<HTMLInputElement>("[data-search-field]"),
  );
  const afterInput = document.querySelector<HTMLInputElement>(
    "[data-search-after]",
  );
  const beforeInput = document.querySelector<HTMLInputElement>(
    "[data-search-before]",
  );
  const categoryInputs = Array.from(
    document.querySelectorAll<HTMLInputElement>("input[data-search-category]"),
  );
  const managerChoices = Array.from(
    document.querySelectorAll<HTMLButtonElement>(
      "[data-search-manager-choice]",
    ),
  );
  const managerLabels = new Map(
    managerChoices.map((choice) => [choice.value, choice.textContent.trim()]),
  );
  const supportsManagerQualifier = managerChoices.length > 0;
  const supportsAuthorQualifier =
    !hasPackageSection &&
    sections.some(
      (section) =>
        ["book", "blog-post", "youtube-video"].includes(
          section.dataset.deferredKind || "",
        ) || Boolean(section.querySelector("[data-search-source]")),
    );
  const qualifierParsers = Object.fromEntries(
    [
      supportsManagerQualifier && "manager",
      supportsAuthorQualifier && "author",
      hasPackageSection && "name",
    ]
      .filter(Boolean)
      .map((name) => [name, DIRECTORY_QUALIFIERS[name]]),
  );
  const includeUnrelatedInput = document.querySelector<HTMLInputElement>(
    "[data-search-include-unrelated]",
  );
  const blogAvatars = new Map(
    Array.from(
      document.querySelectorAll<HTMLElement>("[data-blog-avatar-source]"),
    ).map((element) => [
      element.dataset.blogAvatarSource,
      element.dataset.blogAvatar,
    ]),
  );
  const advanced = document.querySelector<HTMLButtonElement>(
    "[data-search-advanced]",
  );
  const options = document.querySelector<HTMLElement>("[data-search-options]");
  const publicationTimeline = document.querySelector<HTMLElement>(
    "[data-publication-timeline]",
  );
  const emptyMessage = directory.dataset.emptyMessage;
  const minimumQueryLength = 2;
  const now = new Date();
  const today = [
    now.getFullYear(),
    String(now.getMonth() + 1).padStart(2, "0"),
    String(now.getDate()).padStart(2, "0"),
  ].join("-");
  let items = [];
  let itemsBySection = new Map();
  let searchGeneration = 0;
  let searchController = null;
  let pendingPackageId = "";
  let publicationSelection: PublicationSelection = {};
  let publicationMatches = [];
  const originalItemOrder = new WeakMap<HTMLElement, number>();
  let nextItemOrder = 0;

  for (const control of [afterInput, beforeInput].filter(Boolean)) {
    control.max = today;
  }
  if (beforeInput && !beforeInput.value) beforeInput.value = today;
  if (options && !options.hasAttribute("data-search-inline"))
    document.body.append(options);

  function updateManagerControls(managers) {
    for (const choice of managerChoices) {
      choice.setAttribute("aria-pressed", String(managers.has(choice.value)));
    }
  }

  function renderSearchHighlight() {
    if (!searchHighlight) return;
    searchHighlight.replaceChildren();
    const qualifiers = Object.keys(qualifierParsers);
    const qualified = qualifiers.length
      ? `\\b(?:${qualifiers.join("|")}):(?:"(?:[^"\\\\]|\\\\.)*(?:"|$)|[^\\s()]*)`
      : "";
    const pattern = new RegExp(
      `${qualified}${qualified ? "|" : ""}"(?:[^"\\\\]|\\\\.)*"|\\b(?:AND|OR|NOT)\\b|[()]`,
      "gi",
    );
    let offset = 0;
    for (const match of input.value.matchAll(pattern)) {
      const index = match.index ?? 0;
      searchHighlight.append(input.value.slice(offset, index));
      const syntax = document.createElement("span");
      syntax.textContent = match[0];
      const kind = match[0].startsWith('"')
        ? "exact"
        : match[0].includes(":")
          ? "qualifier"
          : "operator";
      syntax.className = `directory-search__syntax directory-search__syntax--${kind}`;
      searchHighlight.append(syntax);
      offset = index + match[0].length;
    }
    searchHighlight.append(input.value.slice(offset), "\u200b");
    searchHighlight.scrollLeft = input.scrollLeft;
  }

  function openQualifierValue() {
    if (input.selectionStart !== input.selectionEnd) return;
    const cursor = input.selectionStart ?? 0;
    const name = Object.keys(qualifierParsers).find(
      (qualifier) =>
        qualifierParsers[qualifier].quoted &&
        new RegExp(`(?:^|\\s)${qualifier}:$`, "i").test(
          input.value.slice(0, cursor),
        ),
    );
    if (!name) return;
    input.setRangeText('""', cursor, cursor, "end");
    input.setSelectionRange(cursor + 1, cursor + 1);
  }

  function detailManifestKey(manifest) {
    return (manifest?.buckets || [])
      .map((bucket) => `${bucket.index}:${bucket.revision}`)
      .join("|");
  }

  function invalidatePackageDetails(state) {
    state.section.querySelectorAll(".package-entry").forEach((entry) => {
      delete entry.dataset.detailsLoaded;
      const body = entry.querySelector(".package-entry__body");
      if (!body) return;
      const loading = createText(
        document.createDocumentFragment(),
        "p",
        copy.open_to_load,
      );
      loading.className = "package-entry__loading";
      body.replaceChildren(loading);
      if (entry.open) entry.dispatchEvent(new Event("toggle"));
    });
  }

  function scrollToPackage(card) {
    const offset = [".header", ".directory-header", ".directory-search"]
      .map((selector) => document.querySelector<HTMLElement>(selector))
      .filter((element): element is HTMLElement => Boolean(element))
      .reduce((bottom, element) => {
        const style = getComputedStyle(element);
        if (!["fixed", "sticky"].includes(style.position)) return bottom;
        return Math.max(
          bottom,
          (Number.parseFloat(style.top) || 0) + element.offsetHeight,
        );
      }, 0);
    window.scrollTo({
      top: window.scrollY + card.getBoundingClientRect().top - offset - 12,
      behavior: "smooth",
    });
  }

  function filters() {
    const before = beforeInput?.value || "";
    const qualified = parseDirectoryQuery(input.value, qualifierParsers);
    const expression = parseSearchQuery(qualified.text);
    const managers = new Set(qualified.qualifiers.manager || []);
    updateManagerControls(managers);
    return {
      query: qualified.text,
      expression,
      terms: expressionTerms(expression),
      fields: fieldInputs.length
        ? fieldInputs
            .filter((control) => control.checked)
            .map((control) => control.value)
        : ["all"],
      after: afterInput?.value || "",
      before,
      dateActive: Boolean(afterInput?.value || (before && before !== today)),
      categories: new Set(
        categoryInputs
          .filter((control) => control.checked)
          .map((control) => control.value),
      ),
      managers,
      qualifiers: qualified.qualifiers,
      includeUnrelated: includeUnrelatedInput?.checked ?? true,
    };
  }

  function sectionItems(section) {
    return itemsBySection.get(section) || [];
  }

  function refreshItems() {
    items = Array.from(directory.querySelectorAll("[data-directory-item]"));
    itemsBySection = new Map(sections.map((section) => [section, []]));
    for (const item of items) {
      if (!originalItemOrder.has(item))
        originalItemOrder.set(item, nextItemOrder++);
      const section = item.closest("[data-directory-section]");
      if (section) itemsBySection.get(section)?.push(item);
    }
    for (const section of sections) {
      sectionItems(section)
        .filter((item) => item.hasAttribute("data-browse-item"))
        .forEach((item, index) => {
          item.dataset.pageIndex = String(index);
        });
    }
  }

  const { blogPost, youtubeVideo } = createFeedCards({
    blogAvatars,
    continueReadingLabel: directory.dataset.continueReadingLabel,
    copy,
    cardCopy,
  });

  const packageCatalog = createPackageCatalog({
    copy,
    packageCopy,
    managerLabels,
    selectDependency: async (id, name, href) => {
      pendingPackageId = id;
      input.value = name;
      history.replaceState(null, "", href);
      await update();
    },
    selectManager: async (manager) => {
      input.value = setQualifier(input.value, "manager", manager, true);
      await update();
      input.focus();
    },
    selectTopic: async (topic) => {
      input.value = topic;
      await update();
      input.focus();
    },
  });
  const managerLabel =
    packageCatalog.managerLabel ||
    ((value) => managerLabels.get(value) || value);
  const packageEntry = packageCatalog.packageEntry;

  function renderRecord(state, record, browse) {
    let card = state.section.querySelector(
      `[data-record-id="${CSS.escape(record.id)}"]`,
    );
    if (!card) {
      card =
        state.kind === "blog-post"
          ? blogPost(record)
          : state.kind === "package"
            ? packageEntry(record, state)
            : state.kind === "book"
              ? createBookCard(record)
              : youtubeVideo(record);
      card.dataset.directoryItem = "";
      card.dataset.recordId = record.id;
      card.hidden = !browse;
      if (state.kind === "package") card.id = record.id;
      state.grid.append(card);
    }
    if (record.cpp_relevance == null) {
      delete card.dataset.cppRelevance;
    } else {
      card.dataset.cppRelevance = String(record.cpp_relevance);
    }
    card.dataset.managers = (record.managers || []).join(" ");
    if (state.kind === "package" && record.id === pendingPackageId) {
      pendingPackageId = "";
      card.open = true;
      requestAnimationFrame(() => {
        scrollToPackage(card);
      });
    }
    if (browse) {
      card.dataset.browseItem = "";
      card.dataset.pagedItem = "";
      delete card.dataset.searchOnly;
    } else if (!card.hasAttribute("data-browse-item")) {
      card.dataset.searchOnly = "";
    }
    return card;
  }

  async function loadIndex(state) {
    if (!state.source) {
      state.source = new StaticSearchCollection(state.url);
    }
    state.index = await state.source.manifest();
    if (state.kind === "book") renderPublicationTimeline(state.index);
    return state.index;
  }

  function renderPublicationTimeline(manifest, records = null, force = false) {
    if (
      !publicationTimeline ||
      (!records && publicationTimeline.childElementCount && !force)
    )
      return;
    const buckets = records
      ? publicationBuckets(records, publicationSelection)
      : Object.entries(manifest.date_histogram || {})
          .map(([year, count]) => ({
            key: year,
            label: year,
            start: `${year}-01-01`,
            end: `${year}-12-31`,
            count: Number(count),
          }))
          .filter(({ count }) => count > 0);
    if (!buckets.length && !publicationTimeline.childElementCount) return;
    publicationTimeline.replaceChildren();
    const maximum = Math.max(...buckets.map(({ count }) => count), 1);
    const all = createText(publicationTimeline, "button", copy.all_years_label);
    all.type = "button";
    all.className = "directory-search__timeline-reset";
    all.addEventListener("click", () => {
      publicationSelection = {};
      if (afterInput) afterInput.value = "";
      if (beforeInput) beforeInput.value = today;
      synchronizeDateBounds(undefined);
      renderPublicationTimeline(manifest, null, true);
      update();
    });
    const bars = document.createElement("div");
    bars.className = "directory-search__timeline-bars";
    const level = !publicationSelection.year
      ? "year"
      : !publicationSelection.month
        ? "month"
        : "week";
    bars.dataset.timelineLevel = level;
    for (const bucket of buckets) {
      const button = createText(bars, "button", bucket.label);
      button.type = "button";
      button.title = `${bucket.label}: ${bucket.count}`;
      button.setAttribute("aria-label", `${bucket.label}: ${bucket.count}`);
      button.style.setProperty(
        "--publication-count",
        String(bucket.count / maximum),
      );
      const selected =
        (level === "year" && publicationSelection.year === bucket.key) ||
        (level === "month" && publicationSelection.month === bucket.key) ||
        (level === "week" && publicationSelection.week === bucket.key);
      if (selected) button.setAttribute("aria-current", "true");
      button.addEventListener("click", () => {
        if (level === "year") publicationSelection = { year: bucket.key };
        else if (level === "month")
          publicationSelection = {
            year: publicationSelection.year,
            month: bucket.key,
          };
        else
          publicationSelection = {
            ...publicationSelection,
            week: bucket.key,
          };
        if (afterInput) afterInput.value = bucket.start;
        if (beforeInput) beforeInput.value = bucket.end;
        synchronizeDateBounds(undefined);
        renderPublicationTimeline(manifest, publicationMatches);
        update();
      });
    }
    publicationTimeline.append(bars);
  }

  async function searchRecords(state, current, resultLimit, signal = null) {
    await loadIndex(state);
    signal?.throwIfAborted();
    return state.source.search(
      {
        query: current.query,
        fields: current.fields,
        after: current.after,
        before: current.before,
        resultLimit,
        qualifiers: current.qualifiers,
      },
      signal,
    );
  }

  async function renderRecords(state, records, browse, signal = null) {
    let yieldAfter = performance.now() + 12;
    const rendered = [];
    for (const record of records) {
      signal?.throwIfAborted();
      rendered.push(renderRecord(state, record, browse));
      if (performance.now() < yieldAfter) continue;
      await new Promise((resolve) => window.setTimeout(resolve, 0));
      signal?.throwIfAborted();
      yieldAfter = performance.now() + 12;
    }
    if (!browse) state.grid.append(...rendered);
  }

  function packageCounts(records) {
    const managers = new Map();
    for (const record of records) {
      const available = new Set(
        (record.packages || []).map((id) => id.split(":", 1)[0]),
      );
      for (const manager of available) {
        managers.set(manager, (managers.get(manager) || 0) + 1);
      }
    }
    return managers;
  }

  function renderPackageCounts(total, counts) {
    if (!packageMatchSummary) return;
    const number = new Intl.NumberFormat();
    const managers = managerChoices.map(
      ({ value: manager }) =>
        `${managerLabel(manager)}: ${number.format(counts.get(manager) || 0)}`,
    );
    packageMatchSummary.textContent = [
      `${number.format(total)} ${total === 1 ? copy.package_singular : copy.packages_plural} ${copy.matched_suffix}`,
      ...managers,
    ].join(" · ");
  }

  function renderPackageTotals(state) {
    if (!packageMatchSummary || state.kind !== "package" || !state.index)
      return;
    renderPackageCounts(
      state.index.count,
      new Map(Object.entries(state.index.manager_counts || {})),
    );
  }

  function setPackageReloading(state, loading, generation = 0) {
    if (loading) {
      state.reloadGeneration = generation;
      if (state.kind === "package") {
        state.section.setAttribute("aria-busy", "true");
        state.loadings.forEach((loadingNote) => {
          loadingNote.hidden = false;
        });
      }
      return;
    }
    if (generation && state.reloadGeneration !== generation) return;
    state.reloadGeneration = 0;
    if (state.kind === "package") {
      state.section.removeAttribute("aria-busy");
      state.loadings.forEach((loadingNote) => {
        loadingNote.hidden = true;
      });
    }
  }

  async function ensureBrowseCount(state, count) {
    const browseFilter = {
      query: "",
      expression: null,
      terms: [],
      fields: fieldInputs.length
        ? fieldInputs.map((control) => control.value)
        : ["all"],
      after: "",
      before: state.kind === "package" ? "" : today,
    };
    const records = await searchRecords(state, browseFilter, count);
    records.forEach((record, index) => {
      renderRecord(state, record, true).dataset.browseIndex = String(index);
    });
    refreshItems();
    updateItems(filters());
  }

  async function renderPreview(state) {
    const response = await fetch(state.url, { cache: "no-cache" });
    if (!response.ok) throw new Error(`Unable to load ${response.url}`);
    const manifest = await response.json();
    state.index = manifest;
    for (const [index, record] of (manifest.preview || []).entries()) {
      renderRecord(state, record, true).dataset.browseIndex = String(index);
    }
    state.previewCount = manifest.preview?.length || 0;
    refreshItems();
    updateItems(filters());
    renderPackageTotals(state);
  }

  function randomizeGroups() {
    for (const section of sections.filter((candidate) =>
      candidate.hasAttribute("data-randomize"),
    )) {
      const grid = section.querySelector(
        "[data-paged-grid], .directory-grid, .blog-grid",
      );
      if (!grid) continue;
      const cards = Array.from(grid.children);
      for (let index = cards.length - 1; index > 0; index -= 1) {
        const selected = Math.floor(Math.random() * (index + 1));
        [cards[index], cards[selected]] = [cards[selected], cards[index]];
      }
      grid.append(...cards);
    }
  }

  randomizeGroups();

  for (const [index, section] of sections.entries()) {
    const header = section.querySelector(":scope > .directory-section__header");
    const content = section.querySelector(
      ":scope > [data-directory-section-content]",
    );
    if (header && content && section.dataset.directoryCollapsible !== "false") {
      const contentId = content.id || `directory-section-${index + 1}`;
      content.id = contentId;
      const button = document.createElement("button");
      button.type = "button";
      button.className = "directory-section__toggle";
      button.setAttribute("aria-controls", contentId);
      button.setAttribute("aria-expanded", "true");
      const sectionName =
        header.querySelector("h2, h3")?.textContent.trim() ||
        copy.section_fallback;
      button.setAttribute("aria-label", copy.hide_label + " " + sectionName);
      button.innerHTML = `<span data-section-toggle-label>${copy.hide_label}</span><span class="directory-section__toggle-icon" aria-hidden="true"></span>`;
      header.append(button);
      button.addEventListener("click", () => {
        const collapsed = section.dataset.collapsed === "true";
        section.dataset.collapsed = String(!collapsed);
        button.setAttribute("aria-expanded", String(collapsed));
        button.setAttribute(
          "aria-label",
          (collapsed ? copy.hide_label + " " : copy.show_label + " ") +
            sectionName,
        );
        button.querySelector("[data-section-toggle-label]").textContent =
          collapsed ? copy.hide_label : copy.show_label;
        update();
      });
    }
    const pageRows = Number(section.dataset.pageRows || 0);
    if (pageRows > 0) section.dataset.visibleRows = String(pageRows);
    if (section.dataset.deferredIndex) {
      deferred.set(section, {
        section,
        url: section.dataset.deferredIndex,
        kind: section.dataset.deferredKind,
        grid: section.querySelector("[data-paged-grid]"),
        source: null,
        index: null,
        reloadGeneration: 0,
        searchMatches: null,
        loadings: Array.from(
          section.querySelectorAll("[data-package-matches-loading]"),
        ),
        detailsUrl: section.dataset.packageDetails || "",
        details: section.dataset.packageDetails ? new Map() : null,
      });
    }
  }

  function pageLimit(section) {
    const explicit = Number(section.dataset.visibleItems || 0);
    if (explicit) return explicit;
    const rows = Number(section.dataset.visibleRows || 0);
    const grid = section.querySelector("[data-paged-grid]");
    if (!rows || !grid) return 0;
    const columns = getComputedStyle(grid)
      .gridTemplateColumns.split(" ")
      .filter(Boolean).length;
    return rows * Math.max(columns, 1);
  }

  function currentPage(section) {
    return Math.max(1, Number(section.dataset.currentPage || 1));
  }

  function sectionTotal(section) {
    const state = deferred.get(section);
    return (
      state?.index?.count ??
      Number(section.dataset.total || sectionItems(section).length)
    );
  }

  function pageNumbers(totalPages, page) {
    const selected = new Set([1, totalPages, page - 1, page, page + 1]);
    return [...selected]
      .filter((number) => number >= 1 && number <= totalPages)
      .sort((left, right) => left - right);
  }

  function renderPagination(section, stateFlags) {
    const pagination = section.querySelector("[data-directory-pagination]");
    if (!pagination) return;

    const limit = pageLimit(section);
    const total = sectionTotal(section);
    const totalPages = limit ? Math.ceil(total / limit) : 1;
    const page = Math.min(currentPage(section), Math.max(totalPages, 1));
    section.dataset.currentPage = String(page);
    pagination.replaceChildren();
    pagination.hidden = Boolean(stateFlags.expanded || totalPages <= 1);
    if (pagination.hidden) return;

    const addButton = (label, target, disabled = false, current = false) => {
      const button = createText(pagination, "button", label);
      button.type = "button";
      button.dataset.directoryPage = String(target);
      button.disabled = disabled;
      if (current) button.setAttribute("aria-current", "page");
      return button;
    };

    addButton(copy.previous_label, page - 1, page === 1);
    let previous = 0;
    for (const number of pageNumbers(totalPages, page)) {
      if (previous && number - previous > 1) {
        const gap = createText(pagination, "span", "…");
        gap.className = "directory-pagination__gap";
        gap.setAttribute("aria-hidden", "true");
      }
      addButton(String(number), number, false, number === page);
      previous = number;
    }
    addButton(copy.next_label, page + 1, page === totalPages);
  }

  async function goToPage(section, page) {
    const limit = pageLimit(section);
    if (!limit) return;
    const totalPages = Math.max(1, Math.ceil(sectionTotal(section) / limit));
    const nextPage = Math.max(1, Math.min(page, totalPages));
    section.dataset.currentPage = String(nextPage);
    const state = deferred.get(section);
    const required = nextPage * limit;
    const available = sectionItems(section).filter((item) =>
      item.hasAttribute("data-browse-item"),
    ).length;
    if (state && required > available) {
      const pagination = section.querySelector("[data-directory-pagination]");
      if (pagination) pagination.setAttribute("aria-busy", "true");
      try {
        await ensureBrowseCount(state, required);
      } finally {
        pagination?.removeAttribute("aria-busy");
      }
    }
    update();
  }

  function removeSearchOnly() {
    directory.querySelectorAll("[data-search-only]").forEach((item) => {
      item.remove();
    });
    for (const state of deferred.values()) {
      const browseCards = (
        Array.from(
          state.grid.querySelectorAll(":scope > [data-browse-item]"),
        ) as HTMLElement[]
      ).sort(
        (left, right) =>
          Number(left.dataset.browseIndex) - Number(right.dataset.browseIndex),
      );
      state.grid.append(...browseCards);
    }
    refreshItems();
  }

  function removeStaleSearchResults(state, matches) {
    state.grid
      .querySelectorAll(":scope > [data-search-only]")
      .forEach((item) => {
        if (!matches.has(item.dataset.recordId)) item.remove();
      });
  }

  function itemMatches(item, current) {
    const section = item.closest("[data-directory-section]");
    const category = section?.dataset.searchCategory;
    if (category && !current.categories.has(category)) return false;
    if (current.managers.size) {
      const available = new Set((item.dataset.managers || "").split(" "));
      if (![...current.managers].every((manager) => available.has(manager))) {
        return false;
      }
    }
    if (
      section?.hasAttribute("data-relevance-filter") &&
      !current.includeUnrelated &&
      item.dataset.cppRelevance !== undefined &&
      Number(item.dataset.cppRelevance) <
        Number(directory.dataset.cppRelevanceThreshold || 0.5)
    )
      return false;

    const catalog = section ? deferred.get(section) : null;
    if (catalog?.searchPending) {
      return !item.hidden;
    }
    if (catalog?.searchMatches && activeSearch(current))
      return catalog.searchMatches.has(item.dataset.recordId);

    const authors = current.qualifiers.author || [];
    if (
      authors.length &&
      !authors.every((author) =>
        matchesSearch(parseSearchQuery(author), [
          item.dataset.searchSource || item.dataset.search || item.textContent,
        ]),
      )
    )
      return false;

    if (current.terms.length) {
      const selected = current.fields.includes("all")
        ? item.dataset.search || item.textContent
        : current.fields
            .map((field) => {
              const suffix = field[0].toUpperCase() + field.slice(1);
              return item.dataset[`search${suffix}`] || "";
            })
            .join(" ");
      if (!matchesSearch(current.expression, [selected])) {
        return false;
      }
    }

    if (!current.dateActive || !section?.hasAttribute("data-date-filter")) {
      return true;
    }
    const published = item.querySelector("time[datetime]")?.dateTime || "";
    if (!published) return false;
    return (
      (!current.after || published >= current.after) &&
      (!current.before || published <= current.before + "T23:59:59")
    );
  }

  function searchState(current) {
    const categoryFiltering = categoryInputs.some(
      (control) => !control.checked,
    );
    const expanded = activeSearch(current);
    return {
      filtering: expanded || categoryFiltering,
      expanded,
    };
  }

  function activeSearch(current) {
    return Boolean(
      current.terms.length ||
      current.dateActive ||
      Object.values(current.qualifiers as Record<string, string[]>).some(
        (values) => values.length,
      ),
    );
  }

  function updateFilterIndicator(current) {
    if (!advanced) return;
    const active = Boolean(
      (fieldInputs.length && current.fields.length !== fieldInputs.length) ||
      current.categories.size !== categoryInputs.length ||
      activeSearch(current) ||
      (includeUnrelatedInput && current.includeUnrelated),
    );
    advanced.dataset.active = String(active);
    const label = active ? advanced.dataset.activeLabel : copy.filters_label;
    advanced.setAttribute("aria-label", label);
    advanced.title = label;
  }

  function updateItems(current) {
    let matches = 0;
    const stateFlags = searchState(current);
    directory
      .querySelectorAll<HTMLElement>("[data-search-context-hide]")
      .forEach((element) => {
        element.hidden = stateFlags.filtering;
      });
    updateFilterIndicator(current);
    for (const section of sections.filter((item) => !deferred.has(item))) {
      const byParent = new Map();
      for (const item of sectionItems(section)) {
        const siblings = byParent.get(item.parentElement) || [];
        siblings.push(item);
        byParent.set(item.parentElement, siblings);
      }
      for (const [parent, children] of byParent) {
        if (!parent) continue;
        children.sort((left, right) => {
          if (!current.terms.length)
            return (
              (originalItemOrder.get(left) || 0) -
              (originalItemOrder.get(right) || 0)
            );
          const quality = (item) =>
            searchMatchQuality(current.expression, [
              {
                values: [
                  item.dataset.searchTitle ||
                    item.querySelector("h2, h3, h4, strong")?.textContent,
                ],
              },
              { values: [item.dataset.search || item.textContent], base: 8 },
            ]);
          return (
            quality(left) - quality(right) ||
            (originalItemOrder.get(left) || 0) -
              (originalItemOrder.get(right) || 0)
          );
        });
        parent.append(...children);
      }
    }
    for (const item of items) {
      const section = item.closest("[data-directory-section]");
      const collapsed = section?.dataset.collapsed === "true";
      const matchesFilters = itemMatches(item, current);
      const paged = item.hasAttribute("data-paged-item");
      const pageIndex = paged ? Number(item.dataset.pageIndex) : -1;
      const limit = section ? pageLimit(section) : 0;
      const page = section ? currentPage(section) : 1;
      const pageStart = (page - 1) * limit;
      const withinPage =
        !paged ||
        stateFlags.expanded ||
        (pageIndex >= pageStart && pageIndex < pageStart + limit);
      const included = !collapsed && matchesFilters;
      const visible = included && withinPage;
      item.hidden = !visible;
      item.dataset.directoryMatch = String(included);
      if (visible) matches += 1;
    }
    for (const section of sections) {
      const collapsed = section.dataset.collapsed === "true";
      const hasMatch = sectionItems(section).some(
        (item) => item.dataset.directoryMatch === "true",
      );
      section.hidden = Boolean(stateFlags.filtering && !collapsed && !hasMatch);
      renderPagination(section, stateFlags);
    }
    clear.hidden = input.value.length === 0;
    const browsing = !activeSearch(current);
    const totalMatches = browsing
      ? sections.reduce((total, section) => {
          const category = section.dataset.searchCategory;
          if (
            section.dataset.collapsed === "true" ||
            (category && !current.categories.has(category))
          )
            return total;
          return total + sectionTotal(section);
        }, 0)
      : matches;
    const noun = totalMatches === 1 ? copy.entry_singular : copy.entry_plural;
    const searching = [...deferred.values()].some(
      (state) => state.reloadGeneration === searchGeneration,
    );
    const tooShort = current.terms.some(
      (term) => term.length < minimumQueryLength,
    );
    if (hasPackageSection && !stateFlags.filtering) {
      const packageState = [...deferred.values()].find(
        (state) => state.kind === "package",
      );
      const total = packageState?.index?.count;
      status.textContent =
        total == null
          ? ""
          : `${new Intl.NumberFormat().format(total)} ${copy.packages_plural}`;
    } else {
      status.textContent = tooShort
        ? `${totalMatches} ${noun} · ${copy.minimum_query.replace("{count}", minimumQueryLength)}`
        : stateFlags.filtering && matches === 0 && !searching
          ? emptyMessage
          : `${totalMatches} ${noun}${searching ? " · " + copy.indexing : ""}`;
    }
    if (hasPackageSection) {
      window.dispatchEvent(
        new CustomEvent("cpp:package-search", {
          detail: {
            filtering: stateFlags.filtering,
            managers: [...current.managers],
            matches: items
              .filter(
                (item) =>
                  item.closest("[data-directory-section]")?.dataset
                    .deferredKind === "package" &&
                  item.dataset.directoryMatch === "true",
              )
              .map((item) => item.dataset.recordId),
          },
        }),
      );
    }
  }

  async function addDeferredMatches(current, generation, signal) {
    const managerFiltering = current.managers.size > 0;
    if (!activeSearch(current)) return;
    await Promise.all(
      [...deferred.values()].map(async (state) => {
        if (state.section.dataset.collapsed === "true") return;
        const category = state.section.dataset.searchCategory;
        if (category && !current.categories.has(category)) return;
        await loadIndex(state);
        signal.throwIfAborted();
        if (
          current.terms.some(
            (term) => term.length < state.index.min_query_length,
          )
        )
          return;
        setPackageReloading(state, true, generation);
        updateItems(current);
        const records = await searchRecords(
          state,
          current,
          managerFiltering ? Infinity : undefined,
          signal,
        );
        signal.throwIfAborted();
        if (generation !== searchGeneration) return;
        if (state.kind === "book") {
          const bounds = publicationBounds(publicationSelection);
          const timelineRecords = await searchRecords(
            state,
            { ...current, ...bounds },
            Infinity,
            signal,
          );
          signal.throwIfAborted();
          if (generation !== searchGeneration) return;
          publicationMatches = timelineRecords;
          renderPublicationTimeline(state.index, timelineRecords);
        }
        const matches = new Set(records.map((record) => record.id));
        if (state.kind === "package") {
          renderPackageCounts(records.length, packageCounts(records));
        }
        await renderRecords(state, records, false, signal);
        signal.throwIfAborted();
        if (generation !== searchGeneration) return;
        state.searchMatches = matches;
        state.searchPending = false;
        removeStaleSearchResults(state, matches);
        refreshItems();
        setPackageReloading(state, false, generation);
        updateItems(current);
      }),
    );
  }

  async function update() {
    renderSearchHighlight();
    searchController?.abort();
    searchController = new AbortController();
    const { signal } = searchController;
    const generation = ++searchGeneration;
    const current = filters();
    const searching = activeSearch(current);
    const queryReady = !current.terms.some(
      (term) => term.length < minimumQueryLength,
    );
    for (const state of deferred.values()) {
      state.searchPending = searching && queryReady;
      if (!searching || !queryReady) state.searchMatches = null;
      setPackageReloading(state, false);
    }
    if (!searching || !queryReady) removeSearchOnly();
    updateItems(current);
    for (const state of deferred.values()) {
      if (!searching) {
        loadIndex(state)
          .then(() => {
            if (signal.aborted) return;
            if (state.kind === "package") {
              renderPackageTotals(state);
            }
            updateItems(filters());
          })
          .catch(console.error);
      } else if (
        current.terms.some((term) => term.length < minimumQueryLength) &&
        state.kind === "package" &&
        packageMatchSummary
      ) {
        packageMatchSummary.textContent = copy.count_matches_prompt.replace(
          "{count}",
          minimumQueryLength,
        );
      } else if (state.kind === "package" && packageMatchSummary) {
        packageMatchSummary.textContent = copy.counting_matches;
      }
    }
    try {
      await addDeferredMatches(current, generation, signal);
    } catch (error) {
      if (error.name === "AbortError") return;
      console.error(error);
      if (generation === searchGeneration) {
        for (const state of deferred.values()) {
          state.searchPending = false;
          setPackageReloading(state, false, generation);
        }
        status.textContent = copy.unavailable;
      }
    }
  }

  for (const section of sections) {
    const pagination = section.querySelector("[data-directory-pagination]");
    if (!pagination) continue;
    pagination.addEventListener("click", (event) => {
      const button = eventElement(event)?.closest<HTMLButtonElement>(
        "button[data-directory-page]",
      );
      if (!button || button.disabled) return;
      goToPage(section, Number(button.dataset.directoryPage));
    });
  }

  function synchronizeDateBounds(event) {
    if (!afterInput || !beforeInput) return;
    if (event?.target === afterInput && afterInput.value > beforeInput.value) {
      beforeInput.value = afterInput.value;
    }
    if (event?.target === beforeInput && beforeInput.value < afterInput.value) {
      afterInput.value = beforeInput.value;
    }
    afterInput.max = beforeInput.value || today;
    beforeInput.min = afterInput.value || "";
    beforeInput.max = today;
  }

  function activateCaches() {
    deferred.forEach((state) => {
      loadIndex(state).catch(console.error);
    });
  }

  function positionFilterMenu() {
    if (!advanced || !options || options.hidden) return;
    const anchor = advanced.getBoundingClientRect();
    const edge = 8;
    const top = Math.min(anchor.bottom + 6, window.innerHeight - edge);
    options.style.top = `${top}px`;
    options.style.right = `${Math.max(edge, window.innerWidth - anchor.right)}px`;
    options.style.maxHeight = `${Math.max(120, window.innerHeight - top - edge)}px`;
  }

  function closeFilterMenu({ restoreFocus = false } = {}) {
    if (!advanced || !options || options.hidden) return;
    advanced.setAttribute("aria-expanded", "false");
    options.hidden = true;
    if (restoreFocus) advanced.focus();
  }

  advanced?.addEventListener("click", () => {
    const expanded = advanced.getAttribute("aria-expanded") === "true";
    if (expanded) {
      closeFilterMenu();
      return;
    }
    advanced.setAttribute("aria-expanded", "true");
    options.hidden = false;
    positionFilterMenu();
  });

  window.addEventListener("resize", positionFilterMenu);
  window.addEventListener("scroll", positionFilterMenu, { passive: true });

  document.addEventListener("pointerdown", (event) => {
    if (
      options?.hidden ||
      advanced?.contains(event.target as Node) ||
      options?.contains(event.target as Node)
    )
      return;
    closeFilterMenu();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && advanced && options && !options.hidden) {
      event.preventDefault();
      closeFilterMenu({ restoreFocus: true });
    }
  });
  input.addEventListener("input", () => {
    openQualifierValue();
    update();
  });
  input.addEventListener("scroll", renderSearchHighlight);
  for (const control of fieldInputs) {
    control.addEventListener("input", () => {
      if (!fieldInputs.some((field) => field.checked)) {
        control.checked = true;
      }
      update();
    });
  }
  for (const control of categoryInputs) {
    control.addEventListener("input", () => {
      if (!categoryInputs.some((category) => category.checked)) {
        control.checked = true;
      }
      update();
    });
  }
  for (const choice of managerChoices) {
    choice.addEventListener("click", () => {
      const active = new Set<string>(
        parseDirectoryQuery(input.value, {
          manager: DIRECTORY_QUALIFIERS.manager,
        }).qualifiers.manager,
      ).has(choice.value);
      input.value = setQualifier(input.value, "manager", choice.value, !active);
      update();
      input.focus();
    });
  }
  includeUnrelatedInput?.addEventListener("input", update);
  for (const control of [afterInput, beforeInput].filter(Boolean)) {
    control.addEventListener("input", (event) => {
      publicationSelection = {};
      synchronizeDateBounds(event);
      update();
    });
  }
  synchronizeDateBounds(undefined);
  input.addEventListener("focus", activateCaches, { once: true });
  window.addEventListener("resize", () => updateItems(filters()));
  clear.addEventListener("click", () => {
    input.value = "";
    update();
    input.focus();
  });

  window.addEventListener("cpp:package-select", async (baseEvent) => {
    const event = baseEvent as CustomEvent<{ id?: string; label?: string }>;
    const id = event.detail?.id;
    if (!id) return;
    pendingPackageId = id;
    input.value = event.detail.label || id;
    history.replaceState(null, "", `#${encodeURIComponent(id)}`);
    await update();
  });

  let lastCacheRefresh = Date.now();
  document.addEventListener("visibilitychange", async () => {
    if (
      document.visibilityState !== "visible" ||
      Date.now() - lastCacheRefresh < 5 * 60 * 1000
    )
      return;
    lastCacheRefresh = Date.now();
    let changed = false;
    await Promise.all(
      [...deferred.values()].map(async (state) => {
        if (!state.source) return;
        const before = state.index?.revision || "";
        const index = await state.source.refresh();
        state.index = index;
        if (before && before !== index.revision) {
          changed = true;
          state.grid?.replaceChildren();
          await ensureBrowseCount(
            state,
            Number(state.section.dataset.pageRows || 30),
          );
        }
        let detailsChanged = false;
        await Promise.all(
          [...(state.details?.values() || [])].map(async (collection) => {
            const oldManifest = await collection.manifest();
            const oldKey = detailManifestKey(oldManifest);
            const newManifest = await collection.refresh();
            if (oldKey !== detailManifestKey(newManifest))
              detailsChanged = true;
          }),
        );
        if (detailsChanged) {
          changed = true;
          invalidatePackageDetails(state);
        }
      }),
    ).catch(console.error);
    if (changed) {
      refreshItems();
      await update();
    }
  });

  document.addEventListener("click", (event) => {
    const tag = eventElement(event)?.closest<HTMLElement>("[data-search-tag]");
    if (!tag) return;
    input.value = tag.dataset.searchTag;
    fieldInputs.forEach((field) => {
      field.checked = field.value === "tags";
    });
    update();
    document
      .querySelector<HTMLDialogElement>("[data-channel-dialog][open]")
      ?.close();
    input.focus();
    input.scrollIntoView({ behavior: "smooth", block: "nearest" });
  });

  refreshItems();
  update();
  deferred.forEach((state) => {
    const initial =
      pageLimit(state.section) || Number(state.section.dataset.pageRows || 30);
    const available = sectionItems(state.section).filter((item) =>
      item.hasAttribute("data-browse-item"),
    ).length;
    if (state.kind === "package" && !available) {
      renderPreview(state).catch(console.error);
    } else if (state.kind !== "package" && available < initial) {
      ensureBrowseCount(state, initial).catch(console.error);
    }
  });
}
