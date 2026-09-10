from datetime import datetime

from pydantic import model_validator
from site_generator import Schema, field, schema

from schemas.pages import FeedSection, Page, PagePresentation, SectionHeading
from schemas.relevance import CppRelevance


class BlogSource(Schema):
    id: str
    title: str
    author: str = ""
    description: str = ""
    website_url: str
    rss_url: str
    sitemap_url: str = ""
    exclude_tags: list[str] = field(default_factory=list)
    discoverable: bool = True
    hidden: bool = False


@schema("blogs/metadata")
class BlogMetadata(Schema):
    description: str = ""
    keywords: list[str] = field(default_factory=list)
    avatar_url: str = ""
    source_url: str = ""


@schema("blogs/cached-post")
class CachedBlogPost(Schema):
    post_id: str
    source_id: str = ""
    source_title: str = ""
    title: str = ""
    url: str = ""
    published: datetime | None = None
    updated: datetime | None = None
    description: str = ""
    tags: list[str] = field(default_factory=list)
    cpp_relevance: CppRelevance | None = None
    hidden: bool = False

    @model_validator(mode="after")
    def complete_unless_hidden(self) -> "CachedBlogPost":
        required = (self.source_id, self.source_title,
                    self.title, self.url, self.published)
        if not self.hidden and not all(required):
            raise ValueError(
                "visible cached posts require source, title, URL, and date")
        return self


class BlogsConfig(PagePresentation):
    blog_metadata: dict[str, BlogMetadata] = field(default_factory=dict)
    post_cache: list[CachedBlogPost] = field(default_factory=list)
    provenance: dict = field(default_factory=dict)

    @model_validator(mode="after")
    def sort_recent_posts(self) -> "BlogsConfig":
        self.post_cache.sort(
            key=lambda item: str(item.published or ""), reverse=True
        )
        return self


class BlogDirectory(SectionHeading):
    sources: list[BlogSource] = field(default_factory=list)


@schema("blogs/index", template="pages/blogs.html")
class Blogs(Page):
    config: BlogsConfig
    latest: FeedSection
    browse: BlogDirectory
