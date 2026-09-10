type PackageManager =
  | "bazel"
  | "conan"
  | "cppget"
  | "hunter"
  | "meson"
  | "spack"
  | "vcpkg"
  | "xmake";

export type PackageVariant = { name: string; registry: PackageManager };

export type PackageRelease = {
  version: string;
  upstream_version?: string;
  checksums?: string[];
  artifacts?: Array<{
    checksums?: string[];
    filename?: string;
    kind?: string;
    url?: string;
  }>;
  capabilities?: string[];
  channel?: string;
  compatibility?: string[];
  dependencies?: Array<{
    condition?: string;
    constraint?: string;
    kind?: string;
    name: string;
  }>;
  description?: string;
  documentation_url?: string;
  features?: Array<{
    condition?: string;
    default?: string;
    description?: string;
    name: string;
    values?: string[];
  }>;
  homepage?: string;
  lifecycle?: string;
  lifecycle_reason?: string;
  licenses?: string[];
  packaging_revision?: string;
  preferred?: boolean;
  recipe_revision?: string;
  recipe_url?: string;
  repository_url?: string;
  summary?: string;
  [key: string]: unknown;
};

export type PackageReleaseMetadata = Omit<PackageRelease, "version"> & {
  releases: string[];
};

type VersionMetadata = Omit<PackageRelease, "version"> | string[];

const versionCollator = new Intl.Collator("en", {
  numeric: true,
  sensitivity: "base",
});

export function upstreamVersion(release?: PackageRelease): string {
  return (
    release?.upstream_version ?? release?.version?.split(/[#@]/, 1)[0] ?? ""
  );
}

export function packageVersions(
  versions: Record<string, VersionMetadata> | undefined,
  defaultVersion = "",
  groupedMetadata: PackageReleaseMetadata[] = [],
): PackageRelease[] {
  return Object.entries(versions ?? {})
    .map(([version, metadata]) => {
      const inherited = Object.assign(
        {},
        ...groupedMetadata
          .filter((group) => group.releases.includes(version))
          .map(({ releases, ...values }) => {
            void releases;
            return values;
          }),
      );
      return {
        version,
        ...inherited,
        ...(Array.isArray(metadata) ? { checksums: metadata } : metadata),
      };
    })
    .sort((left, right) => {
      const leftDefault = upstreamVersion(left) === defaultVersion;
      const rightDefault = upstreamVersion(right) === defaultVersion;
      if (leftDefault !== rightDefault) return leftDefault ? -1 : 1;
      return versionCollator.compare(right.version, left.version);
    });
}

export function consumerReference(
  variant: PackageVariant,
  version = "",
): string {
  const { name, registry } = variant;
  if (registry === "conan")
    return `[requires]\n${name}${version ? `/${version}` : ""}`;
  if (registry === "vcpkg") return `"${name}"`;
  if (registry === "spack")
    return `spack:\n  specs:\n  - ${name}${version ? `@${version}` : ""}`;
  if (registry === "meson") return `subproject('${name}')`;
  if (registry === "bazel")
    return `bazel_dep(name = "${name}"${version ? `, version = "${version}"` : ""})`;
  if (registry === "cppget")
    return `depends: ${name}${version ? ` ^${version}` : ""}`;
  if (registry === "hunter") return `hunter_add_package(${name})`;
  return `add_requires("${name}${version ? ` ${version}` : ""}")`;
}

export function consumerFile(
  registry: PackageManager,
  fallback: string,
): string {
  return (
    {
      bazel: "MODULE.bazel",
      conan: "conanfile.txt",
      cppget: "manifest",
      hunter: "CMakeLists.txt",
      meson: "meson.build",
      spack: "spack.yaml",
      vcpkg: "vcpkg.json",
      xmake: "xmake.lua",
    }[registry] ?? fallback
  );
}
