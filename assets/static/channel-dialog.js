(() => {
  const fitTags = (list) => {
    const tags = Array.from(list.children).filter((item) => !item.matches("[data-tag-overflow]"));
    const overflow = list.querySelector("[data-tag-overflow]");
    tags.forEach((tag) => { tag.hidden = false; });
    overflow.hidden = true;
    const available = list.clientWidth;
    let used = 0;
    let visible = 0;
    for (const tag of tags) {
      const width = tag.getBoundingClientRect().width + 6;
      if (used + width > available - 42) break;
      used += width;
      visible += 1;
    }
    if (visible < tags.length) {
      tags.slice(visible).forEach((tag) => { tag.hidden = true; });
      overflow.querySelector("span").textContent = `+${tags.length - visible}`;
      overflow.hidden = false;
    }
  };

  const fitAllTags = () => document.querySelectorAll("[data-collapsible-tags]").forEach(fitTags);
  requestAnimationFrame(fitAllTags);
  new ResizeObserver(fitAllTags).observe(document.documentElement);

  const dialog = document.querySelector("[data-channel-dialog]");
  const content = dialog?.querySelector("[data-channel-dialog-content]");
  if (!dialog || !content) return;

  let opener = null;
  let originCard = null;
  let closing = false;

  const reduceMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const expansionFrames = (detail, card, reverse = false) => {
    const from = card.getBoundingClientRect();
    const to = detail.getBoundingClientRect();
    const collapsed = {
      opacity: 0.35,
      transform: `translate(${from.left + from.width / 2 - to.left - to.width / 2}px, ${from.top + from.height / 2 - to.top - to.height / 2}px) scale(${from.width / to.width}, ${from.height / to.height})`,
      borderRadius: "14px",
    };
    const expanded = { opacity: 1, transform: "none", borderRadius: "20px" };
    return reverse ? [expanded, collapsed] : [collapsed, expanded];
  };

  const closeDialog = async () => {
    if (!dialog.open || closing) return;
    closing = true;
    const detail = content.querySelector(".channel-detail");
    if (!reduceMotion() && detail && originCard?.isConnected) {
      const animation = detail.animate(expansionFrames(detail, originCard, true), {
        duration: 240,
        easing: "cubic-bezier(.4, 0, 1, 1)",
        fill: "both",
      });
      await animation.finished.catch(() => {});
    }
    dialog.close();
  };

  document.addEventListener("click", (event) => {
    const trigger = event.target.closest("[data-channel-open]");
    if (!trigger) return;

    const card = trigger.closest("[data-channel-card]");
    const template = card?.querySelector("[data-channel-details]");
    if (!template) return;

    opener = trigger;
    originCard = card;
    content.replaceChildren(template.content.cloneNode(true));
    dialog.showModal();
    document.documentElement.classList.add("has-channel-dialog");
    content.querySelector("[data-channel-close]")?.focus();

    if (!reduceMotion()) {
      const detail = content.querySelector(".channel-detail");
      detail?.animate(expansionFrames(detail, card), {
        duration: 380,
        easing: "cubic-bezier(.2, .8, .2, 1)",
        fill: "both",
      });
      dialog.animate([{ opacity: 0 }, { opacity: 1 }], {
        duration: 220,
        easing: "ease-out",
      });
    }
  });

  dialog.addEventListener("click", (event) => {
    if (event.target.closest?.("[data-channel-close]")) {
      closeDialog();
      return;
    }
    if (event.target === dialog) closeDialog();
  });
  dialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    closeDialog();
  });
  dialog.addEventListener("close", () => {
    document.documentElement.classList.remove("has-channel-dialog");
    content.replaceChildren();
    opener?.focus();
    opener = null;
    originCard = null;
    closing = false;
  });
})();
