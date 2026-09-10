import { describe, expect, it } from "vitest";

import {
  consumerReference,
  packageVersions,
  upstreamVersion,
} from "../src/directory/packages/references";

describe("package consumer declarations", () => {
  it("generates manager-specific references", () => {
    expect(
      consumerReference({ name: "fmt", registry: "conan" }, "11.0.2"),
    ).toBe("[requires]\nfmt/11.0.2");
    expect(
      consumerReference({ name: "fmt", registry: "bazel" }, "11.0.2"),
    ).toBe('bazel_dep(name = "fmt", version = "11.0.2")');
  });

  it("normalizes releases and keeps the default version first", () => {
    const releases = packageVersions(
      {
        "2.0#1": { upstream_version: "2.0" },
        "1.0": ["sha256:abc"],
      },
      "1.0",
    );
    expect(releases.map(({ version }) => version)).toEqual(["1.0", "2.0#1"]);
    expect(releases[0].checksums).toEqual(["sha256:abc"]);
    expect(upstreamVersion(releases[1])).toBe("2.0");
  });

  it("expands grouped release metadata without overriding release values", () => {
    const releases = packageVersions(
      {
        "2.0": { lifecycle: "active" },
        "1.0": {},
      },
      "",
      [{ releases: ["1.0", "2.0"], lifecycle: "deprecated" }],
    );
    expect(releases.find(({ version }) => version === "1.0")?.lifecycle).toBe(
      "deprecated",
    );
    expect(releases.find(({ version }) => version === "2.0")?.lifecycle).toBe(
      "active",
    );
  });
});
