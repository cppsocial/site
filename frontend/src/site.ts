import { eventElement } from "./shared/dom";

function initTheme(): void {
  const toggle =
    document.getElementById("theme-toggle") ??
    document.querySelector<HTMLElement>(".theme-toggle");
  if (!toggle) return;
  toggle.addEventListener("click", () => {
    const current =
      document.documentElement.dataset.theme ??
      (window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light");
    const next = current === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem("pref-theme", next);
    } catch {
      // Storage can be unavailable in privacy modes; the theme still changes.
    }
  });
}

function initMenu(): void {
  const toggle = document.querySelector<HTMLElement>(".menu-toggle");
  const menu = document.querySelector<HTMLElement>(".menu");
  if (!toggle || !menu) return;
  const close = () => {
    menu.classList.remove("active");
    toggle.setAttribute("aria-expanded", "false");
  };
  toggle.addEventListener("click", () => {
    menu.classList.toggle("active");
    toggle.setAttribute(
      "aria-expanded",
      String(menu.classList.contains("active")),
    );
  });
  menu.addEventListener("click", (event) => {
    if (eventElement(event)?.closest("a")) close();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") close();
  });
  document.addEventListener("click", (event) => {
    if (!eventElement(event)?.closest(".header-nav")) close();
  });
  window.matchMedia("(min-width: 1121px)").addEventListener("change", close);
}

const interactive = "a, button, input, select, textarea";

function initCardLinks(): void {
  const openCard = (card: HTMLElement) =>
    window.open(
      card.dataset.cardHref,
      card.dataset.cardTarget ?? "_blank",
      "noopener",
    );
  document.addEventListener("keydown", (event) => {
    const target = eventElement(event);
    const card = target?.closest<HTMLElement>("[data-card-href]");
    if (
      !card ||
      target !== card ||
      (event.key !== "Enter" && event.key !== " ")
    )
      return;
    event.preventDefault();
    openCard(card);
  });
  document.addEventListener("click", (event) => {
    const target = eventElement(event);
    const card = target?.closest<HTMLElement>("[data-card-href]");
    if (!target || !card || target.closest(interactive)) return;
    openCard(card);
  });
}

function registerServiceWorker(script: HTMLScriptElement | null): void {
  const url = script?.dataset.serviceWorker;
  if (url && "serviceWorker" in navigator) {
    void navigator.serviceWorker.register(url);
  }
}

const script = document.currentScript as HTMLScriptElement | null;
initTheme();
initMenu();
initCardLinks();
registerServiceWorker(script);
