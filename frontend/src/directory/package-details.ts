import { StaticRecordCollection } from "./catalog";
import { createText } from "../shared/dom";
import {
  consumerFile,
  consumerReference,
  packageVersions,
  upstreamVersion,
} from "./packages/references";
import type { PackageRelease, PackageVariant } from "./packages/references";
import type { PackageReleaseMetadata } from "./packages/references";

type Copy = Record<string, string>;

interface Dependency {
  condition?: string;
  constraint?: string;
  id?: string;
  kind?: string;
  name?: string;
}

interface PackageFeature {
  condition?: string;
  default?: string;
  description?: string;
  name: string;
  values?: string[];
}

interface PackageDetailVariant extends PackageVariant {
  authors?: string[];
  components?: string[];
  default_options?: Record<string, string>;
  default_version?: string;
  deprecated?: boolean;
  deprecation_reason?: string;
  dependency_links?: Dependency[];
  description?: string;
  documentation_url?: string;
  external_names?: string[];
  features?: PackageFeature[];
  homepage?: string;
  languages?: string[];
  licenses?: string[];
  maintainers?: string[];
  native_url?: string;
  options?: string[];
  package_type?: string;
  platforms?: string[];
  recipe_url?: string;
  repository_url?: string;
  source_urls?: string[];
  summary?: string;
  topics?: string[];
  versions?: Parameters<typeof packageVersions>[0];
  release_metadata?: PackageReleaseMetadata[];
}

interface PackageRecord {
  aliases?: string[];
  content?: string;
  id: string;
  licenses?: string[];
  packages?: string[];
  title?: string;
}

interface PackageState {
  details?: Map<string, StaticRecordCollection>;
  detailsUrl: string;
}

interface PackageCatalogOptions {
  copy: Copy;
  packageCopy: Copy;
  managerLabels: ReadonlyMap<string, string>;
  selectDependency: (id: string, name: string, href: string) => Promise<void>;
  selectManager: (manager: string) => Promise<void>;
  selectTopic: (topic: string) => Promise<void>;
}

export function createPackageCatalog({
  copy,
  packageCopy,
  managerLabels,
  selectDependency,
  selectManager,
  selectTopic,
}: PackageCatalogOptions) {
  function packageField(
    parent: HTMLElement,
    label: string,
    values: string | string[] | undefined,
  ): void {
    const items = Array.isArray(values) ? values : [values];
    const visible = items.filter(Boolean);
    if (!visible.length) return;
    const row = document.createElement("div");
    row.className = "package-variant__field";
    createText(row, "dt", label);
    createText(row, "dd", visible.join(", "));
    parent.append(row);
  }

  function packageDependencies(
    parent: HTMLElement,
    dependencies: Dependency[] | undefined,
  ): void {
    if (!dependencies?.length) return;
    const row = document.createElement("div");
    row.className = "package-variant__field";
    createText(row, "dt", packageCopy.dependencies);
    const values = document.createElement("dd");
    dependencies.forEach((dependency, index) => {
      if (index) values.append(document.createTextNode(", "));
      const name = dependency.name || dependency.id || "";
      const suffix = [
        dependency.constraint,
        dependency.kind,
        dependency.condition,
      ]
        .filter(Boolean)
        .join(" · ");
      const label = suffix ? `${name} (${suffix})` : name;
      if (!dependency.id) {
        values.append(document.createTextNode(label));
        return;
      }
      const id = dependency.id;
      const link = createText(values, "a", label);
      link.href = `#${encodeURIComponent(id)}`;
      link.addEventListener("click", async (event) => {
        event.preventDefault();
        await selectDependency(id, name, link.href);
      });
    });
    row.append(values);
    parent.append(row);
  }

  function packageLicenses(
    parent: HTMLElement,
    licenses: string[] | undefined,
  ): void {
    const visible = (licenses || []).filter(Boolean);
    if (!visible.length) return;
    const row = document.createElement("div");
    row.className = "package-variant__field";
    createText(row, "dt", packageCopy.license);
    const values = document.createElement("dd");
    visible.forEach((license, index) => {
      if (index) values.append(document.createTextNode(", "));
      const expression =
        /^[A-Za-z0-9][A-Za-z0-9.+-]*$/.test(license) ||
        /\s(?:AND|OR|WITH)\s|[()]/.test(license);
      if (!expression) {
        values.append(document.createTextNode(license));
        return;
      }
      for (const token of license.split(/(\s+|[()])/)) {
        if (
          !token ||
          /^\s+$|^[()]$/.test(token) ||
          ["AND", "OR", "WITH"].includes(token)
        ) {
          values.append(document.createTextNode(token));
          continue;
        }
        const link = createText(values, "a", token);
        link.href = `https://spdx.org/licenses/${encodeURIComponent(token)}.html`;
        link.target = "_blank";
        link.rel = "noopener";
      }
    });
    row.append(values);
    parent.append(row);
  }

  function packageChips(
    parent: HTMLElement,
    label: string,
    values: string[] | undefined,
  ): void {
    const visible = [...new Set((values || []).filter(Boolean))];
    if (!visible.length) return;
    const group = document.createElement("section");
    group.className = "package-chip-group";
    createText(group, "h4", label);
    const chips = document.createElement("div");
    chips.className = "package-chips";
    visible.forEach((value) => {
      const chip = createText(chips, "button", value);
      chip.type = "button";
      chip.className = "package-chip";
      chip.addEventListener("click", async () => selectTopic(value));
    });
    group.append(chips);
    parent.append(group);
  }

  function packageOptions(
    parent: HTMLElement,
    options: string[] | undefined,
    defaults: Record<string, string> | undefined,
    features: PackageFeature[] | undefined,
  ): void {
    const byName = new Map<string, PackageFeature>();
    for (const name of options || []) byName.set(name, { name });
    for (const feature of features || []) {
      byName.set(feature.name, { ...byName.get(feature.name), ...feature });
    }
    for (const [name, value] of Object.entries(defaults || {})) {
      byName.set(name, { ...byName.get(name), name, default: value });
    }
    if (!byName.size) return;

    const section = document.createElement("section");
    section.className = "package-options";
    createText(section, "h4", packageCopy.options);
    const table = document.createElement("table");
    const head = document.createElement("tr");
    [packageCopy.option, packageCopy.default, packageCopy.details].forEach(
      (label) => createText(head, "th", label),
    );
    const thead = document.createElement("thead");
    thead.append(head);
    table.append(thead);
    const body = document.createElement("tbody");
    [...byName.values()]
      .sort((left, right) => left.name.localeCompare(right.name))
      .forEach((feature) => {
        const row = document.createElement("tr");
        createText(row, "th", feature.name);
        createText(row, "td", feature.default || "—");
        const details = [
          feature.description,
          feature.values?.length
            ? `${packageCopy.values}: ${feature.values.join(", ")}`
            : "",
          feature.condition
            ? `${packageCopy.condition}: ${feature.condition}`
            : "",
        ].filter(Boolean);
        createText(row, "td", details.join(" · ") || "—");
        body.append(row);
      });
    table.append(body);
    section.append(table);
    parent.append(section);
  }

  function packageStatus(
    parent: HTMLElement,
    variant: PackageDetailVariant,
  ): void {
    const values = [
      variant.deprecated ? packageCopy.deprecated : "",
      variant.package_type,
      ...(variant.languages || []),
    ].filter(Boolean) as string[];
    if (!values.length && !variant.deprecation_reason) return;
    const status = document.createElement("div");
    status.className = "package-status";
    values.forEach((value) => {
      const badge = createText(status, "span", value);
      badge.className = `package-status__badge${
        value === packageCopy.deprecated
          ? " package-status__badge--warning"
          : ""
      }`;
    });
    if (variant.deprecation_reason) {
      createText(status, "span", variant.deprecation_reason).className =
        "package-status__reason";
    }
    parent.append(status);
  }

  function packageReleaseTable(
    variant: PackageDetailVariant,
    versions: PackageRelease[],
  ): HTMLDetailsElement | null {
    if (!versions.length) return null;
    const disclosure = document.createElement("details");
    disclosure.className = "package-release-disclosure";
    disclosure.open = true;
    createText(
      disclosure,
      "summary",
      `${packageCopy.releases} (${versions.length})`,
    );
    const scroller = document.createElement("div");
    scroller.className = "package-release-scroll";
    const table = document.createElement("table");
    table.className = "package-release-table";
    const head = document.createElement("tr");
    for (const label of [
      packageCopy.version,
      packageCopy.release_metadata,
      packageCopy.artifacts,
    ]) {
      createText(head, "th", label);
    }
    const thead = document.createElement("thead");
    thead.append(head);
    table.append(thead);
    const body = document.createElement("tbody");
    for (const release of versions) {
      const row = document.createElement("tr");
      createText(row, "th", release.version);
      const metadata = [
        release.preferred && packageCopy.preferred,
        release.lifecycle && `${packageCopy.lifecycle}: ${release.lifecycle}`,
        release.channel && `${packageCopy.channel_prefix} ${release.channel}`,
        release.packaging_revision &&
          `${packageCopy.revision_prefix} ${release.packaging_revision}`,
        ...(release.compatibility || []).map(
          (item) => `${packageCopy.requires_prefix} ${item}`,
        ),
      ].filter(Boolean);
      const metadataCell = createText(row, "td", metadata.join(" · ") || "—");
      const detailed = Boolean(
        release.summary ||
        release.description ||
        release.lifecycle_reason ||
        release.capabilities?.length ||
        release.dependencies?.length ||
        release.features?.length ||
        release.licenses?.length ||
        release.documentation_url ||
        release.homepage ||
        release.repository_url ||
        release.recipe_revision ||
        release.recipe_url,
      );
      if (detailed) {
        const disclosure = document.createElement("details");
        disclosure.className = "package-release-details";
        createText(disclosure, "summary", packageCopy.release_details);
        if (release.summary || release.lifecycle_reason) {
          createText(
            disclosure,
            "p",
            release.lifecycle_reason || release.summary || "",
          );
        }
        if (release.description) {
          const description = document.createElement("div");
          description.innerHTML = release.description;
          disclosure.append(description);
        }
        const fields = document.createElement("dl");
        packageField(fields, packageCopy.capabilities, release.capabilities);
        packageField(
          fields,
          packageCopy.dependencies,
          release.dependencies?.map((dependency) =>
            [
              dependency.name,
              dependency.constraint,
              dependency.kind,
              dependency.condition,
            ]
              .filter(Boolean)
              .join(" · "),
          ),
        );
        packageField(fields, packageCopy.license, release.licenses);
        disclosure.append(fields);
        packageOptions(
          disclosure,
          release.features?.map((feature) => feature.name),
          undefined,
          release.features,
        );
        const links = document.createElement("nav");
        links.className = "package-release-details__links";
        const recipeUrl =
          release.recipe_url ||
          (variant.registry === "vcpkg" && release.recipe_revision
            ? `https://github.com/microsoft/vcpkg/tree/${encodeURIComponent(
                release.recipe_revision,
              )}/ports/${encodeURIComponent(variant.name)}`
            : undefined);
        externalPackageLink(links, packageCopy.recipe, recipeUrl);
        externalPackageLink(
          links,
          packageCopy.documentation,
          release.documentation_url,
        );
        externalPackageLink(links, packageCopy.homepage, release.homepage);
        externalPackageLink(links, packageCopy.source, release.repository_url);
        if (links.childElementCount) disclosure.append(links);
        metadataCell.append(disclosure);
      }
      const artifacts = document.createElement("td");
      const available = release.artifacts || [];
      if (!available.length) {
        artifacts.textContent = "—";
      } else {
        for (const artifact of available) {
          const item = document.createElement("div");
          item.className = "package-release-artifact";
          const label = String(
            artifact.filename || artifact.kind || packageCopy.artifact_fallback,
          ).replaceAll("_", " ");
          if (artifact.url) externalPackageLink(item, label, artifact.url);
          else createText(item, "span", label);
          if (artifact.checksums?.length) {
            const hashes = document.createElement("details");
            createText(hashes, "summary", packageCopy.verify);
            createText(hashes, "code", artifact.checksums.join("\n"));
            item.append(hashes);
          }
          artifacts.append(item);
        }
      }
      row.append(artifacts);
      body.append(row);
    }
    table.append(body);
    scroller.append(table);
    disclosure.append(scroller);
    return disclosure;
  }

  function packageSiteUrl(variant: PackageDetailVariant): string {
    const name = encodeURIComponent(variant.name);
    if (variant.registry === "conan") {
      return `https://conan.io/center/recipes/${name}`;
    }
    if (variant.registry === "vcpkg") {
      return `https://vcpkg.io/en/package/${name}`;
    }
    if (variant.registry === "spack") {
      return `https://packages.spack.io/package.html?name=${name}`;
    }
    if (variant.registry === "meson") {
      return "https://mesonbuild.com/Wrapdb-projects.html";
    }
    if (variant.registry === "cppget") {
      return `https://cppget.org/${name}`;
    }
    if (variant.registry === "hunter") {
      return `https://hunter.readthedocs.io/en/latest/packages/pkg/${name}.html`;
    }
    if (variant.registry === "bazel") {
      return `https://registry.bazel.build/modules/${name}`;
    }
    if (variant.registry === "xmake") {
      return `https://packages.xmake.io/packages/${name}`;
    }
    return "";
  }

  function managerLabel(value: string): string {
    return managerLabels.get(value) || value;
  }

  function externalPackageLink(
    parent: HTMLElement,
    label: string,
    href: string | undefined,
    primary = false,
  ): void {
    if (!href) return;
    const link = createText(parent, "a", label);
    link.className = `package-link${primary ? " package-link--primary" : ""}`;
    link.href = href;
    link.target = "_blank";
    link.rel = "noopener";
  }

  async function copyText(value: string): Promise<void> {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value);
      return;
    }
    const temporary = document.createElement("textarea");
    temporary.value = value;
    temporary.style.position = "fixed";
    temporary.style.opacity = "0";
    document.body.append(temporary);
    temporary.select();
    document.execCommand("copy");
    temporary.remove();
  }

  function packageReferenceControl(
    parent: HTMLElement,
    variant: PackageDetailVariant,
    versions: PackageRelease[],
  ): void {
    const initialVersion = upstreamVersion(versions[0]);
    if (!consumerReference(variant, initialVersion)) return;
    const group = document.createElement("div");
    group.className = "package-reference";
    const label = createText(
      group,
      "span",
      `${packageCopy.consumer_declaration} · ${consumerFile(variant.registry, packageCopy.consumer_config)}`,
    );
    label.className = "package-reference__label";
    const referenceChoices = versions.filter((release, index, values) => {
      const reference = consumerReference(variant, upstreamVersion(release));
      return (
        values.findIndex(
          (candidate) =>
            consumerReference(variant, upstreamVersion(candidate)) ===
            reference,
        ) === index
      );
    });
    if (referenceChoices.length > 1) {
      const select = document.createElement("select");
      select.className = "package-reference__version";
      select.setAttribute("aria-label", packageCopy.reference_version);
      for (const release of referenceChoices) {
        const version = upstreamVersion(release);
        const option = createText(select, "option", release.version);
        option.value = version;
      }
      group.append(select);
      select.addEventListener("change", () => {
        value.textContent = consumerReference(variant, select.value);
      });
    }
    const copy = document.createElement("button");
    copy.type = "button";
    copy.className = "package-reference__copy";
    copy.title = packageCopy.copy_declaration;
    const value = createText(
      copy,
      "code",
      consumerReference(variant, initialVersion),
    );
    value.className = "package-reference__value";
    const icon = createText(copy, "span", "⧉");
    icon.className = "package-reference__icon";
    icon.setAttribute("aria-hidden", "true");
    copy.addEventListener("click", async () => {
      try {
        await copyText(value.textContent ?? "");
        copy.classList.add("is-copied");
        icon.textContent = "✓";
        copy.setAttribute("aria-label", packageCopy.declaration_copied);
        window.setTimeout(() => {
          copy.classList.remove("is-copied");
          icon.textContent = "⧉";
          copy.setAttribute("aria-label", packageCopy.copy_declaration);
        }, 1500);
      } catch (error) {
        console.error(error);
        copy.classList.add("has-error");
      }
    });
    copy.setAttribute("aria-label", packageCopy.copy_declaration);
    group.append(copy);
    parent.append(group);
  }

  function packageVersionOverview(
    variants: PackageDetailVariant[],
  ): HTMLDetailsElement | null {
    const releases = new Map<string, Map<string, string[]>>();
    for (const variant of variants) {
      for (const release of packageVersions(
        variant.versions,
        variant.default_version,
        variant.release_metadata,
      )) {
        const upstream = upstreamVersion(release);
        if (!releases.has(upstream)) releases.set(upstream, new Map());
        const managerReleases = releases.get(upstream)!;
        if (!managerReleases.has(variant.registry)) {
          managerReleases.set(variant.registry, []);
        }
        const exact = managerReleases.get(variant.registry)!;
        if (!exact.includes(release.version)) exact.push(release.version);
      }
    }
    if (!releases.size) return null;
    const table = document.createElement("table");
    table.className = "package-version-overview";
    const managers = variants.map((variant) => variant.registry);
    const head = document.createElement("tr");
    createText(head, "th", packageCopy.version);
    managers.forEach((manager) =>
      createText(head, "th", managerLabel(manager)),
    );
    const thead = document.createElement("thead");
    thead.append(head);
    table.append(thead);
    const body = document.createElement("tbody");
    for (const [version, available] of releases) {
      const row = document.createElement("tr");
      createText(row, "th", version);
      managers.forEach((manager) =>
        createText(row, "td", available.get(manager)?.join(", ") || "—"),
      );
      body.append(row);
    }
    table.append(body);
    const disclosure = document.createElement("details");
    disclosure.className = "package-version-disclosure";
    createText(
      disclosure,
      "summary",
      `${packageCopy.version_availability} (${releases.size})`,
    );
    disclosure.append(table);
    return disclosure;
  }

  function renderPackageDetails(
    body: HTMLElement,
    record: PackageRecord,
    variants: PackageDetailVariant[],
  ): void {
    body.replaceChildren();
    const overview = packageVersionOverview(variants);
    if (overview) body.append(overview);
    const tabs = document.createElement("div");
    tabs.className = "package-tabs";
    tabs.setAttribute("role", "tablist");
    const panels = document.createElement("div");
    variants.forEach((variant, index) => {
      const panelId = `package-${record.id.replace(/[^a-z0-9]+/gi, "-")}-${index}`;
      const tab = document.createElement("button");
      tab.type = "button";
      tab.setAttribute("role", "tab");
      tab.setAttribute("aria-controls", panelId);
      tab.setAttribute("aria-selected", String(index === 0));
      const logo = document.createElement("span");
      logo.className = `package-manager-logo package-manager-logo--${variant.registry}`;
      logo.setAttribute("aria-hidden", "true");
      const labels = document.createElement("span");
      labels.className = "package-tab__labels";
      const manager = document.createElement("span");
      manager.className = "package-tab__manager";
      createText(manager, "strong", managerLabel(variant.registry));
      labels.append(manager);
      createText(labels, "small", variant.name);
      tab.append(logo, labels);
      const panel = document.createElement("section");
      panel.id = panelId;
      panel.className = "package-variant";
      panel.setAttribute("role", "tabpanel");
      panel.hidden = index !== 0;
      packageStatus(panel, variant);
      if (variant.description || variant.summary) {
        const description = document.createElement("div");
        description.className = "package-variant__description";
        if (variant.description) description.innerHTML = variant.description;
        else description.textContent = variant.summary || "";
        if (description.textContent) {
          if (description.textContent.length > 500) {
            const disclosure = document.createElement("details");
            disclosure.className = "package-description-disclosure";
            createText(disclosure, "summary", packageCopy.description);
            disclosure.append(description);
            panel.append(disclosure);
          } else {
            panel.append(description);
          }
        }
      }
      packageChips(panel, packageCopy.topics, variant.topics);
      const versions = packageVersions(
        variant.versions,
        variant.default_version,
        variant.release_metadata,
      );
      const releases = packageReleaseTable(variant, versions);
      if (releases) panel.append(releases);
      const fields = document.createElement("dl");
      packageLicenses(fields, variant.licenses);
      packageDependencies(fields, variant.dependency_links);
      packageField(fields, packageCopy.components, variant.components);
      packageField(fields, packageCopy.platforms, variant.platforms);
      packageField(fields, packageCopy.authors, variant.authors);
      packageField(fields, packageCopy.maintainers, variant.maintainers);
      packageField(
        fields,
        packageCopy.also_packaged_as,
        variant.external_names,
      );
      panel.append(fields);
      packageOptions(
        panel,
        variant.options,
        variant.default_options,
        variant.features,
      );
      const links = document.createElement("nav");
      links.className = "package-variant__links";
      links.setAttribute(
        "aria-label",
        `${managerLabel(variant.registry)} ${packageCopy.package_links_suffix}`,
      );
      packageReferenceControl(links, variant, versions);
      externalPackageLink(
        links,
        `${packageCopy.open_on_prefix} ${managerLabel(variant.registry)}`,
        variant.native_url || packageSiteUrl(variant),
        true,
      );
      externalPackageLink(links, packageCopy.recipe, variant.recipe_url);
      externalPackageLink(
        links,
        packageCopy.documentation,
        variant.documentation_url,
      );
      externalPackageLink(links, packageCopy.homepage, variant.homepage);
      const upstreamUrl =
        variant.repository_url || (variant.source_urls || [])[0];
      if (upstreamUrl !== variant.homepage) {
        externalPackageLink(links, packageCopy.upstream_source, upstreamUrl);
      }
      panel.append(links);
      panels.append(panel);
      tab.addEventListener("click", () => {
        tabs.querySelectorAll('[role="tab"]').forEach((item) => {
          item.setAttribute("aria-selected", String(item === tab));
        });
        panels
          .querySelectorAll<HTMLElement>('[role="tabpanel"]')
          .forEach((item) => {
            item.hidden = item !== panel;
          });
      });
      tabs.append(tab);
    });
    body.append(tabs, panels);
  }

  function packageEntry(
    record: PackageRecord,
    state: PackageState,
  ): HTMLDetailsElement {
    const details = document.createElement("details");
    details.className = "package-entry";
    const summary = document.createElement("summary");
    const nameCell = document.createElement("span");
    nameCell.className = "package-entry__names";
    const heading = createText(nameCell, "span", record.title || record.id);
    heading.className = "package-entry__name";
    const alternateNames = record.aliases || [];
    if (alternateNames.length) {
      createText(
        nameCell,
        "small",
        `${packageCopy.also_packaged_as} ${alternateNames.join(", ")}`,
      );
    }
    summary.append(nameCell);
    const description = document.createElement("span");
    description.className = "package-entry__description";
    if (record.content) description.textContent = record.content;
    else description.innerText = packageCopy.no_description;
    summary.append(description);

    const managers = document.createElement("span");
    managers.className = "package-entry__managers";
    const availableManagers = [
      ...new Set(
        (record.packages || []).map((packageId) => packageId.split(":", 1)[0]),
      ),
    ];
    for (const manager of availableManagers) {
      const badge = createText(managers, "button", managerLabel(manager));
      badge.type = "button";
      badge.className = "package-manager";
      badge.title = `${packageCopy.show_available_prefix} ${managerLabel(manager)}`;
      badge.addEventListener("click", async (event) => {
        event.stopPropagation();
        await selectManager(manager);
      });
    }
    summary.append(managers);
    createText(
      summary,
      "span",
      (record.licenses || []).join(", ") || packageCopy.unspecified,
    ).className = "package-entry__license";
    details.append(summary);

    const body = document.createElement("div");
    body.className = "package-entry__body";
    createText(body, "p", copy.open_to_load).className =
      "package-entry__loading";
    details.append(body);
    details.addEventListener("toggle", async () => {
      if (!details.open || details.dataset.detailsLoaded) return;
      details.dataset.detailsLoaded = "loading";
      const loading = body.querySelector<HTMLElement>(
        ".package-entry__loading",
      );
      if (loading) loading.textContent = packageCopy.loading_metadata;
      try {
        const results = await Promise.allSettled(
          (record.packages || []).map(async (packageId) => {
            const manager = packageId.split(":", 1)[0];
            if (!state.details?.has(manager)) {
              const base = new URL(state.detailsUrl, document.baseURI);
              state.details?.set(
                manager,
                new StaticRecordCollection(
                  new URL(`${manager}/index.json`, base),
                ),
              );
            }
            const result = await state.details?.get(manager)?.record(packageId);
            if (!result) throw new Error(`No package details for ${packageId}`);
            const separator = packageId.indexOf(":");
            return {
              ...result,
              registry: packageId.slice(0, separator),
              name: packageId.slice(separator + 1),
            } as PackageDetailVariant;
          }),
        );
        const variants = results
          .filter((result) => result.status === "fulfilled")
          .map((result) => result.value);
        const failures = results.filter(
          (result) => result.status === "rejected",
        );
        failures.forEach((result) => console.error(result.reason));
        if (!variants.length)
          throw new Error("No package details could be loaded");
        renderPackageDetails(body, record, variants);
        if (failures.length) {
          const warning = createText(
            body,
            "p",
            `${failures.length} ${packageCopy.record_failure_suffix}`,
          );
          warning.className = "package-entry__warning";
          body.prepend(warning);
        }
        details.dataset.detailsLoaded = "true";
      } catch (error) {
        console.error(error);
        body.replaceChildren();
        createText(body, "p", packageCopy.metadata_failure).className =
          "package-entry__loading";
        delete details.dataset.detailsLoaded;
      }
    });
    return details;
  }

  return { managerLabel, packageEntry };
}
