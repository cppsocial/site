# cpp.social

This repository generates the content on cpp.social.

## Repository structure

- `content/` contains editorial page copy, links, and source details for manually
  curated listings. Each `_index.yaml` follows the rendered page from top to
  bottom; larger parts are imported from adjacent files. Updaters read source
  details from the same curated record instead of maintaining parallel lists.
- `ui/text.yaml` contains shared English interface labels. `ui/pages/` contains
  page-specific controls, dialogs, column labels, and status messages. The site
  navigation and footer UI live alongside them. This is deliberately not a
  localization system: cpp.social is English-only, and no translated variants
  should be added for now.
- `config/` contains presentation choices, behavior flags, site identity, and the
  wiring between pages and generated or fetched data. These
  values are kept in YAML so templates remain reusable without mixing configuration
  into editorial content.
- `data/` contains durable generated and remotely fetched records. The per-source
  blog/video recent caches may be edited to add `hidden: true` stubs, and
  `data/packages/overrides.yaml` is maintained by hand. Browser search chunks are
  build artifacts generated under `build/data`, never source data.
- `templates/` provides reusable rendering, `frontend/` owns browser behavior, and
  `assets/static/` contains styles and static media. Text for UI elements goes to `ui/`.

Page-specific templates are appropriate when a page has a genuinely different
structure. Repeated sections and cards should be implemented as components and
configured through the page YAML instead of being copied between templates.

## Frontend organization

- `templates/layouts/` contains the document frame and the shared base for
  searchable listing pages. Page entry templates live under `templates/pages/`;
  pages with several private fragments, such as the home and events pages, get
  their own subfolder.
- `templates/blocks/` contains only top-level, schema-dispatched content sections.
  Reusable visual fragments live under `templates/components/`, including its
  `cards/`, `dialogs/`, `directory/`, and `site/` families.
  A block participates in a page's `sections` list; a card is a nested record
  rendered by a card-group block or a page-specific feed. Directory controller
  labels are serialized by `components/directory/client_config.html`.
- `assets/static/style.css` is the ordered CSS entrypoint. Its files under
  `assets/static/styles/` are grouped by component or page family. Import order is
  part of the cascade and should only change alongside visual regression checks.
- `frontend/src/pages/` contains behavior owned by one page family. The directory
  page entry composes the searchable catalog with its optional book and channel
  enhancements; those implementations live under `frontend/src/directory/` with
  the worker-backed MiniSearch index, package details, and package references.
- `frontend/src/shared/` is limited to browser primitives reused across page
  families. The global site shell is `frontend/src/site.ts`, and service workers
  live under `frontend/src/workers/`. Ambient contracts for external browser
  runtimes live under `frontend/src/types/`.
- `assets/` contains only source assets that need copying, such as styles and
  images. `site-generator build` invokes the configured frontend compiler, which
  writes JavaScript directly to `build/`; generated JavaScript is not committed.

The frontend uses TypeScript with strict checking for shared code, domain modules,
and page integrations. The two large migrated visualization/search modules remain
in an explicit migration config while their state models are split out; they are
still checked on every run. `npm run check:frontend` type-checks browser and worker
contexts separately and runs the focused unit tests.

esbuild is used as a compiler and bundler rather than as the development server.
The site generator already owns routing, template rendering, watching, and local
serving, and passes either `development` or `production` to the frontend build.
Development bundles have inline source maps and retain readable code; production
bundles are minified.
