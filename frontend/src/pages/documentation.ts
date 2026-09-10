(() => {
  const pages = [...document.querySelectorAll<HTMLElement>("[data-docs-page]")];
  const toc = document.querySelector<HTMLElement>("[data-docs-toc]");
  if (!pages.length || !toc) return;

  const slug = (value: string) =>
    value
      .toLowerCase()
      .replace(/[^a-z0-9+]+/g, "-")
      .replace(/^-|-$/g, "");

  for (const page of pages) {
    const used = new Set();
    for (const heading of page.querySelectorAll(".docs-markdown h3")) {
      const headingSlug = heading.id || slug(heading.textContent ?? "");
      let id = `${page.id}-${headingSlug}`;
      let suffix = 2;
      while (used.has(id)) id = `${id}-${suffix++}`;
      used.add(id);
      heading.id = id;
    }
  }

  const renderToc = (page: HTMLElement) => {
    for (const link of document.querySelectorAll(
      ".docs-sidebar a[aria-current]",
    )) {
      link.removeAttribute("aria-current");
    }
    const activeLink = document.querySelector(
      `.docs-sidebar a[href="#${page.id}"]`,
    );
    if (activeLink) activeLink.setAttribute("aria-current", "true");

    toc.replaceChildren();
    const headings = page.querySelectorAll(".docs-markdown h3");
    for (const heading of headings) {
      const item = document.createElement("li");
      const link = document.createElement("a");
      link.href = `#${heading.id}`;
      link.textContent = heading.textContent;
      item.append(link);
      toc.append(item);
    }
    const container = toc.closest<HTMLElement>(".docs-toc");
    if (container) container.hidden = headings.length === 0;
  };

  let active = pages[0];
  renderToc(active);
  const observer = new IntersectionObserver(
    (entries) => {
      const visible = entries
        .filter((entry) => entry.isIntersecting)
        .sort(
          (left, right) =>
            left.boundingClientRect.top - right.boundingClientRect.top,
        );
      if (!visible.length || visible[0].target === active) return;
      active = visible[0].target as HTMLElement;
      renderToc(active);
    },
    { rootMargin: "-15% 0px -65%", threshold: 0 },
  );

  pages.forEach((page) => observer.observe(page));
})();
