import { beforeEach, describe, expect, it, vi } from "vitest";

const event = {
  description: "Three days of C++ talks and community collaboration",
  end_date: "2026-09-10",
  event_type: "conference",
  format: "in_person",
  location: "Aurora, Colorado, USA",
  organizer: "C++ Community",
  path: "https://example.com/event",
  source_url: "https://example.com/source",
  start_date: "2026-09-08",
  status: "confirmed",
  title: "Example C++ Conference",
  venue: "Convention Center",
};

beforeEach(() => {
  vi.resetModules();
  localStorage.clear();
  window.history.replaceState({}, "", "/events/?month=2026-09");
  document.body.innerHTML = `
    <section data-event-calendar>
      <script type="application/json" data-calendar-copy>${JSON.stringify({
        close_label: "Close event details",
        date_label: "Date",
        event_plural: "events",
        event_singular: "event",
        in_label: "in",
        next_prefix: "Next:",
        non_public_note:
          "This is not a public drop-in meeting. Guests must arrange attendance in advance.",
        no_events_prefix: "No events in",
        on_label: "on",
        participation_label: "Learn how to participate in WG21",
        participation_url: "https://isocpp.org/std/meetings-and-participation",
      })}</script>
      <script type="application/json" data-calendar-labels>${JSON.stringify({
        add_to_google_label: "Add to Google",
        event_website_label: "Event website",
        format_label: "Format",
        location_label: "Location",
        organizer_label: "Organizer",
        registration_label: "Registration",
        source_label: "Source",
      })}</script>
      <button data-calendar-previous></button>
      <button data-calendar-today></button>
      <button data-calendar-next></button>
      <h2 data-calendar-title></h2>
      <div data-calendar-weekdays></div>
      <div data-calendar-grid></div>
      <p data-calendar-status></p>
      <script type="application/json" data-calendar-events>${JSON.stringify([event])}</script>
    </section>
    <dialog data-event-dialog aria-labelledby="event-dialog-title">
      <div data-event-dialog-content></div>
    </dialog>
  `;
  const dialog = document.querySelector("dialog")!;
  dialog.showModal = vi.fn(() => dialog.setAttribute("open", ""));
  dialog.close = vi.fn(() => {
    dialog.removeAttribute("open");
    dialog.dispatchEvent(new Event("close"));
  });
});

describe("event calendar", () => {
  it("places days and multi-day events on the same calendar row", async () => {
    await import("../src/pages/event-calendar");

    const week = document.querySelector<HTMLElement>(
      '.month-calendar__day[data-date="2026-09-08"]',
    )!.parentElement!;
    const days = [
      ...week.querySelectorAll<HTMLElement>(".month-calendar__day"),
    ];
    const calendarEvent = week.querySelector<HTMLButtonElement>(
      ".month-calendar__event",
    )!;

    expect(days.map((day) => day.style.gridColumn)).toEqual([
      "1",
      "2",
      "3",
      "4",
      "5",
      "6",
      "7",
    ]);
    expect(calendarEvent.style.gridColumn).toBe("2 / 5");
    expect(calendarEvent.style.gridRow).toBe("");
  });

  it("does not render a redundant hover popover", async () => {
    await import("../src/pages/event-calendar");
    expect(document.querySelector(".month-calendar__popover")).toBeNull();
    expect(
      document
        .querySelector(".month-calendar__event")
        ?.hasAttribute("aria-describedby"),
    ).toBe(false);
  });

  it("opens complete event details in a dialog", async () => {
    await import("../src/pages/event-calendar");
    const calendarEvent = document.querySelector<HTMLButtonElement>(
      ".month-calendar__event",
    )!;
    const dialog = document.querySelector<HTMLDialogElement>(
      "[data-event-dialog]",
    )!;

    calendarEvent.click();

    expect(dialog.open).toBe(true);
    expect(dialog.textContent).toContain("Example C++ Conference");
    expect(dialog.textContent).toContain("Convention Center");
    expect(dialog.textContent).toContain("Three days of C++ talks");
    expect(
      dialog.querySelector<HTMLAnchorElement>(
        'a[href="https://example.com/event"]',
      )?.textContent,
    ).toBe("Event website");
    expect(document.documentElement.classList).toContain("has-event-dialog");

    dialog.querySelector<HTMLButtonElement>("[data-event-close]")!.click();
    await vi.waitFor(() => expect(dialog.open).toBe(false));
    expect(document.activeElement).toBe(calendarEvent);
  });

  it("explains participation for a non-public committee meeting", async () => {
    document.querySelector<HTMLScriptElement>(
      "[data-calendar-events]",
    )!.textContent = JSON.stringify([
      { ...event, event_type: "committee", public: false },
    ]);
    await import("../src/pages/event-calendar");

    document
      .querySelector<HTMLButtonElement>(".month-calendar__event")!
      .click();
    const notice = document.querySelector<HTMLElement>(
      ".event-detail__notice",
    )!;

    expect(notice.textContent).toContain("not a public drop-in meeting");
    expect(notice.querySelector("a")?.href).toBe(
      "https://isocpp.org/std/meetings-and-participation",
    );
  });
});
