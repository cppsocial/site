import { DialogContext, TemplateDialogController } from "../shared/dialog";

export function fitTagList(list: HTMLElement): void {
  const tags = Array.from(list.children).filter(
    (item): item is HTMLElement =>
      item instanceof HTMLElement && !item.matches("[data-tag-overflow]"),
  );
  const overflow = list.querySelector<HTMLElement>("[data-tag-overflow]");
  if (!overflow) return;
  tags.forEach((tag) => (tag.hidden = false));
  overflow.hidden = true;
  let used = 0;
  let visible = 0;
  for (const tag of tags) {
    const width = tag.getBoundingClientRect().width + 6;
    if (used + width > list.clientWidth - 42) break;
    used += width;
    visible += 1;
  }
  if (visible === tags.length) return;
  tags.slice(visible).forEach((tag) => (tag.hidden = true));
  const count = overflow.querySelector("span");
  if (count) count.textContent = `+${tags.length - visible}`;
  overflow.hidden = false;
}

function reduceMotion(): boolean {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function frames(
  detail: HTMLElement,
  card: HTMLElement,
  reverse = false,
): Keyframe[] {
  const from = card.getBoundingClientRect();
  const to = detail.getBoundingClientRect();
  const collapsed = {
    borderRadius: "14px",
    opacity: 0.35,
    transform: `translate(${from.left + from.width / 2 - to.left - to.width / 2}px, ${from.top + from.height / 2 - to.top - to.height / 2}px) scale(${from.width / to.width}, ${from.height / to.height})`,
  };
  const expanded = { borderRadius: "20px", opacity: 1, transform: "none" };
  return reverse ? [expanded, collapsed] : [collapsed, expanded];
}

function animateOpen({ card, content, dialog }: DialogContext): void {
  if (reduceMotion()) return;
  const detail = content.querySelector<HTMLElement>(".channel-detail");
  detail?.animate(frames(detail, card), {
    duration: 380,
    easing: "cubic-bezier(.2, .8, .2, 1)",
    fill: "both",
  });
  dialog.animate([{ opacity: 0 }, { opacity: 1 }], {
    duration: 220,
    easing: "ease-out",
  });
}

async function animateClose({ card, content }: DialogContext): Promise<void> {
  if (reduceMotion() || !card.isConnected) return;
  const detail = content.querySelector<HTMLElement>(".channel-detail");
  if (!detail) return;
  const animation = detail.animate(frames(detail, card, true), {
    duration: 240,
    easing: "cubic-bezier(.4, 0, 1, 1)",
    fill: "both",
  });
  await animation.finished.catch(() => undefined);
}

export function initChannels(): TemplateDialogController | null {
  const fitAllTags = () =>
    document
      .querySelectorAll<HTMLElement>("[data-collapsible-tags]")
      .forEach(fitTagList);
  requestAnimationFrame(fitAllTags);
  new ResizeObserver(fitAllTags).observe(document.documentElement);
  const dialog = document.querySelector<HTMLDialogElement>(
    "[data-channel-dialog]",
  );
  const content = dialog?.querySelector<HTMLElement>(
    "[data-channel-dialog-content]",
  );
  if (!dialog || !content) return null;
  return new TemplateDialogController({
    cardSelector: "[data-channel-card]",
    closeSelector: "[data-channel-close]",
    content,
    dialog,
    documentClass: "has-channel-dialog",
    openSelector: "[data-channel-open]",
    templateSelector: "[data-channel-details]",
    afterOpen: animateOpen,
    beforeClose: animateClose,
  });
}
