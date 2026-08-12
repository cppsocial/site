(function () {
    "use strict";

    const directory = document.querySelector("[data-directory]");
    const input = document.querySelector("[data-directory-input]");
    const clear = document.querySelector("[data-directory-clear]");
    const status = document.querySelector("[data-directory-status]");
    const packageMatchSummary = document.querySelector("[data-package-match-summary]");
    if (!directory || !input || !clear || !status) return;

    const sections = Array.from(directory.querySelectorAll("[data-directory-section]"));
    const hasPackageSection = sections.some(
        (section) => section.dataset.deferredKind === "package",
    );
    const deferred = new Map();
    const fieldInputs = Array.from(document.querySelectorAll("[data-search-field]"));
    const afterInput = document.querySelector("[data-search-after]");
    const beforeInput = document.querySelector("[data-search-before]");
    const categoryInputs = Array.from(
        document.querySelectorAll("input[data-search-category]"),
    );
    const searchTokens = document.querySelector("[data-search-tokens]");
    const managerChoices = Array.from(
        document.querySelectorAll("[data-search-manager-choice]"),
    );
    const includeUnrelatedInput = document.querySelector("[data-search-include-unrelated]");
    const advanced = document.querySelector("[data-search-advanced]");
    const options = document.querySelector("[data-search-options]");
    const emptyMessage = directory.dataset.emptyMessage || "No matching entries found.";
    const minimumQueryLength = 2;
    const now = new Date();
    const today = [
        now.getFullYear(),
        String(now.getMonth() + 1).padStart(2, "0"),
        String(now.getDate()).padStart(2, "0"),
    ].join("-");
    let items = [];
    let itemsBySection = new Map();
    let searchGeneration = 0;
    let pendingPackageId = "";
    let activeManagerFilters = new Set();

    for (const control of [afterInput, beforeInput].filter(Boolean)) {
        control.max = today;
    }
    if (beforeInput && !beforeInput.value) beforeInput.value = today;
    if (options) document.body.append(options);

    function normalize(value) {
        return String(value || "").normalize("NFKC").toLocaleLowerCase().trim()
            .replace(/\s+/g, " ");
    }

    function searchTerms(value) {
        return normalize(value).match(/[\p{L}\p{N}_+#.-]+/gu) || [];
    }

    const packageManagers = new Set([
        "bazel", "conan", "cppget", "hunter", "meson", "spack", "vcpkg", "xmake",
    ]);

    function managerQuery(value) {
        const managers = new Set();
        const text = String(value || "").replace(
            /(^|\s)manager:([a-z0-9-]+)(?=\s|$)/gi,
            (match, spacing, manager) => {
                const normalized = manager.toLocaleLowerCase();
                if (!packageManagers.has(normalized)) return match;
                managers.add(normalized);
                return spacing;
            },
        );
        return { managers, text: text.replace(/\s+/g, " ").trim() };
    }

    function setManagerQuery(managers, text = input.value) {
        activeManagerFilters = new Set(managers);
        input.value = text;
    }

    function renderManagerTokens(managers) {
        if (!searchTokens) return;
        searchTokens.replaceChildren();
        for (const manager of managers) {
            const token = createText(searchTokens, "button", `${managerLabel(manager)} ×`);
            token.type = "button";
            token.className = "directory-search__token";
            token.title = `Remove ${managerLabel(manager)} requirement`;
            token.setAttribute(
                "aria-label", `Remove packages available in ${managerLabel(manager)}`,
            );
            token.addEventListener("click", async () => {
                activeManagerFilters.delete(manager);
                setManagerQuery(activeManagerFilters);
                await update();
                input.focus();
            });
        }
        searchTokens.hidden = managers.size === 0;
        for (const choice of managerChoices) {
            choice.setAttribute("aria-pressed", String(managers.has(choice.value)));
        }
    }

    function detailManifestKey(manifest) {
        return (manifest?.buckets || [])
            .map((bucket) => `${bucket.index}:${bucket.revision}`).join("|");
    }

    function invalidatePackageDetails(state) {
        state.section.querySelectorAll(".package-entry").forEach((entry) => {
            delete entry.dataset.detailsLoaded;
            const body = entry.querySelector(".package-entry__body");
            if (!body) return;
            const loading = createText(
                document.createDocumentFragment(), "p", "Open to load package-manager metadata.",
            );
            loading.className = "package-entry__loading";
            body.replaceChildren(loading);
            if (entry.open) entry.dispatchEvent(new Event("toggle"));
        });
    }

    function scrollToPackage(card) {
        const offset = [".header", ".directory-header", ".directory-search"]
            .map((selector) => document.querySelector(selector))
            .filter(Boolean)
            .reduce((bottom, element) => {
                const style = getComputedStyle(element);
                if (!["fixed", "sticky"].includes(style.position)) return bottom;
                return Math.max(
                    bottom,
                    (Number.parseFloat(style.top) || 0) + element.offsetHeight,
                );
            }, 0);
        window.scrollTo({
            top: window.scrollY + card.getBoundingClientRect().top - offset - 12,
            behavior: "smooth",
        });
    }

    function filters() {
        const before = beforeInput?.value || "";
        const managerFilter = managerQuery(input.value);
        for (const manager of managerFilter.managers) {
            activeManagerFilters.add(manager);
        }
        if (managerFilter.managers.size) input.value = managerFilter.text;
        return {
            terms: searchTerms(managerFilter.text),
            fields: fieldInputs.length
                ? fieldInputs.filter((control) => control.checked)
                    .map((control) => control.value)
                : ["all"],
            after: afterInput?.value || "",
            before,
            dateActive: Boolean(afterInput?.value || (before && before !== today)),
            categories: new Set(
                categoryInputs.filter((control) => control.checked)
                    .map((control) => control.value),
            ),
            managers: new Set(activeManagerFilters),
            includeUnrelated: includeUnrelatedInput?.checked ?? true,
        };
    }

    function sectionItems(section) {
        return itemsBySection.get(section) || [];
    }

    function refreshItems() {
        items = Array.from(directory.querySelectorAll("[data-directory-item]"));
        itemsBySection = new Map(sections.map((section) => [section, []]));
        for (const item of items) {
            const section = item.closest("[data-directory-section]");
            if (section) itemsBySection.get(section)?.push(item);
        }
        for (const section of sections) {
            sectionItems(section)
                .filter((item) => item.hasAttribute("data-browse-item"))
                .forEach((item, index) => {
                    item.dataset.pageIndex = String(index);
                });
        }
    }

    function createText(parent, name, value) {
        const element = document.createElement(name);
        element.textContent = value;
        parent.append(element);
        return element;
    }

    function blogPost(record) {
        const card = document.createElement("article");
        card.className = "blog-post-card";
        card.tabIndex = 0;
        card.setAttribute("role", "link");
        card.dataset.cardHref = record.url;
        const source = createText(card, "p", `${record.source} · `);
        source.className = "blog-post-card__source";
        const time = createText(source, "time", record.published.slice(0, 10));
        time.dateTime = record.published;
        const heading = document.createElement("h3");
        const link = createText(heading, "a", record.title);
        link.href = record.url;
        link.target = "_blank";
        link.rel = "noopener";
        card.append(heading);
        const description = document.createElement("div");
        description.className = "blog-post-card__description";
        if (record.description) description.innerHTML = record.description;
        if (description.textContent) card.append(description);
        return card;
    }

    function youtubeVideo(record) {
        const card = document.createElement("article");
        card.className = "card video-card";
        card.tabIndex = 0;
        card.setAttribute("role", "link");
        card.dataset.cardHref = record.url;
        const visual = document.createElement("a");
        visual.className = "video-card__visual";
        visual.href = record.url;
        visual.target = "_blank";
        visual.rel = "noopener";
        visual.setAttribute("aria-label", `Watch ${record.title} on YouTube`);
        if (record.thumbnail_url) {
            const image = document.createElement("img");
            image.src = record.thumbnail_url;
            image.alt = "";
            image.loading = "lazy";
            image.decoding = "async";
            image.referrerPolicy = "no-referrer";
            visual.append(image);
        }
        const play = createText(visual, "span", "▶");
        play.className = "video-card__play";
        play.setAttribute("aria-hidden", "true");
        card.append(visual);
        const body = document.createElement("div");
        body.className = "video-card__body";
        const heading = document.createElement("h3");
        const link = createText(heading, "a", record.title);
        link.href = record.url;
        link.target = "_blank";
        link.rel = "noopener";
        body.append(heading);
        const byline = createText(body, "p", `${record.channel} · `);
        byline.className = "video-card__byline";
        const time = createText(byline, "time", record.published.slice(0, 10));
        time.dateTime = record.published;
        card.append(body);
        return card;
    }

    function packageField(parent, label, values) {
        const items = Array.isArray(values) ? values : [values];
        const visible = items.filter(Boolean);
        if (!visible.length) return;
        const row = document.createElement("div");
        row.className = "package-variant__field";
        createText(row, "dt", label);
        createText(row, "dd", visible.join(", "));
        parent.append(row);
    }

    function packageDependencies(parent, dependencies) {
        if (!dependencies?.length) return;
        const row = document.createElement("div");
        row.className = "package-variant__field";
        createText(row, "dt", "Dependencies");
        const values = document.createElement("dd");
        dependencies.forEach((dependency, index) => {
            if (index) values.append(document.createTextNode(", "));
            const name = dependency.name || dependency.id;
            const suffix = [dependency.constraint, dependency.kind, dependency.condition]
                .filter(Boolean).join(" · ");
            const label = suffix ? `${name} (${suffix})` : name;
            if (!dependency.id) {
                values.append(document.createTextNode(label));
                return;
            }
            const link = createText(values, "a", label);
            link.href = `#${encodeURIComponent(dependency.id)}`;
            link.addEventListener("click", async (event) => {
                event.preventDefault();
                pendingPackageId = dependency.id;
                input.value = name;
                history.replaceState(null, "", link.href);
                await update();
            });
        });
        row.append(values);
        parent.append(row);
    }

    function packageLicenses(parent, licenses) {
        const visible = (licenses || []).filter(Boolean);
        if (!visible.length) return;
        const row = document.createElement("div");
        row.className = "package-variant__field";
        createText(row, "dt", "License");
        const values = document.createElement("dd");
        visible.forEach((license, index) => {
            if (index) values.append(document.createTextNode(", "));
            const expression = /^[A-Za-z0-9][A-Za-z0-9.+-]*$/.test(license)
                || /\s(?:AND|OR|WITH)\s|[()]/.test(license);
            if (!expression) {
                values.append(document.createTextNode(license));
                return;
            }
            for (const token of license.split(/(\s+|[()])/)) {
                if (!token || /^\s+$|^[()]$/.test(token)
                    || ["AND", "OR", "WITH"].includes(token)) {
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

    function packageReleaseTable(versions) {
        if (!versions.length) return null;
        const disclosure = document.createElement("details");
        disclosure.className = "package-release-disclosure";
        disclosure.open = true;
        createText(disclosure, "summary", `Releases (${versions.length})`);
        const scroller = document.createElement("div");
        scroller.className = "package-release-scroll";
        const table = document.createElement("table");
        table.className = "package-release-table";
        const head = document.createElement("tr");
        for (const label of ["Version", "Release metadata", "Artifacts"]) {
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
                release.channel && `channel: ${release.channel}`,
                release.packaging_revision && `revision: ${release.packaging_revision}`,
                ...(release.compatibility || []).map((item) => `requires ${item}`),
            ].filter(Boolean);
            createText(row, "td", metadata.join(" · ") || "—");
            const artifacts = document.createElement("td");
            const linked = (release.artifacts || []).filter((artifact) => artifact.url);
            if (!linked.length) {
                artifacts.textContent = "—";
            } else {
                for (const artifact of linked) {
                    const item = document.createElement("div");
                    item.className = "package-release-artifact";
                    const label = String(artifact.kind || "artifact").replaceAll("_", " ");
                    externalPackageLink(item, label, artifact.url);
                    if (artifact.checksums?.length) {
                        const hashes = document.createElement("details");
                        createText(hashes, "summary", "Verify");
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

    function packageSiteUrl(variant) {
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
            return `https://hunter.readthedocs.io/en/latest/packages/pkg/${name}.html`
        }
        if (variant.registry === "bazel") {
            return `https://registry.bazel.build/modules/${name}`;
        }
        if (variant.registry === "xmake") {
            return `https://packages.xmake.io/packages/${name}`;
        }
        return "";
    }

    function managerLabel(value) {
        return { conan: "Conan", vcpkg: "vcpkg", spack: "spack", meson: "Meson", cppget: "build2", hunter: "Hunter", bazel: "Bazel", xmake: "xmake" }[value]
            || value;
    }

    function externalPackageLink(parent, label, href, primary = false) {
        if (!href) return;
        const link = createText(parent, "a", label);
        link.className = `package-link${primary ? " package-link--primary" : ""}`;
        link.href = href;
        link.target = "_blank";
        link.rel = "noopener";
    }

    const versionCollator = new Intl.Collator("en", {
        numeric: true,
        sensitivity: "base",
    });

    function packageVersions(versions, defaultVersion = "") {
        const releases = Object.entries(versions || {}).map(([version, metadata]) => ({
            version,
            ...(Array.isArray(metadata) ? { checksums: metadata } : metadata),
        }));
        return releases.sort((left, right) => {
            const leftDefault = upstreamVersion(left) === defaultVersion;
            const rightDefault = upstreamVersion(right) === defaultVersion;
            if (leftDefault !== rightDefault) return leftDefault ? -1 : 1;
            return versionCollator.compare(right.version, left.version);
        });
    }

    function upstreamVersion(release) {
        return release?.upstream_version || release?.version?.split(/[#@]/, 1)[0] || "";
    }

    function consumerReference(variant, version = "") {
        const name = variant.name;
        if (variant.registry === "conan") {
            return `[requires]\n${name}${version ? `/${version}` : ""}`;
        }
        if (variant.registry === "vcpkg") return `"${name}"`;
        if (variant.registry === "spack") {
            return `spack:\n  specs:\n  - ${name}${version ? `@${version}` : ""}`;
        }
        if (variant.registry === "meson") return `subproject('${name}')`;
        if (variant.registry === "bazel") {
            const selected = version ? `, version = "${version}"` : "";
            return `bazel_dep(name = "${name}"${selected})`;
        }
        if (variant.registry === "cppget") {
            return `depends: ${name}${version ? ` ^${version}` : ""}`;
        }
        if (variant.registry === "hunter") return `hunter_add_package(${name})`;
        if (variant.registry === "xmake") {
            return `add_requires("${name}${version ? ` ${version}` : ""}")`;
        }
        return "";
    }

    function consumerFile(registry) {
        return {
            bazel: "MODULE.bazel",
            conan: "conanfile.txt",
            cppget: "manifest",
            hunter: "CMakeLists.txt",
            meson: "meson.build",
            spack: "spack.yaml",
            vcpkg: "vcpkg.json",
            xmake: "xmake.lua",
        }[registry] || "consumer config";
    }

    async function copyText(value) {
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

    function packageReferenceControl(parent, variant, versions) {
        const initialVersion = upstreamVersion(versions[0]);
        if (!consumerReference(variant, initialVersion)) return;
        const group = document.createElement("div");
        group.className = "package-reference";
        const label = createText(
            group, "span", `Consumer declaration · ${consumerFile(variant.registry)}`,
        );
        label.className = "package-reference__label";
        const referenceChoices = versions.filter((release, index, values) => {
            const reference = consumerReference(variant, upstreamVersion(release));
            return values.findIndex((candidate) => (
                consumerReference(variant, upstreamVersion(candidate)) === reference
            )) === index;
        });
        if (referenceChoices.length > 1) {
            const select = document.createElement("select");
            select.className = "package-reference__version";
            select.setAttribute("aria-label", "Reference version");
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
        copy.title = "Copy dependency declaration";
        const value = createText(copy, "code", consumerReference(variant, initialVersion));
        value.className = "package-reference__value";
        const icon = createText(copy, "span", "⧉");
        icon.className = "package-reference__icon";
        icon.setAttribute("aria-hidden", "true");
        copy.addEventListener("click", async () => {
            try {
                await copyText(value.textContent);
                copy.classList.add("is-copied");
                icon.textContent = "✓";
                copy.setAttribute("aria-label", "Dependency declaration copied");
                window.setTimeout(() => {
                    copy.classList.remove("is-copied");
                    icon.textContent = "⧉";
                    copy.setAttribute("aria-label", "Copy dependency declaration");
                }, 1500);
            } catch (error) {
                console.error(error);
                copy.classList.add("has-error");
            }
        });
        copy.setAttribute("aria-label", "Copy dependency declaration");
        group.append(copy);
        parent.append(group);
    }

    function packageVersionOverview(variants) {
        const releases = new Map();
        for (const variant of variants) {
            for (const release of packageVersions(
                variant.versions, variant.default_version,
            )) {
                const upstream = upstreamVersion(release);
                if (!releases.has(upstream)) releases.set(upstream, new Map());
                const managerReleases = releases.get(upstream);
                if (!managerReleases.has(variant.registry)) {
                    managerReleases.set(variant.registry, []);
                }
                const exact = managerReleases.get(variant.registry);
                if (!exact.includes(release.version)) exact.push(release.version);
            }
        }
        if (!releases.size) return null;
        const table = document.createElement("table");
        table.className = "package-version-overview";
        const managers = variants.map((variant) => variant.registry);
        const head = document.createElement("tr");
        createText(head, "th", "Version");
        managers.forEach((manager) => createText(head, "th", managerLabel(manager)));
        const thead = document.createElement("thead");
        thead.append(head);
        table.append(thead);
        const body = document.createElement("tbody");
        for (const [version, available] of releases) {
            const row = document.createElement("tr");
            createText(row, "th", version);
            managers.forEach((manager) => createText(
                row, "td", available.get(manager)?.join(", ") || "—",
            ));
            body.append(row);
        }
        table.append(body);
        const disclosure = document.createElement("details");
        disclosure.className = "package-version-disclosure";
        createText(disclosure, "summary", `Version availability (${releases.size})`);
        disclosure.append(table);
        return disclosure;
    }

    function renderPackageDetails(body, record, variants) {
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
            if (variant.description) {
                const description = document.createElement("div");
                description.className = "package-variant__description";
                description.innerHTML = variant.description;
                if (description.textContent) {
                    if (description.textContent.length > 500) {
                        const disclosure = document.createElement("details");
                        disclosure.className = "package-description-disclosure";
                        createText(disclosure, "summary", "Description");
                        disclosure.append(description);
                        panel.append(disclosure);
                    } else {
                        panel.append(description);
                    }
                }
            }
            const versions = packageVersions(
                variant.versions, variant.default_version,
            );
            const releases = packageReleaseTable(versions);
            if (releases) panel.append(releases);
            const fields = document.createElement("dl");
            packageLicenses(fields, variant.licenses);
            packageDependencies(fields, variant.dependency_links);
            packageField(fields, "Options", variant.options);
            packageField(
                fields,
                "Default options",
                Object.entries(variant.default_options || {})
                    .map(([name, value]) => `${name}=${value}`),
            );
            packageField(fields, "Components", variant.components);
            packageField(fields, "Platforms", variant.platforms);
            packageField(fields, "Authors", variant.authors);
            packageField(fields, "Maintainers", variant.maintainers);
            packageField(fields, "Topics", variant.topics);
            packageField(fields, "Languages", variant.languages);
            packageField(fields, "Package type", variant.package_type);
            panel.append(fields);
            const links = document.createElement("nav");
            links.className = "package-variant__links";
            links.setAttribute("aria-label", `${managerLabel(variant.registry)} package links`);
            packageReferenceControl(links, variant, versions);
            externalPackageLink(
                links, `Open on ${managerLabel(variant.registry)}`,
                variant.native_url || packageSiteUrl(variant), true,
            );
            externalPackageLink(links, "Recipe", variant.recipe_url);
            externalPackageLink(links, "Homepage", variant.homepage);
            const upstreamUrl = variant.repository_url
                || (variant.source_urls || [])[0];
            if (upstreamUrl !== variant.homepage) {
                externalPackageLink(links, "Upstream source", upstreamUrl);
            }
            panel.append(links);
            panels.append(panel);
            tab.addEventListener("click", () => {
                tabs.querySelectorAll('[role="tab"]').forEach((item) => {
                    item.setAttribute("aria-selected", String(item === tab));
                });
                panels.querySelectorAll('[role="tabpanel"]').forEach((item) => {
                    item.hidden = item !== panel;
                });
            });
            tabs.append(tab);
        });
        body.append(tabs, panels);
    }

    function packageEntry(record, state) {
        const details = document.createElement("details");
        details.className = "package-entry";
        const summary = document.createElement("summary");
        const nameCell = document.createElement("span");
        nameCell.className = "package-entry__names";
        const heading = createText(nameCell, "span", record.title || record.id);
        heading.className = "package-entry__name";
        const alternateNames = record.aliases || [];
        if (alternateNames.length) {
            createText(nameCell, "small", `Also packaged as ${alternateNames.join(", ")}`);
        }
        summary.append(nameCell);
        const description = document.createElement("span");
        description.className = "package-entry__description";
        if (record.content)
            description.textContent = record.content;
        else
            description.innerText = "No description available";
        summary.append(description);

        const managers = document.createElement("span");
        managers.className = "package-entry__managers";
        const availableManagers = [...new Set(
            (record.packages || []).map((packageId) => packageId.split(":", 1)[0]),
        )];
        for (const manager of availableManagers) {
            const badge = createText(managers, "button", managerLabel(manager));
            badge.type = "button";
            badge.className = "package-manager";
            badge.title = `Show packages available in ${managerLabel(manager)}`;
            badge.addEventListener("click", async (event) => {
                event.stopPropagation();
                activeManagerFilters.add(manager);
                setManagerQuery(activeManagerFilters);
                await update();
                input.focus();
            });
        }
        summary.append(managers);
        createText(summary, "span", (record.licenses || []).join(", ") || "Unspecified")
            .className = "package-entry__license";
        details.append(summary);

        const body = document.createElement("div");
        body.className = "package-entry__body";
        createText(body, "p", "Open to load package-manager metadata.")
            .className = "package-entry__loading";
        details.append(body);
        details.addEventListener("toggle", async () => {
            if (!details.open || details.dataset.detailsLoaded) return;
            details.dataset.detailsLoaded = "loading";
            body.querySelector(".package-entry__loading").textContent = "Loading metadata...";
            try {
                const results = await Promise.allSettled((record.packages || []).map(
                    async (packageId) => {
                        const manager = packageId.split(":", 1)[0];
                        if (!state.details?.has(manager)) {
                            const base = new URL(state.detailsUrl, document.baseURI);
                            state.details?.set(
                                manager,
                                new window.CppSearchCache.StaticRecordCollection(
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
                        };
                    },
                ));
                const variants = results.filter((result) => result.status === "fulfilled")
                    .map((result) => result.value);
                const failures = results.filter((result) => result.status === "rejected");
                failures.forEach((result) => console.error(result.reason));
                if (!variants.length) throw new Error("No package details could be loaded");
                renderPackageDetails(body, record, variants);
                if (failures.length) {
                    const warning = createText(
                        body, "p", `${failures.length} package-manager record could not be loaded.`,
                    );
                    warning.className = "package-entry__warning";
                    body.prepend(warning);
                }
                details.dataset.detailsLoaded = "true";
            } catch (error) {
                console.error(error);
                body.replaceChildren();
                createText(body, "p", "Package metadata could not be loaded.")
                    .className = "package-entry__loading";
                delete details.dataset.detailsLoaded;
            }
        });
        return details;
    }

    function renderRecord(state, record, browse) {
        let card = state.section.querySelector(
            `[data-record-id="${CSS.escape(record.id)}"]`,
        );
        if (!card) {
            card = state.kind === "blog-post"
                ? blogPost(record)
                : state.kind === "package"
                    ? packageEntry(record, state)
                    : youtubeVideo(record);
            card.dataset.directoryItem = "";
            card.dataset.recordId = record.id;
            if (state.kind === "package") card.id = record.id;
            state.grid.append(card);
        }
        if (record.cpp_relevance == null) {
            delete card.dataset.cppRelevance;
        } else {
            card.dataset.cppRelevance = String(record.cpp_relevance);
        }
        const indexed = record._terms || {};
        card.dataset.search = Object.values(indexed).flat().join(" ");
        card.dataset.managers = (record.managers || []).join(" ");
        if (state.kind === "package" && record.id === pendingPackageId) {
            pendingPackageId = "";
            card.open = true;
            requestAnimationFrame(() => {
                scrollToPackage(card);
            });
        }
        for (const [field, values] of Object.entries(indexed)) {
            card.dataset[`search${field[0].toUpperCase()}${field.slice(1)}`] =
                values.join(" ");
        }
        if (browse) {
            card.dataset.browseItem = "";
            card.dataset.pagedItem = "";
            delete card.dataset.searchOnly;
        } else if (!card.hasAttribute("data-browse-item")) {
            card.dataset.searchOnly = "";
        }
        return card;
    }

    async function loadIndex(state) {
        if (!state.source) {
            if (!window.CppSearchCache) {
                throw new Error("Search cache is unavailable");
            }
            state.source = new window.CppSearchCache.StaticSearchCollection(state.url);
        }
        state.index = await state.source.manifest();
        return state.index;
    }

    async function cachedRecords(state, current, resultLimit) {
        await loadIndex(state);
        return state.source.recordsForPrefix(
            current.terms.join(" "),
            current.fields,
            current.after,
            current.before,
            resultLimit,
        );
    }

    function packageCounts(records) {
        const managers = new Map();
        for (const record of records) {
            const available = new Set(
                (record.packages || []).map((id) => id.split(":", 1)[0]),
            );
            for (const manager of available) {
                managers.set(manager, (managers.get(manager) || 0) + 1);
            }
        }
        return managers;
    }

    function renderPackageCounts(total, counts) {
        if (!packageMatchSummary) return;
        const number = new Intl.NumberFormat();
        const managers = ["conan", "vcpkg", "spack", "meson", "cppget", "hunter", "bazel", "xmake"]
            .map((manager) => (
                `${managerLabel(manager)}: ${number.format(counts.get(manager) || 0)}`
            ));
        packageMatchSummary.textContent = [
            `${number.format(total)} package${total === 1 ? "" : "s"} matched`,
            ...managers,
        ].join(" · ");
    }

    function renderPackageTotals(state) {
        if (!packageMatchSummary || state.kind !== "package" || !state.index) return;
        renderPackageCounts(
            state.index.count,
            new Map(Object.entries(state.index.manager_counts || {})),
        );
    }

    async function ensureBrowseCount(state, count) {
        const browseFilter = {
            terms: [],
            fields: fieldInputs.length
                ? fieldInputs.map((control) => control.value)
                : ["all"],
            after: "",
            before: state.kind === "package" ? "" : today,
        };
        let cachedCount = 0;
        const render = async () => {
            const records = await cachedRecords(state, browseFilter);
            cachedCount = records.length;
            records.slice(0, count).forEach((record) => {
                renderRecord(state, record, true);
            });
            refreshItems();
            updateItems(filters());
        };
        await render();
        if (cachedCount >= count) return;
        await state.source.synchronize({
            fields: browseFilter.fields,
            onProgress: render,
            stopWhen: () => cachedCount >= count,
        });
    }

    async function renderPreview(state) {
        const response = await fetch(state.url, { cache: "no-cache" });
        if (!response.ok) throw new Error(`Unable to load ${response.url}`);
        const manifest = await response.json();
        state.index = manifest;
        for (const record of manifest.preview || []) {
            renderRecord(state, record, true);
        }
        state.previewCount = manifest.preview?.length || 0;
        refreshItems();
        updateItems(filters());
        renderPackageTotals(state);
    }

    function randomizeGroups() {
        for (const section of sections.filter(
            (candidate) => candidate.hasAttribute("data-randomize"),
        )) {
            const grid = section.querySelector("[data-paged-grid], .directory-grid, .blog-grid");
            if (!grid) continue;
            const cards = Array.from(grid.children);
            for (let index = cards.length - 1; index > 0; index -= 1) {
                const selected = Math.floor(Math.random() * (index + 1));
                [cards[index], cards[selected]] = [cards[selected], cards[index]];
            }
            grid.append(...cards);
        }
    }

    randomizeGroups();

    for (const [index, section] of sections.entries()) {
        const header = section.querySelector(":scope > .directory-section__header");
        const content = section.querySelector(
            ":scope > [data-directory-section-content]",
        );
        if (header && content) {
            const contentId = content.id || `directory-section-${index + 1}`;
            content.id = contentId;
            const button = document.createElement("button");
            button.type = "button";
            button.className = "directory-section__toggle";
            button.setAttribute("aria-controls", contentId);
            button.setAttribute("aria-expanded", "true");
            const sectionName = header.querySelector("h2, h3")?.textContent.trim()
                || "section";
            button.setAttribute("aria-label", "Hide " + sectionName);
            button.innerHTML = '<span data-section-toggle-label>Hide</span><span class="directory-section__toggle-icon" aria-hidden="true"></span>';
            header.append(button);
            button.addEventListener("click", () => {
                const collapsed = section.dataset.collapsed === "true";
                section.dataset.collapsed = String(!collapsed);
                button.setAttribute("aria-expanded", String(collapsed));
                button.setAttribute(
                    "aria-label",
                    (collapsed ? "Hide " : "Show ") + sectionName,
                );
                button.querySelector("[data-section-toggle-label]").textContent =
                    collapsed ? "Hide" : "Show";
                update();
            });
        }
        const pageRows = Number(section.dataset.pageRows || 0);
        if (pageRows > 0) section.dataset.visibleRows = String(pageRows);
        if (section.dataset.deferredIndex) {
            deferred.set(section, {
                section,
                url: section.dataset.deferredIndex,
                kind: section.dataset.deferredKind,
                grid: section.querySelector("[data-paged-grid]"),
                source: null,
                index: null,
                syncing: false,
                detailsUrl: section.dataset.packageDetails || "",
                details: section.dataset.packageDetails ? new Map() : null,
            });
        }
    }

    function pageLimit(section) {
        const explicit = Number(section.dataset.visibleItems || 0);
        if (explicit) return explicit;
        const rows = Number(section.dataset.visibleRows || 0);
        const grid = section.querySelector("[data-paged-grid]");
        if (!rows || !grid) return 0;
        const columns = getComputedStyle(grid).gridTemplateColumns
            .split(" ").filter(Boolean).length;
        return rows * Math.max(columns, 1);
    }

    function removeSearchOnly() {
        directory.querySelectorAll("[data-search-only]").forEach((item) => {
            item.remove();
        });
        refreshItems();
    }

    function itemMatches(item, current) {
        const section = item.closest("[data-directory-section]");
        const category = section?.dataset.searchCategory;
        if (category && !current.categories.has(category)) return false;
        if (current.managers.size) {
            const available = new Set((item.dataset.managers || "").split(" "));
            if (![...current.managers].every((manager) => available.has(manager))) {
                return false;
            }
        }
        if (
            section?.hasAttribute("data-relevance-filter")
            && !current.includeUnrelated
            && item.dataset.cppRelevance !== undefined
            && Number(item.dataset.cppRelevance)
            < Number(directory.dataset.cppRelevanceThreshold || 0.5)
        ) return false;

        if (current.terms.length) {
            const selected = current.fields.includes("all")
                ? (item.dataset.search || item.textContent)
                : current.fields.map((field) => {
                    const suffix = field[0].toUpperCase() + field.slice(1);
                    return item.dataset[`search${suffix}`] || "";
                }).join(" ");
            const haystack = normalize(selected);
            if (!current.terms.every((term) => haystack.includes(term))) {
                return false;
            }
        }

        if (!current.dateActive || !section?.hasAttribute("data-date-filter")) {
            return true;
        }
        const published = item.querySelector("time[datetime]")?.dateTime || "";
        if (!published) return false;
        return (!current.after || published >= current.after)
            && (!current.before || published <= current.before + "T23:59:59");
    }

    function searchState(current) {
        const categoryFiltering = categoryInputs.some(
            (control) => !control.checked,
        );
        const managerFiltering = current.managers.size > 0;
        return {
            filtering: Boolean(
                current.terms.length || current.dateActive || categoryFiltering
                || managerFiltering
            ),
            expanded: Boolean(
                current.terms.length || current.dateActive || managerFiltering
            ),
        };
    }

    function updateFilterIndicator(current) {
        if (!advanced) return;
        const active = Boolean(
            (fieldInputs.length && current.fields.length !== fieldInputs.length)
            || current.categories.size !== categoryInputs.length
            || current.managers.size > 0
            || current.dateActive
            || (includeUnrelatedInput && current.includeUnrelated)
        );
        advanced.dataset.active = String(active);
        const label = active ? "Search filters (active)" : "Search filters";
        advanced.setAttribute("aria-label", label);
        advanced.title = label;
    }

    function updateItems(current) {
        let matches = 0;
        const stateFlags = searchState(current);
        directory.querySelectorAll("[data-search-context-hide]").forEach((element) => {
            element.hidden = stateFlags.filtering;
        });
        updateFilterIndicator(current);
        for (const item of items) {
            const section = item.closest("[data-directory-section]");
            const collapsed = section?.dataset.collapsed === "true";
            const matchesFilters = itemMatches(item, current);
            const paged = item.hasAttribute("data-paged-item");
            const pageIndex = paged ? Number(item.dataset.pageIndex) : -1;
            const limit = section ? pageLimit(section) : 0;
            const withinPage = !paged || stateFlags.expanded || pageIndex < limit;
            const included = !collapsed && matchesFilters;
            const visible = included && withinPage;
            item.hidden = !visible;
            item.dataset.directoryMatch = String(included);
            if (visible) matches += 1;
        }
        for (const section of sections) {
            const collapsed = section.dataset.collapsed === "true";
            const hasMatch = sectionItems(section).some(
                (item) => item.dataset.directoryMatch === "true",
            );
            section.hidden = Boolean(
                stateFlags.filtering && !collapsed && !hasMatch
            );
            const more = section.querySelector("[data-directory-more]");
            if (!more) continue;
            const state = deferred.get(section);
            const total = state?.index?.count
                ?? Number(section.dataset.total || 0)
                ?? sectionItems(section).length;
            const limit = pageLimit(section);
            more.hidden = Boolean(stateFlags.expanded || limit >= total);
            const remaining = Math.max(0, total - limit);
            if (remaining) {
                more.textContent = `Show more… (${remaining} remaining)`;
            }
        }
        clear.hidden = input.value.length === 0 && current.managers.size === 0;
        const noun = matches === 1 ? "entry" : "entries";
        const syncing = [...deferred.values()].some((state) => state.syncing);
        const tooShort = current.terms.some(
            (term) => term.length < minimumQueryLength
        );
        if (hasPackageSection && !stateFlags.filtering) {
            const packageState = [...deferred.values()].find(
                (state) => state.kind === "package",
            );
            const total = packageState?.index?.count;
            status.textContent = total == null
                ? ""
                : `${new Intl.NumberFormat().format(total)} packages`;
        } else {
            status.textContent = tooShort
                ? `${matches} ${noun} · type at least ${minimumQueryLength} characters`
                : stateFlags.filtering && matches === 0 && !syncing
                    ? emptyMessage
                    : `${matches} ${noun}${syncing ? " · indexing…" : ""}`;
        }
    }

    async function addDeferredMatches(current, generation) {
        const managerFiltering = current.managers.size > 0;
        if (!current.terms.length && !current.dateActive && !managerFiltering) return;
        await Promise.all([...deferred.values()].map(async (state) => {
            if (state.section.dataset.collapsed === "true") return;
            const category = state.section.dataset.searchCategory;
            if (category && !current.categories.has(category)) return;
            const render = async () => {
                if (generation !== searchGeneration) return;
                const records = await cachedRecords(
                    state, current, managerFiltering ? Infinity : undefined,
                );
                if (generation !== searchGeneration) return;
                records.forEach((record) => {
                    renderRecord(state, record, false);
                });
                refreshItems();
                updateItems(current);
            };
            await loadIndex(state);
            if (current.terms.some(
                (term) => term.length < state.index.min_query_length
            )) return;
            await render();
            state.syncing = true;
            updateItems(current);
            state.source.synchronize({
                query: current.terms.join(" "),
                fields: current.fields,
                onProgress: render,
            }).then(() => {
                state.syncing = false;
                if (generation !== searchGeneration) return;
                updateItems(current);
                if (state.kind === "package") {
                    cachedRecords(state, current, Infinity).then((records) => {
                        if (generation === searchGeneration) {
                            renderPackageCounts(records.length, packageCounts(records));
                        }
                    }).catch(console.error);
                }
            }).catch((error) => {
                state.syncing = false;
                console.error(error);
                if (generation === searchGeneration) {
                    status.textContent = "Search data is unavailable.";
                }
            });
        }));
    }

    async function update() {
        const generation = ++searchGeneration;
        const current = filters();
        renderManagerTokens(current.managers);
        removeSearchOnly();
        updateItems(current);
        for (const state of deferred.values()) {
            if (!current.terms.length && !current.dateActive && !current.managers.size) {
                loadIndex(state).then(() => {
                    if (state.kind === "package") {
                        renderPackageTotals(state);
                        updateItems(filters());
                    }
                }).catch(console.error);
            } else if (current.terms.some(
                (term) => term.length < minimumQueryLength
            ) && state.kind === "package" && packageMatchSummary) {
                packageMatchSummary.textContent =
                    `Type at least ${minimumQueryLength} characters to count matches.`;
            } else if (state.kind === "package" && packageMatchSummary) {
                packageMatchSummary.textContent = "Counting matching packages...";
            }
        }
        try {
            await addDeferredMatches(current, generation);
        } catch (error) {
            console.error(error);
            if (generation === searchGeneration) {
                status.textContent = "Search data is unavailable.";
            }
        }
    }

    for (const section of sections) {
        const more = section.querySelector("[data-directory-more]");
        if (!more) continue;
        more.addEventListener("click", async () => {
            const pageRows = Number(section.dataset.pageRows || 0);
            const pageStep = Number(section.dataset.pageStep || 2);
            const visibleRows = Number(section.dataset.visibleRows || pageRows);
            section.dataset.visibleRows = String(visibleRows + pageStep);
            delete section.dataset.visibleItems;
            const state = deferred.get(section);
            const nextLimit = pageLimit(section);
            const available = sectionItems(section).filter(
                (item) => item.hasAttribute("data-browse-item"),
            ).length;
            if (state && nextLimit > available) {
                more.disabled = true;
                more.textContent = "Loading…";
                try {
                    await ensureBrowseCount(state, nextLimit);
                } finally {
                    more.disabled = false;
                }
            }
            update();
        });
    }

    function synchronizeDateBounds(event) {
        if (!afterInput || !beforeInput) return;
        if (event?.target === afterInput && afterInput.value > beforeInput.value) {
            beforeInput.value = afterInput.value;
        }
        if (event?.target === beforeInput && beforeInput.value < afterInput.value) {
            afterInput.value = beforeInput.value;
        }
        afterInput.max = beforeInput.value || today;
        beforeInput.min = afterInput.value || "";
        beforeInput.max = today;
    }

    function activateCaches() {
        deferred.forEach((state) => {
            loadIndex(state).catch(console.error);
        });
    }

    function positionFilterMenu() {
        if (!advanced || !options || options.hidden) return;
        const anchor = advanced.getBoundingClientRect();
        const edge = 8;
        const top = Math.min(anchor.bottom + 6, window.innerHeight - edge);
        options.style.top = `${top}px`;
        options.style.right = `${Math.max(edge, window.innerWidth - anchor.right)}px`;
        options.style.maxHeight = `${Math.max(120, window.innerHeight - top - edge)}px`;
    }

    function closeFilterMenu({ restoreFocus = false } = {}) {
        if (!advanced || !options || options.hidden) return;
        advanced.setAttribute("aria-expanded", "false");
        options.hidden = true;
        if (restoreFocus) advanced.focus();
    }

    advanced?.addEventListener("click", () => {
        const expanded = advanced.getAttribute("aria-expanded") === "true";
        if (expanded) {
            closeFilterMenu();
            return;
        }
        advanced.setAttribute("aria-expanded", "true");
        options.hidden = false;
        positionFilterMenu();
    });

    window.addEventListener("resize", positionFilterMenu);
    window.addEventListener("scroll", positionFilterMenu, { passive: true });

    document.addEventListener("pointerdown", (event) => {
        if (
            options?.hidden
            || advanced?.contains(event.target)
            || options?.contains(event.target)
        ) return;
        closeFilterMenu();
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && options && !options.hidden) {
            event.preventDefault();
            closeFilterMenu({ restoreFocus: true });
        }
    });
    input.addEventListener("input", update);
    for (const control of fieldInputs) {
        control.addEventListener("input", (event) => {
            if (!fieldInputs.some((field) => field.checked)) {
                event.currentTarget.checked = true;
            }
            update();
        });
    }
    for (const control of categoryInputs) {
        control.addEventListener("input", (event) => {
            if (!categoryInputs.some((category) => category.checked)) {
                event.currentTarget.checked = true;
            }
            update();
        });
    }
    for (const choice of managerChoices) {
        choice.addEventListener("click", () => {
            if (activeManagerFilters.has(choice.value)) {
                activeManagerFilters.delete(choice.value);
            } else {
                activeManagerFilters.add(choice.value);
            }
            setManagerQuery(activeManagerFilters);
            update();
        });
    }
    includeUnrelatedInput?.addEventListener("input", update);
    for (const control of [afterInput, beforeInput].filter(Boolean)) {
        control.addEventListener("input", (event) => {
            synchronizeDateBounds(event);
            update();
        });
    }
    synchronizeDateBounds();
    input.addEventListener("focus", activateCaches, { once: true });
    window.addEventListener("resize", () => updateItems(filters()));
    clear.addEventListener("click", () => {
        input.value = "";
        activeManagerFilters.clear();
        update();
        input.focus();
    });

    let lastCacheRefresh = Date.now();
    document.addEventListener("visibilitychange", async () => {
        if (document.visibilityState !== "visible"
            || Date.now() - lastCacheRefresh < 5 * 60 * 1000) return;
        lastCacheRefresh = Date.now();
        let changed = false;
        await Promise.all([...deferred.values()].map(async (state) => {
            if (!state.source) return;
            const before = state.index
                ? `${state.index.epoch}:${state.index.revision}`
                : "";
            const index = await state.source.refresh();
            state.index = index;
            if (before && before !== `${index.epoch}:${index.revision}`) {
                changed = true;
                state.grid?.replaceChildren();
                await ensureBrowseCount(
                    state,
                    Number(state.section.dataset.pageRows || 30),
                );
            }
            let detailsChanged = false;
            await Promise.all([...(state.details?.values() || [])].map(
                async (collection) => {
                    const oldManifest = await collection.manifest();
                    const oldKey = detailManifestKey(oldManifest);
                    const newManifest = await collection.refresh();
                    if (oldKey !== detailManifestKey(newManifest)) detailsChanged = true;
                },
            ));
            if (detailsChanged) {
                changed = true;
                invalidatePackageDetails(state);
            }
        })).catch(console.error);
        if (changed) {
            refreshItems();
            await update();
        }
    });

    document.addEventListener("click", (event) => {
        const tag = event.target.closest("[data-search-tag]");
        if (!tag) return;
        input.value = tag.dataset.searchTag;
        fieldInputs.forEach((field) => {
            field.checked = field.value === "tags";
        });
        update();
        document.querySelector("[data-channel-dialog][open]")?.close();
        input.focus();
        input.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });

    refreshItems();
    update();
    deferred.forEach((state) => {
        if (!sectionItems(state.section).some((item) => item.hasAttribute("data-browse-item"))) {
            const initial = Number(state.section.dataset.pageRows || 30);
            if (state.kind === "package") {
                renderPreview(state).catch(console.error);
            } else {
                ensureBrowseCount(state, initial).catch(console.error);
            }
        }
    });
})();
