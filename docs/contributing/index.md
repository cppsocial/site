### Ways to contribute

[cpp.social](https://cpp.social) is a community-maintained project - your help is required to keep this site up to date and ensure we're listing the resources people actually care about.

If you notice missing resources, wrong descriptions and other mistakes or have general feedback on how to improve the usability to this site, please do reach out.
While we prefer it where possible, you do not have to submit a pull request for your suggested changes - it is also possible to let us know through an [issue](https://github.com/cppsocial/site/issues/new/choose).

For content submissions, please check for duplicates first and make sure the suggested content fulfills our content requirements.

> [!NOTE]
> **Content PRs require two approvals**
>
> Every content change needs at least two approvals by current curators or maintainers before we can accept it.
> You can find a list of current maintainers and curators on the [About page](/about/).

### What we list

Content must be relevant to C++ developers and have a stable public page.

- Tutorials, guides, and other learning resources must be free to access in full, without a purchase or subscription. Books are of course exempt from this.
- Books, blogs, and YouTube channels must contain substantive human-created work. Purely AI-generated publications are not eligible.
- Tooling must have real users beyond personal experiments or toy projects. Include available evidence of use, such as public projects that depend on them.


> [!WARNING]
> **Use direct links**
>
> Use canonical HTTPS URLs without tracking parameters.
> URL shorteners, referral or affiliate links, and vanity links are not accepted.

### Submit a pull request

To locally build the site, you will need Python 3.13 or newer and Node.js 24 (the version used in CI).
The rest of the tooling can be installed by invoking `make install`.

1. Read the relevant guide below and edit the relevant file(s). Follow a nearby entry's structure and use only supported fields.
2. Optional: If the entry needs fetched metadata, you may run the guide's updater command for that entry (do inspect the output to ensure there's no unrelated changes!).
3. Run `make build` and check the affected page under `build/`.
4. Open a pull request against `cppsocial/site`. Describe the change and explain why it was made.

For code changes, also run `make check-format`, `make lint`, and `make test`.
If formatting fails, use the matching `make format-*` command shown in the failure message.

### Generated files

Add content through the source files named in these guides, not by editing generated files under `data/`.
> [!IMPORTANT]
> **Related metadata changes are welcome**
>
> Content PRs may include related `data/` changes, such as the initial ingest or a targeted refresh for a new blog or YouTube channel.
> Leave out metadata changes for unrelated entries.
>
> However, this is purely optional.

Hand-maintained exceptions are covered in the [Packages](#packages) and [Content maintenance](#maintaining) guides.
