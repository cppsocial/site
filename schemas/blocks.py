from datetime import date, datetime, time
from typing import Annotated, Any, Literal

import markdown
from pydantic import model_validator
from site_generator import Schema, field, schema

from schemas.markdown import select_sections
from schemas.relevance import CppRelevance


@schema("blocks/link")
class Link(Schema):
    label: str
    path: str


@schema("blocks/markdown")
class Markdown(Schema):
    type: Literal["markdown"] = "markdown"
    content: str = ""
    include_headings: list[str] = field(default_factory=list)
    markdown_extensions: list[str] = field(default_factory=list)

    @model_validator(mode="after")
    def select_headings(self) -> "Markdown":
        if self.include_headings:
            self.content = select_sections(self.content, self.include_headings)
        if self.markdown_extensions:
            self.content = markdown.markdown(
                self.content, extensions=self.markdown_extensions
            )
        return self


class MetricBar(Schema):
    label: str
    value: str = ""
    percent: int = 0


class MetricBarGroup(Schema):
    title: str = ""
    bars: list[MetricBar] = field(default_factory=list)


@schema("blocks/metric-bars")
class MetricBars(Schema):
    type: Literal["metric_bars"] = "metric_bars"
    title: str = ""
    description: str = ""
    groups: list[MetricBarGroup] = field(default_factory=list)
    note: str = ""


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


class CommunityMetadataSource(Schema):
    source: Literal["discord", "web", "reddit", "stackoverflow"]
    key: str


@schema("blocks/community-card")
class CommunityCard(Card):
    type: Literal["community_card"] = "community_card"
    community_id: str
    platform: Literal["discord", "slack", "irc", "reddit", "forum"]
    metadata_source: CommunityMetadataSource


@schema("blocks/meetup-card")
class MeetupCard(Card):
    type: Literal["meetup_card"] = "meetup_card"
    source_id: str
    timezone: str = ""


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
    public: bool = True
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
    title: str = ""
    url: str = ""
    published: datetime | None = None
    updated: datetime | None = None
    description: str = ""
    thumbnail_url: str = ""
    tags: list[str] = field(default_factory=list)
    cpp_relevance: CppRelevance | None = None
    hidden: bool = False

    @model_validator(mode="after")
    def complete_unless_hidden(self) -> "CachedVideo":
        if not self.hidden and not all((self.title, self.url, self.published)):
            raise ValueError("visible cached videos require title, URL, and date")
        return self


GroupCard = Annotated[
    Card | BookCard | CommunityCard | MeetupCard | ChannelCard,
    field(discriminator="type"),
]
GroupCardType = Literal[
    "card", "book_card", "community_card", "meetup_card", "channel_card"
]


@schema("blocks/card-group")
class CardGroup(Schema):
    type: Literal["card_group"] = "card_group"
    card_type: GroupCardType = "card"
    id: str
    title: str = ""
    description: str = ""
    default_cta: str = ""
    cards: list[GroupCard] = field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def apply_default_card_type(cls, value: Any) -> Any:
        if not isinstance(value, dict) or not isinstance(value.get("cards"), list):
            return value

        card_type = value.get("card_type", "card")
        cards = [
            {"type": card_type, **card} if isinstance(card, dict) else card
            for card in value["cards"]
        ]
        return {**value, "cards": cards}


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
    Annotated[
        Markdown | CardGroup | MetricBars | StandardsTimeline,
        field(discriminator="type"),
    ]
    | str
)


@schema("blocks/navigation-item")
class NavigationItem(Schema):
    path: str
    label: str
    footer_group: str = ""
    footer_description: str = ""
