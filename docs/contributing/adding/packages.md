### Missing packages

The package search is built from supported package-manager registries.
There is no hand-written package list in this repository.

If a package is missing from its registry, add it upstream first.
If it exists upstream but is absent from cpp.social, open a content-correction issue with:

- The package manager and exact package ID
- The upstream registry or recipe URL
- The expected project homepage or repository
- The date on which you confirmed it was present upstream

> [!WARNING]
> **Registry catalogs are generated**
>
> Do not add records directly to `data/packages/conan.yaml`, `meson.yaml`, `spack.yaml`, or another manager catalog.

### Correct a metadata field

First fix the upstream registry when possible.
For a local metadata fix, add a `corrections` entry to `data/packages/overrides.yaml`.
These entries use `PackageFieldCorrection` in the schema:

```yaml
corrections:
  - package: vcpkg:example
    field: homepage
    operation: replace
    value: https://example.org/
    reason: Registry metadata still points to the retired project site
```

`package` is the exact ID from a registry catalog, such as `vcpkg:fmt`.
`field` names a field on that package; add `version` to target one exact version instead.
`replace` is the default operation; `remove` deletes a field, and `add` appends unique values to a list field.
Explain the correction in `reason` and link to its source in the PR description.

See the [override schema](https://github.com/cppsocial/site/blob/master/schemas/packages.py) and [correction code](https://github.com/cppsocial/site/blob/master/updater/src/meta_updater/commands/packages.py) for the supported fields and behavior.

### Group packages from the same project

Records for the same upstream project can be grouped under `groups` in `data/packages/overrides.yaml`.
These entries use `PackageGroupOverride`, which has different fields from a metadata correction:

```yaml
groups:
  - id: example
    name: Example
    packages:
      - conan:example
      - vcpkg:example
    reason: These recipes use the same upstream repository
```

Replace the example IDs with exact IDs from the registry catalogs.
`id`, `name`, `aliases`, and `reason` are optional; `packages` is required.

Every ID in `packages` must already exist in the saved registry catalogs; a missing ID fails package publishing.
Do not add placeholders for packages that are not yet available.

To keep two packages separate, add a `never_merge` record with those two IDs under `packages` and a `reason`.

`preferences` selects the source for a merged entry's `summary` or `licenses`.
Its `package` is the entity ID from `data/packages/entities.yaml`; its `source` is a registry package ID belonging to that entity.
The schema also accepts URL fields here, but the current browser build does not apply those preferences.

Package matching changes require updater tests.

> [!WARNING]
> **Matching output is generated**
>
> Edit `data/packages/overrides.yaml`, not the generated `entities.yaml` or `matches.yaml`.

### Check package changes

Run `make package-publish` to apply overrides to the saved catalogs and regenerate package identities and matches, then `make build` to update the browser data.
Run `make packages` only when the registries need fetching again.
For matching changes, also run `make test`.
Check the affected package details and leave unrelated generated changes out of the PR.
