from datetime import date, datetime, time
from typing import Annotated, Literal

from site_generator import Schema, field, schema

from schemas.relevance import CppRelevance


@schema("blocks/link")
class Link(Schema):
    label: str
    path: str


@schema("blocks/markdown")
class Markdown(Schema):
    type: Literal["markdown"] = "markdown"
    content: str = ""


@schema("blocks/card")
class Card(Schema):
    type: Literal["card"] = "card"
    hidden: bool = False
    title: str
    description: str = ""
    path: str = ""
    # Omit this field to discover the site's favicon; use null to disable icons.
    icon: str | None = ""
    cta: str = ""
    metadata: dict[str, str] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    items: list[str] = field(default_factory=list)


@schema("blocks/book-card")
class BookCard(Schema):
    type: Literal["book_card"] = "book_card"
    isbn: str
    cover_url: str = ""
    hidden: bool = False


@schema("books/metadata")
class BookMetadata(Schema):
    title: str
    authors: list[str] = field(default_factory=list)
    subtitle: str = ""
    description: str = ""
    isbn_13: str
    isbn_10: str = ""
    publisher: str = ""
    publish_date: str = ""
    pages: int | None = None
    cover_url: str = ""
    url: str
    work_key: str = ""
    subjects: list[str] = field(default_factory=list)
    rating: float | None = None
    rating_count: int = 0


@schema("blocks/discord-card")
class DiscordCard(Card):
    type: Literal["discord_card"] = "discord_card"


@schema("blocks/community-card")
class CommunityCard(Card):
    type: Literal["community_card"] = "community_card"
    community_id: str
    platform: Literal["discord", "slack", "irc", "reddit", "forum"]


@schema("communities/metadata")
class CommunityMetadata(Schema):
    description: str = ""
    avatar_url: str = ""
    banner_url: str = ""
    member_count: int | None = None
    weekly_visitors: int | None = None
    weekly_contributions: int | None = None
    source_url: str = ""

@schema("provenance")
class Provenance(Schema):
    retrieved_at: str = ""
    source_urls: list[str] = field(default_factory=list)

@schema("blocks/event-card")
class EventCard(Card):
    type: Literal["event_card"] = "event_card"
    start_date: date
    end_date: date | None = None
    location: str = ""
    format: Literal["in_person", "online", "hybrid"] = "in_person"


class CalendarEvent(Schema):
    """A dated, source-backed entry in the public C++ event calendar."""

    ical_uid: str
    title: str
    description: str = ""
    start_date: date
    end_date: date | None = None
    start_time: time | None = None
    end_time: time | None = None
    timezone: str = ""
    location: str = ""
    venue: str = ""
    format: Literal["in_person", "online", "hybrid"] = "in_person"
    event_type: Literal["conference", "meetup", "committee", "workshop"]
    organizer: str = ""
    status: Literal["confirmed", "tentative", "cancelled"] = "confirmed"
    path: str = ""
    registration_url: str = ""
    source_url: str
    source_name: str = ""
    last_verified: date | None = None


@schema("blocks/channel-card")
class ChannelCard(Card):
    type: Literal["channel_card"] = "channel_card"
    channel_type: Literal["creator", "conference", "organization", "show"]
    channel_id: str


@schema("youtube/channel-metadata")
class ChannelMetadata(Schema):
    url: str
    description: str = ""
    keywords: list[str] = field(default_factory=list)
    avatar_url: str = ""
    banner_url: str = ""
    source_url: str = ""


@schema("youtube/cached-video")
class CachedVideo(Schema):
    video_id: str
    title: str
    url: str
    published: datetime
    updated: datetime | None = None
    description: str = ""
    thumbnail_url: str = ""
    tags: list[str] = field(default_factory=list)
    cpp_relevance: CppRelevance | None = None
    hidden: bool = False


@schema("blocks/video-card")
class VideoCard(Card):
    type: Literal["video_card"] = "video_card"
    channel: str
    published: date | None = None
    thumbnail: str = ""


GroupCard = Annotated[
    Card | BookCard | DiscordCard | CommunityCard | EventCard | ChannelCard | VideoCard,
    field(discriminator="type"),
]


@schema("blocks/card-group")
class CardGroup(Schema):
    type: Literal["card_group"] = "card_group"
    title: str
    description: str = ""
    search_category: str = ""
    layout: Literal["grid", "showcase", "rail"] = "grid"
    default_cta: str = ""
    page_rows: int = 0
    randomize: bool = False
    cards: list[GroupCard] = field(default_factory=list)


class StandardRelease(Schema):
    title: str
    publication: str
    status: str
    description: str = ""
    features: list[str] = field(default_factory=list)
    cppstat: str
    draft_pdf: str
    draft_html: str = ""
    draft_name: str


@schema("blocks/standards-timeline")
class StandardsTimeline(Schema):
    type: Literal["standards_timeline"] = "standards_timeline"
    title: str
    description: str = ""
    standards: list[StandardRelease] = field(default_factory=list)


ContentBlock = (
    Annotated[Markdown | CardGroup | StandardsTimeline, field(discriminator="type")]
    | str
)


@schema("blocks/navigation-item")
class NavigationItem(Schema):
    path: str
    label: str


@schema("blocks/home-card")
class HomeCard(Schema):
    type: Literal["home_card"] = "home_card"
    title: str
    description: str = ""
    path: str = ""
    icon: str = ""
    icon_type: Literal["File", "Unicode"] = "File"
    cta: str = ""
