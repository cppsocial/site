### Put the change in the right subtree

| Change | Location |
| --- | --- |
| Site content | `content/` |
| Text for UI elements | `ui/` |
| Site and page settings | `config/` |
| Page-specific templates | `templates/pages/` |
| Reusable UI components | `templates/components/` |
| Top-level sections | `templates/blocks/` |
| Client-side JS code | `frontend/` |
| Stylesheets and static files | `assets/` |
| Browser data generation | `site_plugins/` |
| Metadata updater | `updater/` |
| Contributor and maintainer documentation | `docs/` |

### UI changes

The primary CSS entrypoint is `assets/static/style.css`.
All other stylesheets should be put in `assets/static/styles`, especially when that stylesheet is specific to some page or feature.

Keep the import order unless the change needs a different CSS cascade.

Check keyboard navigation, focus visibility, narrow layouts, dark mode, empty states, and long titles.
Include screenshots or a short recording in the pull request for visible changes.

### Updater changes

Network failures, empty responses, and malformed source data must not replace a valid dataset.
Keep output deterministic and preserve provenance URLs and retrieval timestamps.

Do not mix a broad metadata refresh into an updater code change.
Use small fixtures rather than live network calls in tests.

### Documentation changes

The contributing page renders the files under `docs/` in the order declared by `content/contributing/_index.yaml`.
Create new documentation files under `docs/` and register each one in the index with a title, stable anchor ID, description, and `!include` entry.

Run `make build` and inspect `/contributing/` at desktop and mobile widths.
