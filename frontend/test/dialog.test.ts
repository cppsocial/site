import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TemplateDialogController } from "../src/shared/dialog";

let controller: TemplateDialogController;

beforeEach(() => {
  document.body.innerHTML = `
    <article data-card>
      <button data-open>Open</button>
      <template data-template><section><button data-close>Close</button></section></template>
    </article>
    <dialog><div data-content></div></dialog>
  `;
  const dialog = document.querySelector("dialog")!;
  dialog.showModal = vi.fn(() => dialog.setAttribute("open", ""));
  dialog.close = vi.fn(() => {
    dialog.removeAttribute("open");
    dialog.dispatchEvent(new Event("close"));
  });
});

afterEach(() => controller?.destroy());

describe("TemplateDialogController", () => {
  it("clones, opens, closes, cleans up, and restores focus", async () => {
    const afterOpen = vi.fn();
    const beforeClose = vi.fn();
    const dialog = document.querySelector("dialog")!;
    const content = document.querySelector<HTMLElement>("[data-content]")!;
    const opener = document.querySelector<HTMLButtonElement>("[data-open]")!;
    controller = new TemplateDialogController({
      cardSelector: "[data-card]",
      closeSelector: "[data-close]",
      content,
      dialog,
      documentClass: "has-dialog",
      openSelector: "[data-open]",
      templateSelector: "[data-template]",
      afterOpen,
      beforeClose,
    });

    opener.click();
    expect(dialog.open).toBe(true);
    expect(content.querySelector("[data-close]")).not.toBeNull();
    expect(document.documentElement.classList.contains("has-dialog")).toBe(
      true,
    );
    expect(afterOpen).toHaveBeenCalledOnce();

    content.querySelector<HTMLButtonElement>("[data-close]")!.click();
    await vi.waitFor(() => expect(dialog.open).toBe(false));
    expect(beforeClose).toHaveBeenCalledOnce();
    expect(content.childElementCount).toBe(0);
    expect(document.activeElement).toBe(opener);
  });
});
