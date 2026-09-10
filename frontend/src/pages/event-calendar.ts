import { TemplateDialogController } from "../shared/dialog";
import { parseJsonScript, queryRequired } from "../shared/dom";
import { initStoredChoice } from "../shared/choice";

interface CalendarEvent {
  description?: string;
  end_date?: string;
  event_type: string;
  format?: string;
  location?: string;
  organizer?: string;
  path?: string;
  public?: boolean;
  registration_url?: string;
  source_url: string;
  start_date: string;
  status: string;
  title: string;
  venue?: string;
}

interface CalendarCopy {
  close_label: string;
  date_label: string;
  event_plural: string;
  event_singular: string;
  in_label: string;
  next_prefix: string;
  non_public_note: string;
  no_events_prefix: string;
  on_label: string;
  participation_label: string;
  participation_url: string;
}

interface CalendarLabels {
  add_to_google_label: string;
  event_website_label: string;
  format_label: string;
  location_label: string;
  organizer_label: string;
  registration_label: string;
  source_label: string;
}

(function () {
  "use strict";

  const viewButtons = [
    ...document.querySelectorAll<HTMLButtonElement>("[data-event-view]"),
  ];
  const upcomingView = document.querySelector<HTMLElement>(
    "[data-event-upcoming-view]",
  );
  const calendarView = document.querySelector<HTMLElement>(
    "[data-event-calendar-view]",
  );

  if (upcomingView && calendarView) {
    initStoredChoice<"upcoming" | "calendar">({
      apply: (view) => {
        upcomingView.hidden = view !== "upcoming";
        calendarView.hidden = view !== "calendar";
      },
      buttons: viewButtons,
      initial: "upcoming",
      storageKey: "event-view",
      value: (button) =>
        button.dataset.eventView === "calendar" ? "calendar" : "upcoming",
    });
  }

  const calendar = document.querySelector<HTMLElement>("[data-event-calendar]");
  if (!calendar) return;

  const title = queryRequired<HTMLElement>(calendar, "[data-calendar-title]");
  const grid = queryRequired<HTMLElement>(calendar, "[data-calendar-grid]");
  const weekdays = queryRequired<HTMLElement>(
    calendar,
    "[data-calendar-weekdays]",
  );
  const status = queryRequired<HTMLElement>(calendar, "[data-calendar-status]");
  const copy = parseJsonScript<CalendarCopy>(calendar, "[data-calendar-copy]");
  const labels = parseJsonScript<CalendarLabels>(
    calendar,
    "[data-calendar-labels]",
  );
  const previous = queryRequired<HTMLButtonElement>(
    calendar,
    "[data-calendar-previous]",
  );
  const next = queryRequired<HTMLButtonElement>(
    calendar,
    "[data-calendar-next]",
  );
  const todayButton = queryRequired<HTMLButtonElement>(
    calendar,
    "[data-calendar-today]",
  );
  const events = parseJsonScript<CalendarEvent[]>(
    calendar,
    "[data-calendar-events]",
  ).sort((left, right) => left.start_date.localeCompare(right.start_date));
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  function dateFromIso(value: string): Date {
    const [year, month, day] = value.split("-").map(Number);
    return new Date(year, month - 1, day);
  }

  function isoDate(value: Date): string {
    return [
      value.getFullYear(),
      String(value.getMonth() + 1).padStart(2, "0"),
      String(value.getDate()).padStart(2, "0"),
    ].join("-");
  }

  function monthFromUrl(): Date {
    const value = new URL(window.location.href).searchParams.get("month");
    const match = value?.match(/^(\d{4})-(\d{2})$/);
    if (!match || Number(match[2]) < 1 || Number(match[2]) > 12) {
      return new Date(today.getFullYear(), today.getMonth(), 1);
    }
    return new Date(Number(match[1]), Number(match[2]) - 1, 1);
  }

  let visibleMonth = monthFromUrl();

  const weekdayFormatter = new Intl.DateTimeFormat(undefined, {
    weekday: "short",
  });
  const monthFormatter = new Intl.DateTimeFormat(undefined, {
    month: "long",
    year: "numeric",
  });
  const dateFormatter = new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
  const monday = new Date(2024, 0, 1);
  for (let offset = 0; offset < 7; offset += 1) {
    const heading = document.createElement("div");
    const day = new Date(monday);
    day.setDate(monday.getDate() + offset);
    heading.textContent = weekdayFormatter.format(day);
    heading.setAttribute("role", "columnheader");
    weekdays.append(heading);
  }

  function eventDateLabel(event: CalendarEvent): string {
    const end = event.end_date || event.start_date;
    return event.start_date === end
      ? dateFormatter.format(dateFromIso(event.start_date))
      : dateFormatter.format(dateFromIso(event.start_date)) +
          "–" +
          dateFormatter.format(dateFromIso(end));
  }

  function eventLabel(event: CalendarEvent): string {
    return (
      event.title +
      ", " +
      eventDateLabel(event) +
      (event.location ? ", " + event.location : "")
    );
  }

  function appendFact(
    facts: HTMLDListElement,
    label: string,
    value: string,
  ): void {
    const row = document.createElement("div");
    const term = document.createElement("dt");
    const description = document.createElement("dd");
    term.textContent = label;
    description.textContent = value;
    row.append(term, description);
    facts.append(row);
  }

  function externalLink(label: string, href: string): HTMLAnchorElement {
    const link = document.createElement("a");
    link.href = href;
    link.target = "_blank";
    link.rel = "noopener";
    link.textContent = label;
    return link;
  }

  function googleCalendarUrl(event: CalendarEvent): string {
    const exclusiveEnd = dateFromIso(event.end_date || event.start_date);
    exclusiveEnd.setDate(exclusiveEnd.getDate() + 1);
    const compact = (value: string) => value.replaceAll("-", "");
    const parameters = new URLSearchParams({
      action: "TEMPLATE",
      dates: `${compact(event.start_date)}/${compact(isoDate(exclusiveEnd))}`,
      details: [event.description, `Source: ${event.source_url}`]
        .filter(Boolean)
        .join("\n\n"),
      location: event.location || "",
      text: event.title,
    });
    return `https://calendar.google.com/calendar/render?${parameters}`;
  }

  function eventDetails(event: CalendarEvent): DocumentFragment {
    const fragment = document.createDocumentFragment();
    const article = document.createElement("article");
    article.className = "event-detail";
    const close = document.createElement("button");
    close.className = "book-dialog__close";
    close.type = "button";
    close.dataset.eventClose = "";
    close.setAttribute("aria-label", copy.close_label);
    close.textContent = "×";
    const kind = document.createElement("p");
    kind.className = "calendar-event__kind";
    kind.textContent =
      event.event_type.replaceAll("_", " ") +
      (event.status === "confirmed" ? "" : ` · ${event.status}`);
    const heading = document.createElement("h2");
    heading.id = "event-dialog-title";
    heading.textContent = event.title;
    article.append(close, kind, heading);
    if (event.description) {
      const description = document.createElement("p");
      description.className = "event-detail__description";
      description.textContent = event.description;
      article.append(description);
    }
    if (event.public === false) {
      const notice = document.createElement("aside");
      notice.className = "event-detail__notice";
      const message = document.createElement("strong");
      message.textContent = copy.non_public_note;
      const participation = externalLink(
        copy.participation_label,
        copy.participation_url,
      );
      notice.append(message, participation);
      article.append(notice);
    }
    const facts = document.createElement("dl");
    facts.className = "event-detail__facts";
    appendFact(facts, copy.date_label, eventDateLabel(event));
    const location = [event.venue, event.location].filter(Boolean).join(", ");
    if (location) appendFact(facts, labels.location_label, location);
    if (event.organizer) {
      appendFact(facts, labels.organizer_label, event.organizer);
    }
    if (event.format) {
      const format = event.format.replaceAll("_", " ");
      appendFact(
        facts,
        labels.format_label,
        format.charAt(0).toUpperCase() + format.slice(1),
      );
    }
    article.append(facts);
    const links = document.createElement("nav");
    links.className = "event-detail__links";
    if (event.path) {
      links.append(externalLink(labels.event_website_label, event.path));
    }
    if (event.registration_url && event.registration_url !== event.path) {
      links.append(
        externalLink(labels.registration_label, event.registration_url),
      );
    }
    links.append(
      externalLink(labels.add_to_google_label, googleCalendarUrl(event)),
      externalLink(labels.source_label, event.source_url),
    );
    article.append(links);
    fragment.append(article);
    return fragment;
  }

  function eventLink(
    event: CalendarEvent,
    segmentStart: string,
    segmentEnd: string,
    lane: number,
  ): HTMLButtonElement {
    const link = document.createElement("button");
    link.type = "button";
    const end = event.end_date || event.start_date;
    const classes = [
      "month-calendar__event",
      "month-calendar__event--" + event.event_type,
    ];
    if (event.status !== "confirmed") {
      classes.push("month-calendar__event--" + event.status);
    }
    if (segmentStart === event.start_date) classes.push("is-start");
    if (segmentEnd === end) classes.push("is-end");
    link.className = classes.join(" ");
    link.style.setProperty("--calendar-event-lane", String(lane));
    link.dataset.eventCard = "";
    link.dataset.eventOpen = "";
    link.setAttribute("aria-haspopup", "dialog");
    const label = document.createElement("span");
    label.className = "month-calendar__event-label";
    label.textContent = event.title;
    const template = document.createElement("template");
    template.dataset.eventDetails = "";
    template.content.append(eventDetails(event));
    link.append(label, template);
    link.setAttribute("aria-label", eventLabel(event));
    return link;
  }

  function eventStatus(
    monthStart: Date,
    monthEnd: Date,
    monthEvents: CalendarEvent[],
  ): void {
    status.replaceChildren();
    if (monthEvents.length) {
      status.textContent =
        String(monthEvents.length) +
        " " +
        (monthEvents.length === 1 ? copy.event_singular : copy.event_plural) +
        " " +
        copy.in_label +
        " " +
        monthFormatter.format(monthStart) +
        ".";
      return;
    }

    status.append(
      copy.no_events_prefix + " " + monthFormatter.format(monthStart) + ".",
    );
    const upcoming = events.find(
      (event) =>
        dateFromIso(event.start_date) > monthEnd &&
        event.status !== "cancelled",
    );
    if (!upcoming) return;
    status.append(" " + copy.next_prefix + " ");
    const link = document.createElement("a");
    link.href = upcoming.path || upcoming.source_url;
    link.target = "_blank";
    link.rel = "noopener";
    link.textContent =
      upcoming.title +
      " " +
      copy.on_label +
      " " +
      dateFormatter.format(dateFromIso(upcoming.start_date));
    status.append(link, ".");
  }

  function render(): void {
    grid.replaceChildren();
    title.textContent = monthFormatter.format(visibleMonth);
    const monthStart = new Date(
      visibleMonth.getFullYear(),
      visibleMonth.getMonth(),
      1,
    );
    const monthEnd = new Date(
      visibleMonth.getFullYear(),
      visibleMonth.getMonth() + 1,
      0,
    );
    const mondayOffset = (monthStart.getDay() + 6) % 7;
    const firstCell = new Date(monthStart);
    firstCell.setDate(firstCell.getDate() - mondayOffset);
    const monthEvents = events.filter(
      (event) =>
        dateFromIso(event.start_date) <= monthEnd &&
        dateFromIso(event.end_date || event.start_date) >= monthStart,
    );

    for (let weekOffset = 0; weekOffset < 42; weekOffset += 7) {
      const week = document.createElement("div");
      week.className = "month-calendar__week";
      week.setAttribute("role", "row");
      const weekStart = new Date(firstCell);
      weekStart.setDate(firstCell.getDate() + weekOffset);
      const weekEnd = new Date(weekStart);
      weekEnd.setDate(weekStart.getDate() + 6);
      const weekStartIso = isoDate(weekStart);
      const weekEndIso = isoDate(weekEnd);

      for (let dayOffset = 0; dayOffset < 7; dayOffset += 1) {
        const day = new Date(weekStart);
        day.setDate(weekStart.getDate() + dayOffset);
        const dayIso = isoDate(day);
        const cell = document.createElement("div");
        cell.className = "month-calendar__day";
        cell.setAttribute("role", "gridcell");
        cell.dataset.date = dayIso;
        cell.style.gridColumn = String(dayOffset + 1);
        if (day.getMonth() !== visibleMonth.getMonth()) {
          cell.classList.add("is-outside");
        }
        if (day.getTime() === today.getTime()) {
          cell.classList.add("is-today");
          cell.setAttribute("aria-current", "date");
        }

        const number = document.createElement("time");
        number.className = "month-calendar__date";
        number.dateTime = dayIso;
        number.textContent = String(day.getDate());
        cell.append(number);
        week.append(cell);
      }

      const weekEvents = events
        .filter(
          (event) =>
            event.start_date <= weekEndIso &&
            (event.end_date || event.start_date) >= weekStartIso,
        )
        .map((event) => ({
          event,
          start:
            event.start_date < weekStartIso ? weekStartIso : event.start_date,
          end:
            (event.end_date || event.start_date) > weekEndIso
              ? weekEndIso
              : event.end_date || event.start_date,
        }))
        .sort(
          (left, right) =>
            left.start.localeCompare(right.start) ||
            right.end.localeCompare(left.end) ||
            left.event.title.localeCompare(right.event.title),
        );
      const laneEnds: string[] = [];
      for (const segment of weekEvents) {
        let lane = laneEnds.findIndex((end) => end < segment.start);
        if (lane === -1) lane = laneEnds.length;
        laneEnds[lane] = segment.end;
        const link = eventLink(segment.event, segment.start, segment.end, lane);
        const startColumn =
          Math.round(
            (dateFromIso(segment.start).getTime() - weekStart.getTime()) /
              86_400_000,
          ) + 1;
        const endColumn =
          Math.round(
            (dateFromIso(segment.end).getTime() - weekStart.getTime()) /
              86_400_000,
          ) + 2;
        link.style.gridColumn = `${startColumn} / ${endColumn}`;
        week.append(link);
      }
      week.style.setProperty("--calendar-event-lanes", String(laneEnds.length));
      grid.append(week);
    }

    eventStatus(monthStart, monthEnd, monthEvents);
    const url = new URL(window.location.href);
    const currentMonth = [
      visibleMonth.getFullYear(),
      String(visibleMonth.getMonth() + 1).padStart(2, "0"),
    ].join("-");
    url.searchParams.set("month", currentMonth);
    window.history.replaceState({}, "", url);
    todayButton.disabled =
      visibleMonth.getFullYear() === today.getFullYear() &&
      visibleMonth.getMonth() === today.getMonth();
  }

  function moveMonth(offset: number): void {
    visibleMonth = new Date(
      visibleMonth.getFullYear(),
      visibleMonth.getMonth() + offset,
      1,
    );
    render();
  }

  previous.addEventListener("click", () => moveMonth(-1));
  next.addEventListener("click", () => moveMonth(1));
  todayButton.addEventListener("click", () => {
    visibleMonth = new Date(today.getFullYear(), today.getMonth(), 1);
    render();
  });

  const dialog = document.querySelector<HTMLDialogElement>(
    "[data-event-dialog]",
  );
  const dialogContent = dialog?.querySelector<HTMLElement>(
    "[data-event-dialog-content]",
  );
  if (dialog && dialogContent) {
    new TemplateDialogController({
      cardSelector: "[data-event-card]",
      closeSelector: "[data-event-close]",
      content: dialogContent,
      dialog,
      documentClass: "has-event-dialog",
      openSelector: "[data-event-open]",
      templateSelector: "[data-event-details]",
    });
  }

  render();
})();
