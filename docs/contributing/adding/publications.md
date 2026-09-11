### Blogs

Add the source to `content/blogs/sources.yaml`:

```yaml
- id: example_blog
  title: Example C++ Blog
  author: Ada Example
  website_url: https://example.org/
  rss_url: https://example.org/feed.xml
```

The blog must publish substantial C++ content and provide a public RSS or Atom feed.

- Choose a unique lowercase `id` based on the publication name and follow the naming convention in the file.
- Copy the title and canonical website URL from the blog. Include `author` if it names an individual author.
- Find the feed through the site's RSS or Subscribe link, or the page source's [RSS/Atom alternate link](https://html.spec.whatwg.org/dev/links.html#rel-alternate). Open it and check that it contains post URLs and publication dates.
- Add a description only if the title does not explain the source.

`sitemap_url` may be required to properly backfill the blog's content archive.
You do not need to do this for a content PR, but you can if you want.

Backfilling is done by executing `meta-updater blogs ingest --id example_blog`.
The normal `make blogs` command only fetches the RSS feed to discover new posts.

### YouTube channels

Add a channel to the `cards` list in the file matching its owner:

| Channel                         | File                                 | `channel_type` |
| ------------------------------- | ------------------------------------ | -------------- |
| Independent creator or educator | `content/youtube/channels.yaml`      | `creator`      |
| Conference archive              | `content/youtube/conferences.yaml`   | `conference`   |
| Organization                    | `content/youtube/organizations.yaml` | `organization` |
| Podcast or recurring show       | `content/youtube/organizations.yaml` | `show`         |

```yaml
- title: Example C++ Channel
  channel_type: creator
  channel_id: UCxxxxxxxxxxxxxxxxxxxxxx
```

The channel must publish substantial C++ material.
Copy its title from the channel header and choose the file and `channel_type` from the table above.

> [!IMPORTANT]
> **Use the channel ID**
>
> Use the stable ID beginning with `UC`, not a handle, playlist, or video ID.

On desktop, open the channel, expand its description with **more**, then choose **Share channel → Copy channel ID** ([YouTube Help Community instructions](https://support.google.com/youtube/thread/341141249?hl=en&msgid=341283926)).
For your own channel, you can also use [Advanced settings](https://support.google.com/youtube/answer/3250431?hl=en).
Open `https://www.youtube.com/channel/<channel_id>` to check that it is the intended channel.

Do not manually add video IDs, thumbnails, descriptions, or feed URLs - those are fetched automatically by the metadata updater.

### Books

Add an ISBN record to the `cards` list in `content/books/books.yaml` (this example is already listed):

```yaml
- { isbn: "9780321563842" }
```

Use the quoted 13-digit ISBN from the publisher page or copyright page for the exact edition and format you want to list.
Hardbacks, paperbacks, ebooks, and later editions can have different ISBNs.

> [!NOTE]
> **Book metadata is fetched automatically**
>
> Submit only the ISBN and, if needed, a cover override. Open Library supplies the title, author, publisher, and description.

Only add `cover_url` when Open Library has no usable cover or returns the wrong edition:

```yaml
- isbn: "9780321563842"
  cover_url: https://example.org/covers/9780321563842.jpg
```

The override must be a stable HTTPS image URL that the project is allowed to display.

### Generated metadata

Run the command for the entry you added, then build:

```sh
make blogs ID=example_blog
make youtube ID=UCxxxxxxxxxxxxxxxxxxxxxx
make books ID=9780321563842
make build
```

The ID must already exist in the relevant curated file.
To refresh multiple entries, repeat `--id`, for example `meta-updater blogs all --id first_blog --id second_blog`.

Check the affected page for the correct publication and metadata.
Do not create or edit cache files by hand.
See [Generated files](#start) for when to include updater output in the PR.
