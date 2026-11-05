### Descriptions

- Write one factual sentence and do not end it with a period
- Use the project's own description if it is clear and factual, otherwise summarize what it does
- Avoid first person, superlatives, calls to action, download counts, and other marketing claims
- Preserve the project's own spelling and capitalization

### URLs and sources

- Use canonical HTTPS URLs without tracking parameters or fragments unless the fragment is essential
- Prefer first-party project, organizer, publisher, or repository pages
- Use a primary resource for event dates and corrections, not a search result or social repost
- Keep link labels short and consistent with nearby entries
- Discord invites must be permanent and cannot be vanity links

### YAML

- Copy the indentation and field order of a nearby record
- Quote strings that YAML could misread, such as `"yes"`, `"0123"`, or text containing `: ` or ` #`
- Use ISO `YYYY-MM-DD` dates and IANA timezone names
- Keep locally assigned IDs lowercase, unique, and stable
- Preserve external identifiers exactly, including case in YouTube channel IDs, Discord invite codes, and package IDs
- Do not reformat unrelated entries in a content pull request

The `$schema` line describes the whole document and should not be changed when adding a record.
Unknown fields fail schema validation.

### Markdown

Use [semantic line breaks](https://sembr.org/) for prose in `docs/` and other long-form Markdown.
Use sentence-case headings, fenced code blocks with a language, and relative links for repository documentation.
