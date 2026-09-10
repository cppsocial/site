import { beforeEach, describe, expect, it, vi } from "vitest";

import { initStoredChoice } from "../src/shared/choice";

beforeEach(() => {
  localStorage.clear();
  document.body.innerHTML = `
    <button data-view="cards">Cards</button>
    <button data-view="list">List</button>
  `;
});

function initialize() {
  const apply = vi.fn();
  const buttons = [
    ...document.querySelectorAll<HTMLButtonElement>("[data-view]"),
  ];
  const select = initStoredChoice<"cards" | "list">({
    apply,
    buttons,
    initial: "cards",
    storageKey: "catalog-view",
    value: (button) => (button.dataset.view === "list" ? "list" : "cards"),
  });
  return { apply, buttons, select };
}

describe("initStoredChoice", () => {
  it("restores, applies, announces, and persists a choice", () => {
    localStorage.setItem("catalog-view", "list");
    const { apply, buttons } = initialize();

    expect(apply).toHaveBeenLastCalledWith("list");
    expect(
      buttons.map((button) => button.getAttribute("aria-pressed")),
    ).toEqual(["false", "true"]);

    buttons[0].click();
    expect(apply).toHaveBeenLastCalledWith("cards");
    expect(localStorage.getItem("catalog-view")).toBe("cards");
    expect(
      buttons.map((button) => button.getAttribute("aria-pressed")),
    ).toEqual(["true", "false"]);
  });

  it("ignores unknown stored values", () => {
    localStorage.setItem("catalog-view", "obsolete");
    const { apply } = initialize();
    expect(apply).toHaveBeenLastCalledWith("cards");
  });

  it("continues to work when storage is unavailable", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    const { apply, buttons } = initialize();

    buttons[1].click();
    expect(apply).toHaveBeenLastCalledWith("list");
  });
});
