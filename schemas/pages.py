from typing import Annotated, Any, Literal

import markdown
from pydantic import computed_field, model_validator
from site_generator import Schema, field, schema

from schemas.blocks import (
    BookMetadata,
    CachedVideo,
    CalendarEvent,
    ChannelMetadata,
    CommunityMetadata,
    ContentBlock,
    MetricBars,
    NavigationItem,
)
from schemas.markdown import GitHubAdmonitionsExtension
from schemas.relevance import CppRelevance


class SearchContent(Schema):
    placeholder: str = ""
    empty_message: str = ""
    fields: dict[str, str] = field(default_factory=dict)
    categories: dict[str, str] = field(default_factory=dict)
    managers: dict[str, str] = field(default_factory=dict)
    labels: dict[str, str] = field(default_factory=dict)


class SearchPresentation(Schema):
    enabled: bool = False
    database: bool = False
    feed_cards: bool = False
    package_catalog: bool = False
    advanced: bool = False
    options_expanded: bool = False
    date_range: bool = False
    date_histogram: bool = False
    relevance_filter: bool = False
    cpp_relevance_threshold: CppRelevance = 0.5


class SectionPresentation(Schema):
    layout: str = "grid"
    page_rows: int = 0
    page_step: int = 0
    collapsible: bool = True
    randomize: bool = False
    search_category: str = ""
    deferred_index: str = ""


class CodeEditorPresentation(Schema):
    compiler: str = "clang2110"
    args: str = "-std=c++23"
    height: str = "350px"
    min_height: str = "240px"


class SiteConfig(Schema):
    language: str = "en"
    name: str
    origin: str
    logo_mark: str
    description: str = ""
    logo: str = "/favicon.png"
    social_image: str = ""
    social_image_alt: str = ""
    title_separator: str = ""
    announcement: str = ""


class SiteUiText(Schema):
    skip_link: str
    menu_label: str
    primary_navigation_label: str
    theme_toggle_label: str
    footer_label: str
    project_group_label: str
    calendar_feed_title: str


class SearchUiText(Schema):
    label_prefix: str
    filters_label: str
    active_filters_label: str
    clear_label: str
    fields_legend: str
    categories_legend: str
    managers_legend: str
    published_legend: str
    from_label: str
    through_label: str
    publication_timeline_label: str
    all_years_label: str
    include_unrelated_label: str
    pagination_label: str
    previous_label: str
    next_label: str
    entry_singular: str
    entry_plural: str
    packages_plural: str
    package_singular: str
    minimum_query: str
    indexing: str
    unavailable: str
    remove_prefix: str
    requirement_suffix: str
    remove_packages_prefix: str
    open_to_load: str
    continue_reading: str
    hide_label: str
    show_label: str
    section_fallback: str
    matched_suffix: str
    count_matches_prompt: str
    counting_matches: str
    reloading_matches: str


class ProvenanceUiText(Schema):
    default_label: str
    external_label: str
    description: str
    retrieved_prefix: str


class CardUiText(Schema):
    location_label: str
    organizer_label: str
    format_label: str
    topics_label: str
    event_website_label: str
    registration_label: str
    add_to_google_label: str
    source_label: str
    checked_label: str
    weekly_visitors_label: str
    weekly_contributions_label: str
    members_suffix: str
    watch_prefix: str
    youtube_suffix: str
    links_suffix: str
    references_suffix: str


class UiText(Schema):
    site: SiteUiText
    search: SearchUiText
    provenance: ProvenanceUiText
    cards: CardUiText


class LatestUiText(Schema):
    continue_reading: str = ""


class BrowseUiText(Schema):
    author_prefix: str = ""
    read_blog: str = ""
    rss: str = ""


class UpcomingUiText(Schema):
    eyebrow: str = ""
    calendar_options: str = ""
    view_label: str = ""
    upcoming_view: str = ""
    calendar_view: str = ""
    subscribe: str = ""
    add_to_google_calendar: str = ""
    empty_title: str = ""
    empty_description: str = ""


class DialogUiText(Schema):
    layout_label: str = ""
    view_details_prefix: str = ""
    cover_prefix: str = ""
    no_cover: str = ""
    publisher: str = ""
    published: str = ""
    isbn: str = ""
    close_label: str = ""
    cover_unavailable: str = ""
    author_prefix: str = ""
    metadata_title: str = ""
    isbn_13: str = ""
    isbn_10: str = ""
    pages: str = ""
    metadata_source: str = ""
    ratings_title: str = ""
    open_library: str = ""
    loading: str = ""
    subjects_title: str = ""
    find_title: str = ""
    find_description: str = ""
    places_prefix: str = ""
    retailers: dict[str, str] = field(default_factory=dict)
    catalog_record: str = ""
    ratings_suffix: str = ""
    retrieved_live: str = ""
    cached_rating: str = ""
    unavailable: str = ""
    no_public_ratings: str = ""
    channel_suffix: str = ""
    keywords_label: str = ""
    watch_on_youtube: str = ""
    recent_videos: str = ""
    recent_empty: str = ""
    about_label: str = ""
    missing_description: str = ""


class CatalogUiText(Schema):
    package: str = ""
    description: str = ""
    managers: str = ""
    license: str = ""


class GraphUiText(Schema):
    view_label: str = ""
    list: str = ""
    graph: str = ""
    eyebrow: str = ""
    title: str = ""
    loading: str = ""
    fullscreen: str = ""
    exit_fullscreen: str = ""
    hint: str = ""


class DetailsUiText(Schema):
    dependencies: str = ""
    license: str = ""
    releases: str = ""
    version: str = ""
    release_metadata: str = ""
    release_details: str = ""
    preferred: str = ""
    deprecated: str = ""
    lifecycle: str = ""
    capabilities: str = ""
    artifacts: str = ""
    channel_prefix: str = ""
    revision_prefix: str = ""
    requires_prefix: str = ""
    artifact_fallback: str = ""
    verify: str = ""
    consumer_config: str = ""
    consumer_declaration: str = ""
    reference_version: str = ""
    copy_declaration: str = ""
    declaration_copied: str = ""
    version_availability: str = ""
    description: str = ""
    options: str = ""
    option: str = ""
    default: str = ""
    details: str = ""
    values: str = ""
    condition: str = ""
    default_options: str = ""
    components: str = ""
    platforms: str = ""
    authors: str = ""
    maintainers: str = ""
    topics: str = ""
    documentation: str = ""
    source: str = ""
    languages: str = ""
    package_type: str = ""
    package_links_suffix: str = ""
    open_on_prefix: str = ""
    recipe: str = ""
    homepage: str = ""
    upstream_source: str = ""
    also_packaged_as: str = ""
    no_description: str = ""
    show_available_prefix: str = ""
    unspecified: str = ""
    loading_metadata: str = ""
    record_failure_suffix: str = ""
    metadata_failure: str = ""


class CalendarUiText(Schema):
    eyebrow: str = ""
    options_label: str = ""
    subscribe_label: str = ""
    add_to_google_label: str = ""
    directory_label: str = ""
    note: str = ""
    previous_month_label: str = ""
    today_label: str = ""
    next_month_label: str = ""
    viewport_label: str = ""
    javascript_required: str = ""
    feed_fallback: str = ""
    open_label: str = ""
    close_label: str = ""
    non_public_note: str = ""
    participation_label: str = ""
    participation_url: str = ""
    date_label: str = ""
    event_singular: str = ""
    event_plural: str = ""
    in_label: str = ""
    no_events_prefix: str = ""
    next_prefix: str = ""
    on_label: str = ""


class TimelineUiText(Schema):
    features: str = ""
    html: str = ""


class PageUiText(Schema):
    search: SearchContent = field(default_factory=SearchContent)
    provenance_label: str = ""
    latest: LatestUiText = field(default_factory=LatestUiText)
    browse: BrowseUiText = field(default_factory=BrowseUiText)
    upcoming: UpcomingUiText = field(default_factory=UpcomingUiText)
    dialog: DialogUiText = field(default_factory=DialogUiText)
    catalog: CatalogUiText = field(default_factory=CatalogUiText)
    graph: GraphUiText = field(default_factory=GraphUiText)
    details: DetailsUiText = field(default_factory=DetailsUiText)
    calendar: CalendarUiText = field(default_factory=CalendarUiText)
    timeline: TimelineUiText = field(default_factory=TimelineUiText)


class CommonConfig(Schema):
    site: SiteConfig
    ui: UiText


class PagePresentation(Schema):
    common: CommonConfig
    structured_data_type: Literal["AboutPage", "CollectionPage", "WebPage"] = (
        "WebPage"
    )
    ui: PageUiText = field(default_factory=PageUiText)
    search: SearchPresentation = field(default_factory=SearchPresentation)
    sections: dict[str, SectionPresentation] = field(default_factory=dict)
    code_editor: CodeEditorPresentation = field(default_factory=CodeEditorPresentation)
    book_view_toggle: bool = False
    hide_non_cards_while_searching: bool = False


class SectionHeading(Schema):
    title: str
    description: str = ""
    labels: dict[str, str] = field(default_factory=dict)


class FeedSection(SectionHeading):
    pass


class PageContent(Schema):
    """Common editorial fields shared by every rendered HTML page."""

    title: str = ""
    seo_title: str = ""
    description: str = ""
    config: PagePresentation


class DocumentationEntry(Schema):
    id: str
    title: str
    description: str = ""
    content: str

    @computed_field
    @property
    def rendered_content(self) -> str:
        return markdown.markdown(
            self.content,
            extensions=[GitHubAdmonitionsExtension(), "admonition",
                        "fenced_code", "tables", "toc"],
        )


class DocumentationGroup(Schema):
    title: str
    pages: list[DocumentationEntry] = field(default_factory=list)


class HomeConfig(PagePresentation):
    events: list[CalendarEvent] = field(default_factory=list)
    imported_events: list[CalendarEvent] = field(default_factory=list)
    blog_sources: list[dict[str, Any]] = field(default_factory=list)
    recent_posts: list[dict[str, Any]] = field(default_factory=list)
    video_groups: list[dict[str, Any]] = field(default_factory=list)
    video_cache: dict[str, list[CachedVideo]] = field(default_factory=dict)

    @model_validator(mode="after")
    def sort_recent_activity(self) -> "HomeConfig":
        self.recent_posts.sort(
            key=lambda item: str(item.get("published") or ""), reverse=True
        )
        for videos in self.video_cache.values():
            videos.sort(key=lambda item: str(item.published or ""), reverse=True)
        return self


class YouTubeConfig(PagePresentation):
    channel_metadata: dict[str, ChannelMetadata] = field(default_factory=dict)
    video_cache: dict[str, list[CachedVideo]] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)

    @model_validator(mode="after")
    def sort_channel_videos(self) -> "YouTubeConfig":
        for videos in self.video_cache.values():
            videos.sort(key=lambda item: str(item.published or ""), reverse=True)
        return self


class CommunitiesConfig(PagePresentation):
    metadata: dict[str, CommunityMetadata] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)


class BooksConfig(PagePresentation):
    metadata: dict[str, BookMetadata] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)


class EventsConfig(PagePresentation):
    feed_url: str = ""
    events: list[CalendarEvent] = field(default_factory=list)
    imported_events: list[CalendarEvent] = field(default_factory=list)


class SitemapConfig(Schema):
    common: CommonConfig
    navigation: list[NavigationItem] = field(default_factory=list)
    footer: list[NavigationItem] = field(default_factory=list)
    additional_paths: list[str] = field(default_factory=list)


class HomeGuide(Schema):
    label: str
    title: str
    path: str


class HomePackage(Schema):
    title: str
    description: str = ""
    managers: list[str] = field(default_factory=list)


class HomeCodeTab(Schema):
    name: str
    code: str


class HomeLink(Schema):
    label: str
    path: str


class HomeHero(Schema):
    eyebrow: str = ""
    actions: list[HomeLink] = field(default_factory=list)
    tabs: list[HomeCodeTab] = field(default_factory=list)


class HomeSectionIntro(Schema):
    eyebrow: str = ""
    title: str = ""
    description: str = ""


class HomeEventPanel(Schema):
    type: Literal["event_list"] = "event_list"
    title: str = ""
    link: HomeLink


class HomeTextListPanel(Schema):
    type: Literal["text_list"] = "text_list"
    title: str = ""
    description: str = ""
    link: HomeLink
    items: list[str] = field(default_factory=list)


class HomeMetricPanel(Schema):
    type: Literal["metric_bars"] = "metric_bars"
    content: MetricBars


class HomeLinkGridPanel(Schema):
    type: Literal["link_grid"] = "link_grid"
    title: str = ""
    description: str = ""
    items: list[HomeGuide] = field(default_factory=list)


HomePanel = Annotated[
    HomeEventPanel | HomeTextListPanel | HomeMetricPanel | HomeLinkGridPanel,
    field(discriminator="type"),
]


class HomeSplitSection(Schema):
    type: Literal["split"] = "split"
    id: str
    intro: HomeSectionIntro
    panels: list[HomePanel] = field(default_factory=list)


class HomeFeed(Schema):
    source: Literal["blogs", "videos"]
    count_label: str
    title: str
    link: HomeLink
    limit: int = 5


class HomeFeedsSection(Schema):
    type: Literal["feeds"] = "feeds"
    id: str
    intro: HomeSectionIntro
    feeds: list[HomeFeed] = field(default_factory=list)


class HomePackageDemo(Schema):
    search: HomeLink
    previews: list[HomePackage] = field(default_factory=list)
    note: str = ""


class HomePackagesSection(Schema):
    type: Literal["package_showcase"] = "package_showcase"
    id: str
    intro: HomeSectionIntro
    action: HomeLink
    demo: HomePackageDemo


HomeSection = Annotated[
    HomeSplitSection | HomeFeedsSection | HomePackagesSection,
    field(discriminator="type"),
]


@schema("pages/page", template="pages/default.html")
class Page(PageContent):
    sections: list[ContentBlock] = field(default_factory=list)


@schema("pages/documentation", template="pages/documentation.html")
class Documentation(PageContent):
    groups: list[DocumentationGroup] = field(default_factory=list)


@schema("pages/youtube", template="pages/youtube.html")
class YouTube(Page):
    config: YouTubeConfig
    latest: FeedSection


@schema("pages/article", template="pages/home/index.html")
class Article(PageContent):
    config: HomeConfig
    path: str = ""
    hero: HomeHero = field(default_factory=HomeHero)
    sections: list[HomeSection] = field(default_factory=list)
    navigation: list[NavigationItem] = field(default_factory=list)
    footer: list[NavigationItem] = field(default_factory=list)


@schema("pages/communities", template="pages/communities.html")
class Communities(Page):
    config: CommunitiesConfig


@schema("pages/books", template="pages/books.html")
class Books(Page):
    config: BooksConfig


class EventCatalog(PageContent):
    config: EventsConfig


@schema("pages/events", template="pages/events/index.html")
class Events(EventCatalog):
    upcoming: FeedSection
    sections: list[ContentBlock] = field(default_factory=list)


@schema("pages/event-calendar-feed", template="pages/events/calendar.ics")
class EventCalendarFeed(Schema):
    config: EventsConfig
    calendar_name: str
    description: str
    product_id: str


@schema("pages/sitemap", template="pages/sitemap.xml")
class Sitemap(Schema):
    config: SitemapConfig
