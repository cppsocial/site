(function () {
    const toggle = document.getElementById("theme-toggle") ||
        document.querySelector(".theme-toggle");

    const menuToggle = document.querySelector(".menu-toggle");
    const menu = document.querySelector(".menu");
    const html = document.documentElement;

    if (toggle) {
        toggle.addEventListener("click", () => {
            const newTheme = html.dataset.theme === "dark" ? "light" : "dark";
            html.dataset.theme = newTheme;
            localStorage.setItem("pref-theme", newTheme);
        });
    }

    if (menuToggle) {
        menuToggle.addEventListener("click", () => {
            menu.classList.toggle("active");
            menuToggle.setAttribute(
                "aria-expanded",
                menu.classList.contains("active")
            );
        });
    }
})();

(() => {
  const interactive = "a, button, input, select, textarea";

  document.addEventListener("keydown", (event) => {
    const card = event.target.closest?.("[data-card-href]");
    if (!card || event.target !== card || (event.key !== "Enter" && event.key !== " ")) return;
    event.preventDefault();
    window.open(card.dataset.cardHref, "_blank", "noopener");
  });

  document.addEventListener("click", (event) => {
    const card = event.target.closest?.("[data-card-href]");
    if (!card || event.target.closest(interactive)) return;
    window.open(card.dataset.cardHref, "_blank", "noopener");
  });
})();

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register(
    document.currentScript.dataset.serviceWorker,
  );
}

(() => {
  const reset = document.querySelector("[data-reset-local-cache]");
  const status = document.querySelector("[data-reset-local-cache-status]");
  if (!reset) return;

  function deleteDatabase(name) {
    return new Promise((resolve, reject) => {
      const request = indexedDB.deleteDatabase(name);
      request.onsuccess = resolve;
      request.onerror = () => reject(request.error);
      request.onblocked = () => reject(
        new Error("Cache reset is blocked by another open tab."),
      );
    });
  }

  reset.addEventListener("click", async (event) => {
    event.preventDefault();
    reset.setAttribute("aria-disabled", "true");
    if (status) status.textContent = "Clearing…";
    try {
      window.CppSearchCache?.closeDatabases?.();
      if ("caches" in window) {
        const names = await caches.keys();
        await Promise.all(names
          .filter((name) => name.startsWith("directory-data-")
            || name.startsWith("external-images-")
            || name.startsWith("youtube-artwork-"))
          .map((name) => caches.delete(name)));
      }
      if ("indexedDB" in window) {
        let names = ["blog-posts", "youtube-videos", "packages"]
          .map((name) => `cpp-social-search-v8:${name}`);
        if (indexedDB.databases) {
          const databases = await indexedDB.databases();
          names = databases.map((database) => database.name)
            .filter((name) => name?.startsWith("cpp-social-search-"));
        }
        await Promise.all(names.map(deleteDatabase));
      }
      if (status) status.textContent = "Cleared. Reloading…";
      location.reload();
    } catch (error) {
      console.error(error);
      reset.removeAttribute("aria-disabled");
      if (status) status.textContent = "Could not clear cache.";
    }
  });
})();
