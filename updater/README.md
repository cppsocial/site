# Meta updater

`meta-updater` refreshes the generated metadata and browser caches used by cpp.social.

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
meta-updater packages ingest --manager conan --refresh
```

The package updater additionally supports `matches`, `ingest`, `publish`, and
`inspect`. Run `meta-updater <updater> --help` for the complete option list.
