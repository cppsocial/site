# Meta updater

`meta-updater` refreshes the durable metadata used by cpp.social. Browser search
chunks are produced later by the site generator.

## Usage

```text
meta-updater [--config PATH] <updater> [options] [action]
```

The updaters are `blogs`, `books`, `communities`, `events`, `packages`, and
`youtube`. Network-backed updaters accept `--timeout` and `--check`; the
feed-based updaters also accept `--delay`. These options may be placed before
or after an updater action.

```sh
meta-updater blogs all
meta-updater youtube videos --check
meta-updater youtube all --id UCxxxxxxxxxxxxxxxxxxxxxx
meta-updater packages ingest --manager conan --refresh
```

`blogs`, `books`, `communities`, and `youtube` accept repeatable `--id` options.
An ID must already be present in the corresponding curated content file.
Targeted runs preserve every unselected cache entry:

```sh
meta-updater blogs all --id example_blog
meta-updater blogs ingest --id example_blog
meta-updater books --id 9780123456789
meta-updater communities --id example-community
meta-updater youtube all --id UCxxxxxxxxxxxxxxxxxxxxxx
```

`blogs ingest` is a manual, slow backfill for a newly added blog. It requires
exactly one `--id`, uses sitemaps as a URL inventory, and correlates candidates
with links from archive, timeline, and pagination pages. The feed supplies
current posts, publishing-system detection, and a stable post URL shape; it is
not treated as a historical inventory. An explicit `sitemap_url` still takes
precedence over discovered CMS locations. Ingest also removes off-site URLs,
generated paths, static assets, and URLs already present in the feed or cache.
Normal `blogs posts` and `blogs all` runs never invoke it.

The package updater additionally supports `matches`, `ingest`, `publish`, and
`inspect`. Run `meta-updater <updater> --help` for the complete option list.

Blog posts and YouTube videos are stored in one YAML file per source under
`data/blogs/posts/` and `data/youtube/videos/`. Refreshes only append or update
identified entries. To suppress one permanently, set `hidden: true`; all fields
except `post_id` or `video_id` may then be removed. Manual edits to existing
records are preserved, including an inline `cpp_relevance` score from 0 to 1.

Package manager catalogs are replaced only after a successful non-empty refresh.
Human package corrections, merge preferences, and the `ignored` package-ID list
live in `data/packages/overrides.yaml`. Ignored IDs are filtered before catalogs
and consolidated entities are written.

Generated package catalogs intentionally store a browser-oriented normalized
view rather than an archival copy of upstream metadata. Descriptions are bounded
excerpts; README headings, comments, badges, and image-only blocks are discarded.
Markdown is rendered without headings, HTML uses a small safe-tag allow-list,
descriptions equal to summaries are omitted, and release metadata equal to the
package-level value is inherited. Missing artifact `kind` means `upstream_source`.
vcpkg release recipes store `recipe_revision`; the site reconstructs the exact
repository URL when it renders a release.
