import argparse
import hashlib
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from meta_updater.shared.provenance import finish_provenance_tracking, start_provenance_tracking, track_provenance
import yaml
from schemas.blocks import CalendarEvent

from ..config import MetaUpdaterConfig
from ..shared.dataset import YamlDataset
from ..shared.runtime import add_network_options, finish, network_values

DESCRIPTION = "Refresh dated events from public iCalendar feeds."


def configure(parser: argparse.ArgumentParser) -> None:
    add_network_options(parser, delay=False)
    parser.set_defaults(handler=run)


def fetch(url: str, timeout: float) -> str:
    request = Request(
        url,
        headers={
            "Accept": "text/calendar",
            "User-Agent": "cpp.social event calendar (+https://cpp.social/contributing/)",
        },
    )
    track_provenance(url)
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8-sig", errors="replace")


def source_records(source_path: Path) -> list[dict]:
    values = yaml.safe_load(source_path.read_text(encoding="utf-8"))
    if not isinstance(values, list):
        raise ValueError(f"{source_path}: expected a list")
    ids = [value["id"] for value in values]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{source_path}: duplicate source id")
    return values


def unfold_ical(document: str) -> list[str]:
    unfolded: list[str] = []
    for line in document.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if line.startswith((" ", "\t")) and unfolded:
            unfolded[-1] += line[1:]
        else:
            unfolded.append(line)
    return unfolded


def ical_unescape(value: str) -> str:
    return (
        value.replace("\\N", "\n")
        .replace("\\n", "\n")
        .replace("\\,", ",")
        .replace("\\;", ";")
        .replace("\\\\", "\\")
    )


def ical_properties(lines: list[str]) -> list[dict[str, tuple[dict[str, str], str]]]:
    events: list[dict[str, tuple[dict[str, str], str]]] = []
    current: dict[str, tuple[dict[str, str], str]] | None = None
    for line in lines:
        if line == "BEGIN:VEVENT":
            current = {}
            continue
        if line == "END:VEVENT":
            if current is not None:
                events.append(current)
            current = None
            continue
        if current is None or ":" not in line:
            continue
        head, value = line.split(":", 1)
        parts = head.split(";")
        params = {}
        for part in parts[1:]:
            if "=" in part:
                key, parameter = part.split("=", 1)
                params[key.upper()] = parameter.strip('"')
        current[parts[0].upper()] = (params, ical_unescape(value))
    return events


def parse_ical_value(
    property_value: tuple[dict[str, str], str],
    fallback_zone: str,
) -> tuple[date, datetime | None, str]:
    params, value = property_value
    if params.get("VALUE") == "DATE" or len(value) == 8:
        return datetime.strptime(value[:8], "%Y%m%d").date(), None, ""
    zone_name = params.get("TZID", fallback_zone)
    if value.endswith("Z"):
        parsed = datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        if fallback_zone:
            parsed = parsed.astimezone(ZoneInfo(fallback_zone))
            zone_name = fallback_zone
    else:
        parsed = datetime.strptime(value[:15], "%Y%m%dT%H%M%S")
        parsed = parsed.replace(tzinfo=ZoneInfo(zone_name) if zone_name else UTC)
    return parsed.date(), parsed, zone_name


def stable_meetup_id(source_id: str, raw: dict, start: date) -> str:
    identity = raw.get("UID", ({}, ""))[1]
    if not identity:
        identity = f"{raw.get('SUMMARY', ({}, ''))[1]}\0{start.isoformat()}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return f"{source_id}-{digest}@cpp.social"


def meetup_events(source: dict, document: str, checked: date) -> list[dict]:
    events = []
    for raw in ical_properties(unfold_ical(document)):
        if "DTSTART" not in raw or "SUMMARY" not in raw:
            continue
        start_date, start_at, zone_name = parse_ical_value(
            raw["DTSTART"], source.get("timezone", "")
        )
        end_date = start_date
        end_at = None
        if "DTEND" in raw:
            end_date, end_at, end_zone = parse_ical_value(
                raw["DTEND"], zone_name or source.get("timezone", "")
            )
            zone_name = zone_name or end_zone
            if start_at is None and end_at is None:
                end_date -= timedelta(days=1)
        status = raw.get("STATUS", ({}, "CONFIRMED"))[1].lower()
        if status not in {"confirmed", "tentative", "cancelled"}:
            status = "confirmed"
        event_url = raw.get("URL", ({}, source.get("homepage", "")))[1]
        organizer = source["organizer"]
        if "ORGANIZER" in raw:
            organizer = raw["ORGANIZER"][0].get("CN", organizer)
        location = raw.get("LOCATION", ({}, source.get("default_location", "")))[1]
        event = {
            "ical_uid": stable_meetup_id(source["id"], raw, start_date),
            "title": raw["SUMMARY"][1],
            "description": raw.get("DESCRIPTION", ({}, ""))[1],
            "start_date": start_date,
            "end_date": end_date,
            "timezone": zone_name,
            "location": location,
            "format": source["format"],
            "event_type": source["event_type"],
            "organizer": organizer,
            "status": status,
            "path": event_url,
            "source_url": source["url"],
            "source_name": source["source_name"],
            "last_verified": checked.isoformat(),
        }
        if start_at:
            event["start_time"] = start_at.timetz().replace(tzinfo=None)
        if end_at:
            event["end_time"] = end_at.timetz().replace(tzinfo=None)
        events.append(event)
    return events


def refresh(source_path: Path, timeout: float) -> list[CalendarEvent]:
    checked = date.today()
    records: list[dict] = []
    for source in source_records(source_path):
        if source["kind"] != "meetup_ical":
            raise ValueError(f"unknown event source kind: {source['kind']}")
        found = meetup_events(source, fetch(source["url"], timeout), checked)
        print(f"{source['id']}: {len(found)} dated events")
        records.extend(found)
    records.sort(key=lambda event: (event["start_date"], event["title"]))
    return [CalendarEvent.model_validate(event) for event in records]


def run(args: argparse.Namespace, config: MetaUpdaterConfig) -> int:
    timeout, _ = network_values(args, config)
    dataset = YamlDataset(
        config.data / "events-imported.yaml",
        list[CalendarEvent],
        "meta-updater events",
        "Meetup events come from public organizer iCalendar feeds.",
        exclude_none=True,
        exclude_defaults=True,
    )
    start_provenance_tracking(config.data / "events" / "provenance.yaml")
    changed = dataset.update(
        refresh(config.content / "events" / "sources.yaml", timeout), args.check
    )
    if changed:
        finish_provenance_tracking()
    return finish(changed, args.check, "event")
