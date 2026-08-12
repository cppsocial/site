.PHONY: help install dev build schemas blogs books communities events packages package-ingest package-publish package-conan package-meson package-spack package-vcpkg package-matches youtube serve clean lint test

help:
	@echo "C++ Social - Development Commands"
	@echo ""
	@echo "Available targets:"
	@echo "  make install     - Install the updater and generator"
	@echo "  make build       - Build the site"
	@echo "  make dev         - Watch, rebuild, and serve the site"
	@echo "  make schemas     - Generate JSON Schemas"
	@echo "  make blogs       - Refresh blog metadata and posts"
	@echo "  make books       - Refresh book metadata"
	@echo "  make communities - Refresh community metadata"
	@echo "  make events      - Refresh public event imports"
	@echo "  make packages    - Refresh the package catalog"
	@echo "  make package-ingest  - Refresh manager catalogs without publishing"
	@echo "  make package-publish - Publish from saved manager catalogs"
	@echo "  make package-conan   - Refresh the Conan catalog"
	@echo "  make package-meson   - Refresh the Meson catalog"
	@echo "  make package-spack   - Refresh the Spack catalog"
	@echo "  make package-vcpkg   - Refresh the vcpkg catalog"
	@echo "  make package-matches - Recalculate package matches"
	@echo "  make youtube     - Refresh YouTube metadata and videos"
	@echo "  make serve       - Build and serve the site"
	@echo "  make clean       - Clean build artifacts"
	@echo "  make lint        - Run static checks"
	@echo "  make test        - Run unit tests"

install:
	python3 -m pip install -e ./tools/meta-updater
	python3 -m pip install git+https://github.com/cppsocial/site-generator.git@master

dev:
	site-generator develop

build:
	site-generator build

schemas:
	site-generator schemas

blogs:
	meta-updater blogs all

books:
	meta-updater books

communities:
	meta-updater communities

events:
	meta-updater events

packages:
	meta-updater packages --refresh

package-ingest:
	meta-updater packages --refresh ingest

package-publish:
	meta-updater packages publish

package-conan:
	meta-updater packages --manager conan

package-meson:
	meta-updater packages --manager meson

package-spack:
	meta-updater packages --manager spack

package-vcpkg:
	meta-updater packages --manager vcpkg

package-matches:
	meta-updater packages matches

youtube:
	meta-updater youtube all

update-all: blogs books communities events packages youtube

serve: build
	python3 -m http.server --directory build 1313

clean:
	rm -rf build

lint:
	python3 -m compileall -q updater/src schemas

test:
	PYTHONPATH=updater/src python3 -m unittest discover -s tools/meta-updater/tests -v
