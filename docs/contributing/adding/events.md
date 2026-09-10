### Meetup groups

Add a group to the `cards` list in `content/events/meetups.yaml` only when it exposes a public Meetup iCalendar feed.
The updater imports individual occurrences from that feed.

```yaml
- type: meetup_card
  source_id: example-cpp
  timezone: Europe/Paris
  title: Example C++ Meetup
  path: https://www.meetup.com/example-cpp/
  description: Regular C++ meetup in Paris
  metadata:
    Location: Paris, France
  links:
    - {label: RSS feed, path: https://www.meetup.com/example-cpp/events/rss/}
    - {label: Calendar, path: https://www.meetup.com/example-cpp/events/ical/}
```

> [!IMPORTANT]
> **Include the meetup type**
>
> Set `type: meetup_card` on the entry itself. The event importer does not use the group's `card_type` default.

Use the group name from `meetup.com/<group-name>/` as `source_id`, lowercased.
Choose the group's timezone from [IANA's list](https://data.iana.org/time-zones/tzdb/zone1970.tab), for example `Europe/Paris`.
Copy the group calendar feed using [Meetup's export instructions](https://help.meetup.com/hc/en-us/articles/39237118960013-Exporting-an-event-to-your-calendar).
Include exactly one calendar link ending in `/events/ical/` (the trailing slash is optional).
Open the link to check that the feed is public.
Do not copy imported occurrences into `content/events/events.yaml`.

### Recurring series or dated occurrence

A recurring conference series is a directory card in `content/events/conferences.yaml`.
Move a series to `content/events/past-conferences.yaml` when it is no longer running.
Follow the Directory entries guide for that record.

Add a specific conference, workshop, committee meeting, or one-off meetup to the YAML list in `content/events/events.yaml`.

> [!WARNING]
> **Do not duplicate imported events**
>
> Meetup events from configured calendar feeds are imported automatically. Do not add them to `content/events/events.yaml`.

### Add a dated event

```yaml
- ical_uid: exampleconf-2027@cpp.social
  title: ExampleConf 2027
  description: Two-day conference focused on C++ systems programming
  start_date: 2027-04-12
  end_date: 2027-04-13
  location: Paris, France
  venue: Example Convention Centre
  format: in_person
  event_type: conference
  organizer: Example C++ Association
  path: https://example.org/2027/
  registration_url: https://example.org/2027/register/
  source_url: https://example.org/2027/announcement/
  source_name: ExampleConf
  last_verified: 2026-09-07
```

### Requirements

- Provide `ical_uid`, `title`, `start_date`, `event_type`, and `source_url`
- Provide the canonical event URL, format, organizer, location, and a useful factual description when available
- Keep `ical_uid` globally unique and stable; use a readable slug and year followed by `@cpp.social`
- Use ISO `YYYY-MM-DD` dates; `end_date` is the final day of the event
- Allowed `format` values are `in_person`, `online`, and `hybrid`
- Allowed `event_type` values are `conference`, `meetup`, `committee`, and `workshop`
- Omit `registration_url` or `venue` when they are not known
- `source_url` must link directly to first-party evidence for the date and location
- Set `status` to `tentative` or `cancelled` when applicable; otherwise omit it
- Set `last_verified` to the date on which the source was checked

> [!NOTE]
> **Times are optional**
>
> Omit `start_time` and `end_time` for multi-day events or when times are not published.
> For a single-day event, you may add its published start and end times as quoted `HH:MM` values, with a `timezone` from [IANA's list](https://data.iana.org/time-zones/tzdb/zone1970.tab).

> [!IMPORTANT]
> **Check the current announcement**
>
> Only add an event once the organizer has published its date.
> Do not reuse a previous year's location, venue, or format without checking the current announcement.

### Check the calendar

Run `make build` and inspect `/events/` in the build output.
Check multi-day boundaries, timezone labels, external links, and the generated calendar entry.
