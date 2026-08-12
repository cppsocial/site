from datetime import datetime

from site_generator import Schema, field, schema

from schemas.pages import Page
from schemas.relevance import CppRelevance


class BlogSource(Schema):
    id: str
    title: str
    author: str = ""
    description: str = ""
    website_url: str
    rss_url: str
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
    source_id: str
    source_title: str
    title: str
    url: str
    published: datetime
    updated: datetime | None = None
    description: str = ""
    tags: list[str] = field(default_factory=list)
    cpp_relevance: CppRelevance | None = None
    hidden: bool = False


@schema("blogs/index", template="blogs.html")
class Blogs(Page):
    sources: list[BlogSource] = field(default_factory=list)
    blog_metadata: dict[str, BlogMetadata] = field(default_factory=dict)
    post_cache: list[CachedBlogPost] = field(default_factory=list)
    latest_rows: int = 2
