(function () {
    "use strict";

    const calendar = document.querySelector("[data-event-calendar]");
    if (!calendar) return;

    const title = calendar.querySelector("[data-calendar-title]");
    const grid = calendar.querySelector("[data-calendar-grid]");
    const weekdays = calendar.querySelector("[data-calendar-weekdays]");
    const status = calendar.querySelector("[data-calendar-status]");
    const source = calendar.querySelector("[data-calendar-events]");
    const previous = calendar.querySelector("[data-calendar-previous]");
    const next = calendar.querySelector("[data-calendar-next]");
    const todayButton = calendar.querySelector("[data-calendar-today]");
    const events = JSON.parse(source.textContent).sort(
        (left, right) => left.start_date.localeCompare(right.start_date),
    );
    const today = new Date();
    today.setHours(0, 0, 0, 0);

    function dateFromIso(value) {
        const [year, month, day] = value.split("-").map(Number);
        return new Date(year, month - 1, day);
    }

    function isoDate(value) {
        return [
            value.getFullYear(),
            String(value.getMonth() + 1).padStart(2, "0"),
            String(value.getDate()).padStart(2, "0"),
        ].join("-");
    }

    function monthFromUrl() {
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

    function eventLabel(event) {
        const end = event.end_date || event.start_date;
        const dates = event.start_date === end
            ? dateFormatter.format(dateFromIso(event.start_date))
            : dateFormatter.format(dateFromIso(event.start_date)) + "–"
                + dateFormatter.format(dateFromIso(end));
        return event.title + ", " + dates
            + (event.location ? ", " + event.location : "");
    }

    function eventLink(event, currentDate) {
        const link = document.createElement("a");
        const end = event.end_date || event.start_date;
        const classes = [
            "month-calendar__event",
            "month-calendar__event--" + event.event_type,
        ];
        if (event.status !== "confirmed") {
            classes.push("month-calendar__event--" + event.status);
        }
        if (currentDate === event.start_date) classes.push("is-start");
        if (currentDate === end) classes.push("is-end");
        link.className = classes.join(" ");
        link.href = event.path || event.source_url;
        link.target = "_blank";
        link.rel = "noopener";
        link.textContent = event.title;
        link.setAttribute("aria-label", eventLabel(event));
        link.title = eventLabel(event);
        return link;
    }

    function eventStatus(monthStart, monthEnd, monthEvents) {
        status.replaceChildren();
        if (monthEvents.length) {
            status.textContent = String(monthEvents.length) + " "
                + (monthEvents.length === 1 ? "event" : "events")
                + " in " + monthFormatter.format(monthStart) + ".";
            return;
        }

        status.append("No events in " + monthFormatter.format(monthStart) + ".");
        const upcoming = events.find(
            (event) => dateFromIso(event.start_date) > monthEnd
                && event.status !== "cancelled",
        );
        if (!upcoming) return;
        status.append(" Next: ");
        const link = document.createElement("a");
        link.href = upcoming.path || upcoming.source_url;
        link.target = "_blank";
        link.rel = "noopener";
        link.textContent = upcoming.title + " on "
            + dateFormatter.format(dateFromIso(upcoming.start_date));
        status.append(link, ".");
    }

    function render() {
        grid.replaceChildren();
        title.textContent = monthFormatter.format(visibleMonth);
        const monthStart = new Date(
            visibleMonth.getFullYear(), visibleMonth.getMonth(), 1,
        );
        const monthEnd = new Date(
            visibleMonth.getFullYear(), visibleMonth.getMonth() + 1, 0,
        );
        const mondayOffset = (monthStart.getDay() + 6) % 7;
        const firstCell = new Date(monthStart);
        firstCell.setDate(firstCell.getDate() - mondayOffset);
        const monthEvents = events.filter((event) => (
            dateFromIso(event.start_date) <= monthEnd
            && dateFromIso(event.end_date || event.start_date) >= monthStart
        ));

        for (let offset = 0; offset < 42; offset += 1) {
            const day = new Date(firstCell);
            day.setDate(firstCell.getDate() + offset);
            const dayIso = isoDate(day);
            const cell = document.createElement("div");
            cell.className = "month-calendar__day";
            cell.setAttribute("role", "gridcell");
            cell.dataset.date = dayIso;
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

            const dayEvents = events.filter((event) => (
                event.start_date <= dayIso
                && (event.end_date || event.start_date) >= dayIso
            ));
            for (const event of dayEvents) {
                cell.append(eventLink(event, dayIso));
            }
            grid.append(cell);
        }

        eventStatus(monthStart, monthEnd, monthEvents);
        const url = new URL(window.location.href);
        const currentMonth = [
            visibleMonth.getFullYear(),
            String(visibleMonth.getMonth() + 1).padStart(2, "0"),
        ].join("-");
        url.searchParams.set("month", currentMonth);
        window.history.replaceState({}, "", url);
        todayButton.disabled = (
            visibleMonth.getFullYear() === today.getFullYear()
            && visibleMonth.getMonth() === today.getMonth()
        );
    }

    function moveMonth(offset) {
        visibleMonth = new Date(
            visibleMonth.getFullYear(), visibleMonth.getMonth() + offset, 1,
        );
        render();
    }

    previous.addEventListener("click", () => moveMonth(-1));
    next.addEventListener("click", () => moveMonth(1));
    todayButton.addEventListener("click", () => {
        visibleMonth = new Date(today.getFullYear(), today.getMonth(), 1);
        render();
    });

    render();
}());
