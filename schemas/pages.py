from typing import Any

from site_generator import Schema, field, schema

from schemas.blocks import (
    BookMetadata,
    CachedVideo,
    CalendarEvent,
    ChannelMetadata,
    CommunityMetadata,
    ContentBlock,
    HomeCard,
    NavigationItem,
)
from schemas.relevance import CppRelevance


@schema("pages/page", template="page.html")
class Page(Schema):
    title: str = ""
    description: str = ""
    searchable: bool = False
    search_placeholder: str = "Search by name, topic, or description"
    empty_message: str = "No matching entries found."
    advanced_search: bool = False
    search_fields: dict[str, str] = field(default_factory=dict)
    search_categories: dict[str, str] = field(default_factory=dict)
    search_date_range: bool = False
    search_relevance_filter: bool = False
    hide_non_cards_while_searching: bool = False
    cpp_relevance_threshold: CppRelevance = 0.5
    provenance: dict[str, Any] = field(default_factory=dict)
    body: list[ContentBlock] = field(default_factory=list)


@schema("pages/youtube", template="youtube.html")
class YouTube(Page):
    latest_rows: int = 1
    channel_metadata: dict[str, ChannelMetadata] = field(default_factory=dict)
    video_cache: dict[str, list[CachedVideo]] = field(default_factory=dict)


@schema("pages/article", template="article.html")
class Article(Schema):
    title: str = ""
    path: str = ""
    description: str = ""
    home_cards: list[HomeCard] | str = field(default_factory=list)
    navigation: list[NavigationItem] = field(default_factory=list)
    footer: list[NavigationItem] = field(default_factory=list)


@schema("pages/communities", template="communities.html")
class Communities(Schema):
    title: str = ""
    description: str = ""
    searchable: bool = True
    search_placeholder: str = "Search communities by name, platform, or topic"
    empty_message: str = "No matching communities found."
    community_metadata: dict[str, CommunityMetadata] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    body: list[ContentBlock] = field(default_factory=list)


@schema("pages/cards", template="cards.html")
class Cards(Page):
    home_cards: list[HomeCard] = field(default_factory=list)


@schema("pages/resources", template="resources.html")
class Resources(Page):
    book_metadata: dict[str, BookMetadata] = field(default_factory=dict)


class EventCatalog(Schema):
    title: str = "Events"
    description: str = ""
    calendar_url: str = "/events/calendar/"
    feed_url: str = "https://cpp.social/events/calendar.ics"
    upcoming_count: int = 4
    events: list[CalendarEvent] = field(default_factory=list)
    imported_events: list[CalendarEvent] = field(default_factory=list)


@schema("pages/events", template="events.html")
class Events(EventCatalog):
    searchable: bool = True
    search_placeholder: str = "Search events and event communities"
    empty_message: str = "No matching events or event communities found."
    body: list[ContentBlock] = field(default_factory=list)


@schema("pages/event-calendar", template="event_calendar.html")
class EventCalendar(EventCatalog):
    pass


@schema("pages/event-calendar-feed", template="event_calendar.ics")
class EventCalendarFeed(Schema):
    calendar_name: str = "C++ Community Events"
    description: str = "Conferences, meetups, and WG21 meetings for the C++ community."
    product_id: str = "-//cpp.social//C++ Community Events//EN"
    events: list[CalendarEvent] = field(default_factory=list)
    imported_events: list[CalendarEvent] = field(default_factory=list)
