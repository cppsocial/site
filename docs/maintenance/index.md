### Review a content submission

1. Confirm that the entry is C++-relevant, public, maintainable, and not duplicated.
2. Check that it is in the file named by the contributor guide and matches a nearby record.
3. Open the canonical URL, all secondary links, and the first-party verification source.
4. Verify names, identifiers, dates, timezone, location, and factual claims.
5. Check the hard constraints for the content type.
6. (Optionally) Run `make build` and inspect the affected rendered page or request a preview in the PR (`/preview` command).

Some CI checks may run (e.g. for Discord we verify that links are active, non-expiring and not a vanity link), inspect their output.

> [!IMPORTANT]
> **Two approvals are required**
>
> A pull request that changes any file under `content/` may be accepted only after approval from at least two current maintainers or curators listed on the [About page](/about/).


### Manually refresh metadata

Install the tools once with `make install`.

To update metadata for some specific new content, prefer running a narrow updater rather than `make update-all`.

| Curated change | Command |
| --- | --- |
| Blog source | `make blogs ID=<source-id>` |
| Book ISBN | `make books ID=<isbn>` |
| Community | `make communities ID=<community-id>` |
| Meetup calendar source | `make events` |
| YouTube channel | `make youtube ID=<channel-id>` |
| Package override only | `make package-publish` |
| Package registry sources | `make packages` |

These commands update `data/`.
All fetch remote sources except `make package-publish`, which uses saved catalogs.
`make events` refreshes every configured Meetup feed - it has no per-group `ID` option.

Content PRs may include related `data/` changes, such as the initial ingest or a targeted refresh for a new blog or YouTube channel.
Do not include metadata changes for unrelated entries.

For metadata patches, verify:

- Expected source IDs appear once and in the correct dataset
- Provenance names the URLs actually fetched
- Existing records were not removed because of a transient or empty response
- Sorting and serialization are stable
- No unrelated updater output is included

For updater code changes, run:

```sh
make check-format
make lint
make test
make build
```


### Add overrides

- Manually added events go to `content/events/events.yaml`, never `data/events-imported.yaml`
- To suppress a fetched post or video, keep its `post_id` or `video_id` and set `hidden: true` in `data/blogs/posts/<source-id>.yaml` or `data/youtube/videos/<channel-id>.yaml`. Other fields may be removed from that hidden record
- Put package corrections and merge decisions in `data/packages/overrides.yaml`, never in generated manager catalogs
- Apart from these overrides and hidden records, do not hand-edit fetched metadata, provenance, imported events, package entities, or match output

To remove registry records from package search, add a fully qualified manager ID to `ignored` or a stable, manager-qualified prefix to `ignored_prefixes` in `data/packages/overrides.yaml`. Make sure to do this for every affected package manager.

Run `make package-publish`, then `make build`, and confirm the primary package and its graph edges are absent.
