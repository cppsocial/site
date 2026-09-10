from typing import Any, Literal

from site_generator import Schema, field, schema

from schemas.pages import Page, PagePresentation, SectionHeading


class PackageArtifact(Schema):
    kind: Literal[
        "upstream_source",
        "registry_package",
        "binary_package",
        "patch",
        "documentation",
    ] = "upstream_source"
    url: str | None = None
    checksums: list[str] | None = None
    filename: str | None = None
    size: int | None = None
    format: str | None = None
    platform: str | None = None
    architecture: str | None = None
    compiler: str | None = None
    build_type: str | None = None
    options: dict[str, str] | None = None
    recipe_revision: str | None = None
    package_id: str | None = None
    package_revision: str | None = None


class PackageDependency(Schema):
    name: str
    constraint: str | None = None
    kind: str | None = None
    feature: str | None = None
    condition: str | None = None
    optional: bool | None = None


class PackageFeature(Schema):
    name: str
    description: str | None = None
    values: list[str] | None = None
    default: str | None = None
    condition: str | None = None


class PackageVersion(Schema):
    version: str
    upstream_version: str | None = None
    packaging_revision: str | int | None = None
    channel: str | None = None
    lifecycle: Literal["active", "yanked", "deprecated", "broken"] | None = None
    lifecycle_reason: str | None = None
    preferred: bool | None = None
    summary: str | None = None
    description: str | None = None
    licenses: list[str] | None = None
    homepage: str | None = None
    repository_url: str | None = None
    documentation_url: str | None = None
    dependencies: list[PackageDependency] | None = None
    features: list[PackageFeature] | None = None
    compatibility: list[str] | None = None
    capabilities: list[str] | None = None
    artifacts: list[PackageArtifact] | None = None
    recipe_revision: str | None = None
    recipe_url: str | None = None


class RegistryPackage(Schema):
    id: str
    registry: str
    name: str
    summary: str | None = None
    description: str | None = None
    description_format: str | None = None
    licenses: list[str] | None = None
    homepage: str | None = None
    repository_url: str | None = None
    documentation_url: str | None = None
    authors: list[str] | None = None
    maintainers: list[str] | None = None
    topics: list[str] | None = None
    languages: list[str] | None = None
    package_type: str | None = None
    deprecated: bool | None = None
    deprecation_reason: str | None = None
    platforms: list[str] | None = None
    dependencies: list[str] | None = None
    dependency_details: list[PackageDependency] | None = None
    options: list[str] | None = None
    default_options: dict[str, str] | None = None
    components: list[str] | None = None
    external_names: list[str] | None = None
    features: list[PackageFeature] | None = None
    versions: list[PackageVersion] | None = None
    default_version: str | None = None
    recipe_url: str | None = None
    native_url: str | None = None


@schema("packages/registry")
class RegistryCatalog(Schema):
    registry: str
    repository: str
    revision: str | None = None
    packages: list[RegistryPackage] | None = None


class PackageReference(Schema):
    registry: str
    package_id: str
    metadata_file: str
    recipe_url: str | None = None


class PackageGroupOverride(Schema):
    id: str | None = None
    name: str | None = None
    aliases: list[str] | None = None
    packages: list[str]
    reason: str | None = None


class PackageNeverMerge(Schema):
    packages: list[str]
    reason: str | None = None


class PackageFieldPreference(Schema):
    package: str
    field: Literal["summary", "licenses", "homepage",
                   "repository_url", "documentation_url"]
    source: str
    reason: str | None = None


class PackageFieldCorrection(Schema):
    package: str
    field: str
    operation: Literal["add", "replace", "remove"] = "replace"
    value: Any | None = None
    version: str | None = None
    reason: str


@schema("packages/overrides")
class PackageOverrides(Schema):
    ignored: list[str] = field(default_factory=list)
    ignored_prefixes: list[str] = field(default_factory=list)
    groups: list[PackageGroupOverride] | None = None
    never_merge: list[PackageNeverMerge] | None = None
    preferences: list[PackageFieldPreference] | None = None
    corrections: list[PackageFieldCorrection] | None = None


class PackageEntityIdentity(Schema):
    id: str
    name: str | None = None
    aliases: list[str] | None = None
    packages: list[str]


@schema("packages/entities")
class PackageEntityCatalog(Schema):
    entities: list[PackageEntityIdentity] | None = None


class MatchEvidence(Schema):
    signal: str
    weight: float


class PackageMatch(Schema):
    left: str
    right: str
    confidence: float
    decision: Literal[
        "merge",
        "manual_merge",
        "none",
        "conflict",
    ]
    evidence: list[MatchEvidence] = field(default_factory=list)


@schema("packages/matches")
class MatchCatalog(Schema):
    threshold: float
    matches: list[PackageMatch] = field(default_factory=list)


class PackagesConfig(PagePresentation):
    package_view_toggle: bool = False
    provenance: dict[str, Any] = field(default_factory=dict)


class PackageCatalogContent(SectionHeading):
    pass


@schema("pages/packages", template="pages/packages.html")
class PackagesPage(Page):
    config: PackagesConfig
    catalog: PackageCatalogContent
