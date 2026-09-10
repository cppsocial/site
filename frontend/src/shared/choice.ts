export type StoredChoiceOptions<Value extends string> = {
  apply: (value: Value) => void;
  buttons: readonly HTMLButtonElement[];
  initial: Value;
  storageKey: string;
  value: (button: HTMLButtonElement) => Value;
};

/** Keep a button-backed view choice, its ARIA state, and persistence in sync. */
export function initStoredChoice<Value extends string>({
  apply,
  buttons,
  initial,
  storageKey,
  value,
}: StoredChoiceOptions<Value>): (choice: Value) => void {
  const choices = new Set(buttons.map(value));
  const select = (choice: Value, persist = true): void => {
    apply(choice);
    for (const button of buttons)
      button.setAttribute("aria-pressed", String(value(button) === choice));
    if (persist) {
      try {
        localStorage.setItem(storageKey, choice);
      } catch {
        // Storage can be unavailable in privacy modes; the view still works.
      }
    }
  };
  for (const button of buttons)
    button.addEventListener("click", () => select(value(button)));
  try {
    const stored = localStorage.getItem(storageKey) as Value | null;
    if (stored && choices.has(stored)) initial = stored;
  } catch {
    // Use the caller's initial view when storage is unavailable.
  }
  select(initial, false);
  return select;
}
