(() => {
  const dialog = document.querySelector("[data-book-dialog]");
  const content = dialog?.querySelector("[data-book-dialog-content]");
  if (!dialog || !content) return;

  let opener = null;

  const ratingLabel = (average, count) => (
    `${average.toFixed(1)} / 5 · ${count.toLocaleString()} ratings`
  );

  const sourceRecord = (name, url, average = null, count = 0, status = "") => ({
    name,
    url,
    average: Number(average),
    count: Number(count),
    status,
  });

  const openLibraryRating = async (detail) => {
    const url = detail.dataset.openLibraryUrl;
    const fallbackAverage = Number(detail.dataset.openLibraryRating);
    const fallbackCount = Number(detail.dataset.openLibraryCount);
    try {
      if (!detail.dataset.workKey) throw new Error("No Open Library work key");
      const response = await fetch(
        `https://openlibrary.org${detail.dataset.workKey}/ratings.json`,
      );
      if (!response.ok) throw new Error(`Open Library returned ${response.status}`);
      const { summary = {} } = await response.json();
      return sourceRecord("Open Library", url, summary.average, summary.count, "Retrieved live");
    } catch (error) {
      console.warn("Could not refresh Open Library rating", error);
      if (Number.isFinite(fallbackAverage) && fallbackCount) {
        return sourceRecord(
          "Open Library",
          url,
          fallbackAverage,
          fallbackCount,
          "Cached rating",
        );
      }
      return sourceRecord("Open Library", url, null, 0, "Unavailable");
    }
  };

  const renderRating = (detail, source) => {
    const container = detail.querySelector("[data-book-rating-sources]");
    if (!container || !detail.isConnected) return;

    const value = container.querySelector("[data-book-rating-value]");
    if (!value) return;
    const rated = Number.isFinite(source.average) && source.count > 0;
    value.textContent = rated
      ? [ratingLabel(source.average, source.count), source.status]
          .filter(Boolean)
          .join(" · ")
      : source.status || "No public ratings";
    container.removeAttribute("aria-busy");
  };

  const refreshRating = async (detail) => {
    if (!detail) return;
    renderRating(detail, await openLibraryRating(detail));
  };

  const close = () => dialog.open && dialog.close();

  document.addEventListener("click", (event) => {
    const trigger = event.target.closest?.("[data-book-open]");
    if (!trigger) return;
    const card = trigger.closest("[data-book-card]");
    const template = card?.querySelector("[data-book-details]");
    if (!template) return;

    opener = trigger;
    content.replaceChildren(template.content.cloneNode(true));
    dialog.showModal();
    document.documentElement.classList.add("has-book-dialog");
    content.querySelector("[data-book-close]")?.focus();
    refreshRating(content.querySelector(".book-detail"));
  });

  dialog.addEventListener("click", (event) => {
    if (event.target.closest?.("[data-book-close]") || event.target === dialog) close();
  });
  dialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    close();
  });
  dialog.addEventListener("close", () => {
    document.documentElement.classList.remove("has-book-dialog");
    content.replaceChildren();
    opener?.focus();
    opener = null;
  });
})();
