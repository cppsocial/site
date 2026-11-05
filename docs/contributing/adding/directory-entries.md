### Pick the destination

| Entry | File |
| --- | --- |
| General reference or online tool | `content/resources/general.yaml` |
| Guide, FAQ, or learning material | `content/resources/guides.yaml` |
| Compiler or toolchain | `content/ecosystem/compilers.yaml` |
| Build system or project generator | `content/ecosystem/builds.yaml` |
| Library or standard-library implementation | `content/ecosystem/libraries.yaml` |
| Package manager as a tool | `content/ecosystem/packages.yaml` |
| ABI resource | `content/ecosystem/abi.yaml` |
| General standardization resources | `content/evolution/resources.yaml` |
| Related technical standard | `content/evolution/related-standards.yaml` |
| Active recurring conference series | `content/events/conferences.yaml` |
| Conference series no longer running | `content/events/past-conferences.yaml` |

> [!NOTE]
> **Events and registry packages have separate guides**
>
> For dated events, follow the [Events guide](#events).
> For packages listed in a registry, follow the [Packages guide](#packages).

### Add a card

Add a record under the existing `cards` list:

```yaml
- title: Example Tool
  path: https://example.org/
  description: Short factual explanation of its use in C++
  metadata:
    License: MIT
  links:
    - {label: Documentation, path: https://example.org/docs/}
    - {label: Source, path: https://github.com/example/tool}
```

### Requirements

- Provide a concise `title` and the canonical HTTPS `path`
- Explain the entry's relevance to C++ in a short, factual `description`
- Check that the entry is public and not already listed; for active projects, look for recent releases or development
- For a project or tool, show that it has real users and is relevant to C++ developers
- Add `metadata` and secondary `links` only when they help someone evaluate or use the entry
- Use labels already established in that section
- Follow the shared URL, description, and YAML rules in the Style guide

### Icons and hidden entries

Omit `icon` to discover the site's favicon automatically.
Set `icon: null` when no icon should be displayed.
Use an explicit HTTPS image URL only when favicon discovery gives the wrong result.

> [!WARNING]
> **No hidden placeholders**
>
> Use `hidden: true` only to hide an existing entry.
> New entries must be complete and visible.

### Check the result

Run `make build`, open the affected page under `build/`, and check the card at narrow and wide widths.
Confirm that every link works and that the description does not duplicate the title.
