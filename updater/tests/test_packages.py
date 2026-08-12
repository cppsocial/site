import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml
from schemas.packages import RegistryPackage

from meta_updater.commands.packages import (
    apply_corrections,
    browser_records,
    browser_versions,
    compact_release_metadata,
    without_empty,
)
from meta_updater.packages import (
    amalgamate,
    compare_packages,
    parse_conan,
    parse_meson,
    parse_spack,
    parse_vcpkg,
)
from meta_updater.packages.common import normalize_package_record, version_identity


class PackageParserTests(unittest.TestCase):
    def test_version_identity_preserves_manager_release_spelling(self) -> None:
        self.assertEqual(version_identity("xmake", "v2.2.1"), ("2.2.1", ""))
        self.assertEqual(version_identity("cppget", "2.2.1+1"), ("2.2.1", "1"))
        self.assertEqual(
            version_identity("hunter", "2.2.1-hunter-4"),
            ("2.2.1", "hunter-4"),
        )

    def test_inferred_version_identity_is_optional_metadata(self) -> None:
        package = normalize_package_record({
            "id": "cppget:example",
            "registry": "cppget",
            "name": "example",
            "versions": [
                {"version": "2.2.1+1"},
                {"version": "2.2.1+2"},
            ],
        })
        self.assertEqual(
            package["versions"],
            [
                {
                    "version": "2.2.1+1",
                    "upstream_version": "2.2.1",
                    "packaging_revision": "1",
                },
                {
                    "version": "2.2.1+2",
                    "upstream_version": "2.2.1",
                    "packaging_revision": "2",
                },
            ],
        )

    def test_browser_version_does_not_duplicate_embedded_revision(self) -> None:
        self.assertEqual(
            browser_versions([{
                "version": "2.2.1+1",
                "upstream_version": "2.2.1",
                "packaging_revision": "1",
            }]),
            {"2.2.1+1": {"upstream_version": "2.2.1", "packaging_revision": "1"}},
        )

    def test_browser_versions_are_keyed_objects(self) -> None:
        self.assertEqual(
            browser_versions(
                [
                    {"version": "1.0", "checksums": ["sha256:abc"]},
                    {"version": "2.0", "checksums": []},
                    {"version": "3.0", "source_urls": ["source"]},
                ]
            ),
            {
                "1.0": ["sha256:abc"],
                "2.0": {},
                "3.0": {"source_urls": ["source"]},
            },
        )

    def test_browser_versions_excerpt_repeated_release_descriptions(self) -> None:
        versions = browser_versions(
            [
                {
                    "version": "1.0",
                    "description": "<p>First.</p><p>Second.</p><p>Third.</p>",
                }
            ]
        )
        self.assertEqual(
            versions["1.0"]["description"],
            "<p>First.</p><p>Second.</p>",
        )

    def test_release_metadata_is_inherited_and_grouped(self) -> None:
        versions, groups = compact_release_metadata(
            {
                "1.0": {"description": "Current", "channel": "stable"},
                "2.0": {"description": "Historical", "channel": "stable"},
                "2.1": {"description": "Historical", "channel": "testing"},
                "3.0": {"description": "Unique"},
            },
            {"description": "Current"},
        )
        self.assertNotIn("description", versions["1.0"])
        self.assertNotIn("description", versions["2.0"])
        self.assertNotIn("description", versions["2.1"])
        self.assertEqual(versions["3.0"]["description"], "Unique")
        self.assertEqual(
            groups,
            [{"releases": ["2.0", "2.1"], "description": "Historical"}],
        )

    def test_browser_records_omit_empty_values(self) -> None:
        self.assertEqual(
            without_empty(
                {
                    "empty": "",
                    "items": [],
                    "mapping": {},
                    "flag": False,
                    "count": 0,
                    "value": "kept",
                }
            ),
            {"count": 0, "value": "kept"},
        )

    def test_corrections_are_scoped_to_variant_and_release(self) -> None:
        catalogs = {
            "vcpkg": [
                {
                    "id": "vcpkg:fmt",
                    "versions": [{"version": "1.0", "licenses": ["Old"]}],
                }
            ]
        }
        apply_corrections(
            catalogs,
            [
                {
                    "package": "vcpkg:fmt",
                    "version": "1.0",
                    "field": "licenses",
                    "operation": "replace",
                    "value": ["MIT"],
                }
            ],
        )
        self.assertEqual(catalogs["vcpkg"][0]["versions"][0]["licenses"], ["MIT"])

    def test_optional_schema_fields_are_omitted(self) -> None:
        package = RegistryPackage.model_validate(
            {"id": "meson:foo", "registry": "meson", "name": "foo"}
        )
        self.assertEqual(
            package.model_dump(exclude_none=True, exclude_defaults=True),
            {"id": "meson:foo", "registry": "meson", "name": "foo"},
        )

    def test_vcpkg_manifest_and_history(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            port = root / "ports" / "zlib-ng"
            port.mkdir(parents=True)
            (port / "vcpkg.json").write_text(
                json.dumps(
                    {
                        "name": "zlib-ng",
                        "version": "2.3.3",
                        "description": "Compression",
                        "license": "Zlib",
                        "homepage": "https://github.com/zlib-ng/zlib-ng",
                        "dependencies": ["cmake"],
                        "default-features": ["compat"],
                        "features": {"compat": {"description": "zlib API"}},
                    }
                )
            )
            (port / "portfile.cmake").write_text(
                "vcpkg_from_github(REPO zlib-ng/zlib-ng REF 2.3.3 "
                f"SHA512 {'a' * 128})\n"
                "vcpkg_download_distfile(PATCH URLS "
                "https://github.com/unrelated/tools/archive/1.0.tar.gz "
                "FILENAME tool.tar.gz SHA512 deadbeef)\n"
            )
            history = root / "versions" / "z-" / "zlib-ng.json"
            history.parent.mkdir(parents=True)
            history.write_text(
                json.dumps({"versions": [{"version": "2.3.3", "port-version": 1}]})
            )
            package = parse_vcpkg(root)[0]
            self.assertEqual(
                package["versions"][0]["artifacts"][0]["checksums"],
                [f"sha512:{'a' * 128}"],
            )
            self.assertEqual(
                package["repository_url"], "https://github.com/zlib-ng/zlib-ng"
            )
            self.assertNotIn("source_urls", package)
            self.assertEqual(package["options"], ["compat"])
            self.assertEqual(package["default_options"], {"compat": "enabled"})
            RegistryPackage.model_validate(package)

    @patch("meta_updater.packages.conan.shutil.which", return_value=None)
    def test_conan_static_fallback(self, _which) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            recipe = root / "recipes" / "zlib-ng"
            folder = recipe / "all"
            folder.mkdir(parents=True)
            (recipe / "config.yml").write_text(
                yaml.safe_dump({"versions": {"2.3.3": {"folder": "all"}}})
            )
            (folder / "conanfile.py").write_text(
                "class ZlibNgConan:\n"
                "    name = 'zlib-ng'\n"
                "    description = 'Compression'\n"
                "    license = 'Zlib'\n"
                "    homepage = 'https://github.com/zlib-ng/zlib-ng'\n"
                "    def requirements(self):\n"
                "        self.requires('zlib/1.3.1')\n"
                "        self.tool_requires('cmake/[>=3.20]')\n"
            )
            (folder / "conandata.yml").write_text(
                yaml.safe_dump(
                    {
                        "sources": {
                            "2.3.3": {
                                "url": "https://github.com/zlib-ng/zlib-ng/archive/2.3.3.tar.gz",
                                "sha256": "ABCDEF",
                            }
                        }
                    }
                )
            )
            package = parse_conan(root)[0]
            self.assertEqual(package["versions"][0]["version"], "2.3.3")
            self.assertEqual(
                package["versions"][0]["artifacts"][0],
                {
                    "kind": "upstream_source",
                    "url": "https://github.com/zlib-ng/zlib-ng/archive/2.3.3.tar.gz",
                    "checksums": ["sha256:abcdef"],
                },
            )
            self.assertEqual(package["dependencies"], ["zlib", "cmake"])
            RegistryPackage.model_validate(package)

    def test_spack_and_meson(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            spack_recipe = root / "repos/spack_repo/builtin/packages/zlib_ng/package.py"
            spack_recipe.parent.mkdir(parents=True)
            spack_recipe.write_text(
                "class ZlibNgPackage:\n"
                "    '''Compression library.'''\n"
                "    homepage = 'https://github.com/zlib-ng/zlib-ng'\n"
                "    git = 'https://github.com/zlib-ng/zlib-ng.git'\n"
                "    license('Zlib')\n"
                "    version('2.3.3', sha256='ABCDEF')\n"
                "    depends_on('cmake@3:')\n"
            )
            spack = parse_spack(root)[0]
            self.assertEqual(spack["name"], "zlib-ng")
            self.assertEqual(spack["dependencies"], ["cmake"])
            self.assertEqual(
                spack["versions"][0]["artifacts"][0]["checksums"],
                ["sha256:abcdef"],
            )
            wrap = root / "subprojects/zlib-ng.wrap"
            wrap.parent.mkdir()
            wrap.write_text(
                "[wrap-file]\n"
                "directory = zlib-ng-2.3.3\n"
                "source_url = https://github.com/zlib-ng/zlib-ng/archive/2.3.3.tar.gz\n"
                "source_hash = ABCDEF\n"
            )
            meson = parse_meson(root)[0]
            self.assertEqual(meson["versions"][0]["version"], "2.3.3")
            self.assertEqual(
                meson["versions"][0]["artifacts"][0]["checksums"],
                ["sha256:abcdef"],
            )

    def test_spack_decodes_leading_underscore(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for encoded in ("_3dtk", "_3proxy", "_4ti2"):
                recipe = (
                    root / f"repos/spack_repo/builtin/packages/{encoded}/package.py"
                )
                recipe.parent.mkdir(parents=True)
                recipe.write_text("class Package:\n    pass\n")

            names = [package["name"] for package in parse_spack(root)]
            self.assertEqual(names, ["3dtk", "3proxy", "4ti2"])


class PackageMatchingTests(unittest.TestCase):
    def package(self, registry: str, name: str, repository: str) -> dict:
        return {
            "id": f"{registry}:{name}",
            "registry": registry,
            "name": name,
            "repository_url": repository,
            "recipe_url": repository,
        }

    def test_name_and_repository_merge(self) -> None:
        left = self.package("conan", "zlib-ng", "https://github.com/zlib-ng/zlib-ng")
        right = self.package("vcpkg", "zlib-ng", "https://github.com/zlib-ng/zlib-ng")
        match = compare_packages(left, right)
        self.assertIsNotNone(match)
        self.assertGreaterEqual(match["confidence"], 0.82)

    def test_dependency_name_is_omitted_when_it_matches_master_id(self) -> None:
        dependency = self.package("conan", "zlib", "")
        consumer = self.package("conan", "app", "")
        consumer["dependencies"] = ["zlib"]
        catalogs = {"conan": [consumer, dependency]}
        master, _ = amalgamate(catalogs)
        _, details = browser_records(master, catalogs)
        app = next(item for item in details if item["id"] == "conan:app")
        self.assertEqual(app["dependency_links"], [{"id": "zlib"}])

    def test_browser_details_excerpt_description_without_mutating_catalog(self) -> None:
        package = self.package("conan", "verbose", "")
        package["description"] = (
            "<p>First paragraph.</p><p>Second paragraph.</p>"
            "<p>Third paragraph that should stay only in the catalog.</p>"
        )
        catalogs = {"conan": [package]}
        master, _ = amalgamate(catalogs)
        _, details = browser_records(master, catalogs)
        self.assertEqual(
            details[0]["description"],
            "<p>First paragraph.</p><p>Second paragraph.</p>",
        )
        self.assertIn("Third paragraph", package["description"])

    def test_global_fields_are_ranked_without_unioning_licenses(self) -> None:
        conan = self.package("conan", "fmt", "")
        conan.update({"summary": "Conan summary", "licenses": ["MIT"]})
        vcpkg = self.package("vcpkg", "fmt", "")
        vcpkg.update({"summary": "vcpkg summary", "licenses": ["Apache-2.0"]})
        master, _ = amalgamate({"conan": [conan], "vcpkg": [vcpkg]})
        summaries, _ = browser_records(master, {"conan": [conan], "vcpkg": [vcpkg]})
        self.assertEqual(summaries[0]["content"], "vcpkg summary")
        self.assertEqual(summaries[0]["licenses"], ["Apache-2.0"])
        self.assertEqual(summaries[0]["field_sources"]["licenses"], "vcpkg:fmt")

    def test_field_preference_overrides_default_ranking(self) -> None:
        conan = self.package("conan", "fmt", "")
        conan["summary"] = "Preferred Conan summary"
        vcpkg = self.package("vcpkg", "fmt", "")
        vcpkg["summary"] = "Default vcpkg summary"
        master, _ = amalgamate({"conan": [conan], "vcpkg": [vcpkg]})
        summaries, _ = browser_records(
            master,
            {"conan": [conan], "vcpkg": [vcpkg]},
            [
                {
                    "package": "fmt",
                    "field": "summary",
                    "source": "conan:fmt",
                }
            ],
        )
        self.assertEqual(summaries[0]["content"], "Preferred Conan summary")
        self.assertEqual(summaries[0]["summary_source"], "conan:fmt")

    def test_upstream_repository_is_certain(self) -> None:
        left = self.package("conan", "llvm", "https://github.com/llvm/llvm-project")
        right = self.package("vcpkg", "clang", "https://github.com/llvm/llvm-project")
        match = compare_packages(left, right)
        self.assertIsNotNone(match)
        self.assertEqual(match["confidence"], 1.0)

    def test_exact_source_archive_is_certain(self) -> None:
        left = self.package("conan", "foo", "https://example.test/one")
        right = self.package("vcpkg", "bar", "https://example.test/two")
        source = "https://downloads.example.test/project-1.0.tar.gz"
        for package in (left, right):
            package["versions"] = [
                {
                    "version": "1.0",
                    "artifacts": [{"kind": "upstream_source", "url": source}],
                }
            ]
        match = compare_packages(left, right)
        self.assertIsNotNone(match)
        self.assertEqual(match["confidence"], 1.0)

    def test_exact_source_checksum_is_certain_when_rehosted(self) -> None:
        left = self.package("conan", "foo", "https://example.test/one")
        right = self.package("vcpkg", "bar", "https://example.test/two")
        checksum = "sha256:abcdef"
        left["versions"] = [
            {
                "version": "1.0",
                "artifacts": [
                    {"kind": "upstream_source", "checksums": [checksum]}
                ],
            }
        ]
        right["versions"] = [
            {
                "version": "2024",
                "artifacts": [
                    {"kind": "upstream_source", "checksums": [checksum]}
                ],
            }
        ]
        match = compare_packages(left, right)
        self.assertIsNotNone(match)
        self.assertEqual(match["confidence"], 1.0)
        self.assertIn(
            "same distributed source checksum",
            {item["signal"] for item in match["evidence"]},
        )

    def test_typed_upstream_artifacts_are_match_evidence(self) -> None:
        left = self.package("conan", "foo", "")
        right = self.package("xmake", "bar", "")
        for package in (left, right):
            package["versions"] = [
                {
                    "version": "1.0",
                    "artifacts": [
                        {
                            "kind": "upstream_source",
                            "url": "https://example.test/foo-1.0.tar.gz",
                            "checksums": ["sha256:abc"],
                        }
                    ],
                }
            ]
        self.assertEqual(compare_packages(left, right)["confidence"], 1.0)

    def test_registry_package_hash_does_not_identify_upstream(self) -> None:
        left = self.package("cppget", "foo", "")
        right = self.package("conan", "bar", "")
        for package in (left, right):
            package["versions"] = [
                {
                    "version": "1.0",
                    "artifacts": [
                        {
                            "kind": "registry_package",
                            "checksums": ["sha256:abc"],
                        }
                    ],
                }
            ]
        self.assertIsNone(compare_packages(left, right))

    def test_author_corroborates_name(self) -> None:
        left = self.package("conan", "foo", "https://example.test/one")
        right = self.package("vcpkg", "libfoo", "https://example.test/two")
        left["authors"] = ["A. Developer"]
        right["authors"] = ["A. Developer"]
        match = compare_packages(left, right)
        self.assertIsNotNone(match)
        self.assertGreaterEqual(match["confidence"], 0.82)

    def test_exact_name_is_strong_without_other_metadata(self) -> None:
        left = self.package("conan", "asio", "")
        right = self.package("meson", "asio", "")
        match = compare_packages(left, right)
        self.assertIsNotNone(match)
        self.assertEqual(match["confidence"], 0.95)

    def test_conflicting_descriptions_do_not_overturn_exact_name(self) -> None:
        left = self.package("conan", "units", "")
        right = self.package("spack", "units", "")
        left["description"] = "Header-only C++ dimensional analysis library"
        right["description"] = "Command line conversion between measurement units"
        match = compare_packages(left, right)
        self.assertIsNotNone(match)
        self.assertGreaterEqual(match["confidence"], 0.82)

    def test_conflicting_licenses_are_stronger_than_descriptions(self) -> None:
        left = self.package("conan", "units", "")
        right = self.package("spack", "units", "")
        left["licenses"] = ["MIT"]
        right["licenses"] = ["GPL-3.0-only"]
        match = compare_packages(left, right)
        self.assertIsNotNone(match)
        self.assertEqual(match["confidence"], 0.836)
        self.assertIn(
            "conflicting licenses",
            {item["signal"] for item in match["evidence"]},
        )

    def test_missing_license_is_neutral(self) -> None:
        left = self.package("conan", "asio", "")
        right = self.package("meson", "asio", "")
        left["licenses"] = ["BSL-1.0"]
        match = compare_packages(left, right)
        self.assertIsNotNone(match)
        self.assertEqual(match["confidence"], 0.95)
        self.assertNotIn(
            "conflicting licenses",
            {item["signal"] for item in match["evidence"]},
        )

    def test_missing_comparison_metadata_is_neutral(self) -> None:
        left = self.package("conan", "asio", "")
        right = self.package("spack", "asio", "")
        left.update(
            {
                "licenses": ["BSL-1.0"],
                "description": "Portable asynchronous I/O",
                "package_type": "library",
            }
        )
        right["licenses"] = ["NOASSERTION"]
        match = compare_packages(left, right)
        self.assertIsNotNone(match)
        self.assertEqual(match["confidence"], 0.95)
        self.assertFalse(any(item["weight"] < 0 for item in match["evidence"]))

    def test_substantially_different_names_are_negative_evidence(self) -> None:
        left = self.package("conan", "foo", "")
        right = self.package("spack", "bar", "")
        left["authors"] = ["A. Developer"]
        right["authors"] = ["A. Developer"]
        match = compare_packages(left, right)
        self.assertIsNotNone(match)
        self.assertLess(match["confidence"], 0.82)
        self.assertIn(
            "substantially different names",
            {item["signal"] for item in match["evidence"]},
        )

    def test_repeated_homepage_is_not_match_evidence(self) -> None:
        left = self.package("conan", "qt", "")
        right = self.package("vcpkg", "qtmultimedia", "")
        left["homepage"] = right["homepage"] = "https://www.qt.io"
        counts = {"www.qt.io": {"conan": 1, "vcpkg": 49}}
        self.assertIsNone(compare_packages(left, right, counts))

    def test_exact_name_precedes_repository_only_cluster_edge(self) -> None:
        repository = "https://github.com/example/monorepo"
        conan = self.package("conan", "faiss", repository)
        exact = self.package("vcpkg", "faiss", repository)
        component = self.package("vcpkg", "cuda-samples", repository)
        master, matches = amalgamate(
            {
                "conan": [conan],
                "vcpkg": [component, exact],
            }
        )
        faiss = next(item for item in master if item["name"] == "faiss")
        self.assertEqual(
            {item["package_id"] for item in faiss["packages"]},
            {"conan:faiss", "vcpkg:faiss"},
        )
        decisions = {
            (item["left"], item["right"]): item["decision"] for item in matches
        }
        self.assertEqual(
            decisions[("conan:faiss", "vcpkg:cuda-samples")],
            "conflict",
        )

    def test_exact_name_precedes_shared_component_archive(self) -> None:
        checksum = "sha256:abcdef"
        conan_zlib = self.package("conan", "zlib", "")
        conan_minizip = self.package("conan", "minizip", "")
        spack_zlib = self.package("spack", "zlib", "")
        spack_minizip = self.package("spack", "minizip", "")
        conan_zlib["description"] = spack_zlib["description"] = "Compression library"
        conan_minizip["description"] = spack_minizip["description"] = "ZIP file tools"
        for package in (conan_zlib, conan_minizip, spack_zlib, spack_minizip):
            package["versions"] = [
                {
                    "version": "1.0",
                    "artifacts": [
                        {"kind": "upstream_source", "checksums": [checksum]}
                    ],
                }
            ]
        master, _ = amalgamate(
            {
                "conan": [conan_zlib, conan_minizip],
                "spack": [spack_zlib, spack_minizip],
            }
        )
        groups = {
            package["name"]: {item["package_id"] for item in package["packages"]}
            for package in master
        }
        self.assertEqual(groups["zlib"], {"conan:zlib", "spack:zlib"})
        self.assertEqual(groups["minizip"], {"conan:minizip", "spack:minizip"})

    def test_same_manager_redistribution_aliases_share_master_package(self) -> None:
        repository = "https://github.com/nlohmann/json"
        description = "JSON for Modern C++ parser and generator."
        packages = [
            self.package("conan", "nlohmann_json", repository),
            self.package("conan", "jsonformoderncpp", repository),
            self.package("meson", "nlohmann_json", repository),
            self.package("meson", "json", repository),
        ]
        for package in packages:
            package["description"] = description
        master, matches = amalgamate(
            {
                "conan": packages[:2],
                "meson": packages[2:],
            }
        )
        self.assertEqual(len(master), 1)
        self.assertEqual(master[0]["id"], "nlohmann-json")
        self.assertEqual(
            {item["package_id"] for item in master[0]["packages"]},
            {package["id"] for package in packages},
        )
        self.assertIn("merge", {item["decision"] for item in matches})

    def test_master_is_minimal_and_keeps_aliases(self) -> None:
        left = self.package("conan", "zlib-ng", "https://github.com/zlib-ng/zlib-ng")
        right = self.package(
            "spack", "libzlib-ng", "https://github.com/zlib-ng/zlib-ng"
        )
        master, matches = amalgamate({"conan": [left], "spack": [right]})
        self.assertEqual(len(master), 1)
        self.assertEqual(master[0]["id"], "zlib-ng")
        self.assertEqual(master[0]["aliases"], ["libzlib-ng"])
        self.assertEqual(matches[0]["decision"], "merge")

    def test_manual_group_override_sets_name_and_forces_aliases(self) -> None:
        left = self.package("conan", "old-name", "https://example.test/one")
        right = self.package("conan", "new-name", "https://example.test/two")
        automatic = self.package("spack", "old-name", "https://example.test/one")
        master, matches = amalgamate(
            {"conan": [left, right], "spack": [automatic]},
            overrides=[
                {
                    "name": "canonical-name",
                    "aliases": ["historic-name"],
                    "packages": [left["id"], right["id"]],
                }
            ],
        )
        self.assertEqual(len(master), 1)
        overridden = next(
            package for package in master if package["name"] == "canonical-name"
        )
        self.assertEqual(
            overridden["aliases"], ["historic-name", "new-name", "old-name"]
        )
        self.assertEqual(
            {item["decision"] for item in matches}, {"manual_merge", "merge"}
        )

    def test_never_merge_assertion_blocks_automatic_match(self) -> None:
        left = self.package("conan", "units", "")
        right = self.package("spack", "units", "")
        master, matches = amalgamate(
            {"conan": [left], "spack": [right]},
            overrides={
                "never_merge": [
                    {"packages": [left["id"], right["id"]], "reason": "homonyms"}
                ]
            },
        )
        self.assertEqual(len(master), 2)
        self.assertEqual(matches[0]["decision"], "conflict")

    def test_previous_entity_id_survives_added_variant(self) -> None:
        conan = self.package("conan", "fmt", "")
        vcpkg = self.package("vcpkg", "fmt", "")
        master, _ = amalgamate(
            {"conan": [conan], "vcpkg": [vcpkg]},
            previous_entities=[{"id": "fmt-library", "packages": [conan["id"]]}],
        )
        self.assertEqual(master[0]["id"], "fmt-library")

    def test_matching_is_independent_of_catalog_order(self) -> None:
        conan = self.package("conan", "fmt", "https://github.com/fmtlib/fmt")
        vcpkg = self.package("vcpkg", "fmt", "https://github.com/fmtlib/fmt")
        spack = self.package("spack", "libfmt", "https://github.com/fmtlib/fmt")
        forward = {"conan": [conan], "vcpkg": [vcpkg], "spack": [spack]}
        reverse = {"spack": [spack], "vcpkg": [vcpkg], "conan": [conan]}
        self.assertEqual(amalgamate(forward), amalgamate(reverse))

    def test_optional_override_member_may_be_absent(self) -> None:
        left = self.package("conan", "fmt", "")
        right = self.package("vcpkg", "fmt", "")
        master, _ = amalgamate(
            {"conan": [left], "vcpkg": [right]},
            overrides={
                "groups": [
                    {
                        "id": "fmt",
                        "packages": [left["id"], right["id"]],
                        "optional_packages": ["hunter:fmt"],
                    }
                ]
            },
        )
        self.assertEqual(master[0]["id"], "fmt")


if __name__ == "__main__":
    unittest.main()
