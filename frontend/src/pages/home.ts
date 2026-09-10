(() => {
  function currentTheme(): "light" | "dark" {
    const theme = document.documentElement.dataset.theme;
    return theme === "dark" || theme === "light"
      ? theme
      : matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light";
  }

  if (!window.CodeBlocks) {
    console.error("[CodeBlocks] The runtime loader did not initialize");
    return;
  }

  window.CodeBlocks.configure({
    theme: currentTheme(),
    editorOptions: {
      minimap: { enabled: false },
      scrollBeyondLastLine: false,
    },
  });

  window.CodeBlocks.ready
    .then(() => {
      document
        .querySelectorAll(".home-codeblock .codeblocks-output")
        .forEach((output, index) => {
          const toggle = output.querySelector<HTMLButtonElement>(
            "header .codeblocks-output-tab",
          );
          const contents = output.querySelector<HTMLPreElement>("pre");
          if (!toggle || !contents) return;

          contents.id ||= `codeblocks-output-${index + 1}`;
          toggle.classList.add("codeblocks-output-toggle");
          toggle.textContent = "Output";
          toggle.setAttribute("aria-controls", contents.id);
          toggle.setAttribute("aria-expanded", "true");
          toggle.addEventListener("click", () => {
            const expanded = toggle.getAttribute("aria-expanded") === "true";
            toggle.setAttribute("aria-expanded", String(!expanded));
            contents.hidden = expanded;
          });
        });

      const updateTheme = () => {
        void window.CodeBlocks?.setTheme(currentTheme());
      };

      new MutationObserver(updateTheme).observe(document.documentElement, {
        attributes: true,
        attributeFilter: ["data-theme"],
      });
    })
    .catch((error: unknown) => {
      console.error("[CodeBlocks] Runtime initialization failed", error);
    });
})();
