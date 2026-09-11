.PHONY: help install dev build frontend schemas blogs books communities events packages package-ingest package-publish package-conan package-meson package-spack package-vcpkg package-matches youtube serve clean format format-python format-templates format-makefile format-assets format-frontend format-yaml check-format check-format-python check-format-templates check-format-makefile check-format-assets check-format-frontend check-format-yaml lint lint-python lint-templates lint-makefile lint-frontend test test-frontend

ID_ARG = $(if $(ID),--id $(ID),)
PYTHON_PATHS = updater/src updater/tests schemas scripts site_plugins

help:
	@echo "C++ Social - Development Commands"
	@echo ""
	@echo "Available targets:"
	@echo "  make install     - Install the updater and generator"
	@echo "  make build       - Build the site"
	@echo "  make dev         - Watch, rebuild, and serve the site"
	@echo "  make schemas     - Generate JSON Schemas"
	@echo "  make update-all  - Update all metadata"
	@echo "  make blogs       - Refresh blog metadata and posts (optional ID=source-id)"
	@echo "  make books       - Refresh book metadata (optional ID=isbn)"
	@echo "  make communities - Refresh community metadata (optional ID=community-id)"
	@echo "  make events      - Refresh public event imports"
	@echo "  make packages    - Refresh the package catalog"
	@echo "  make package-ingest  - Refresh manager catalogs without publishing"
	@echo "  make package-publish - Publish from saved manager catalogs"
	@echo "  make package-conan   - Refresh the Conan catalog"
	@echo "  make package-meson   - Refresh the Meson catalog"
	@echo "  make package-spack   - Refresh the Spack catalog"
	@echo "  make package-vcpkg   - Refresh the vcpkg catalog"
	@echo "  make package-matches - Recalculate package matches"
	@echo "  make youtube     - Refresh YouTube metadata and videos (optional ID=channel-id)"
	@echo "  make serve       - Build and serve the site"
	@echo "  make clean       - Clean build artifacts"
	@echo "  make format      - Auto-format source files"
	@echo "  make check-format - Check formatting without changing files"
	@echo "  make lint        - Run source linters and validators"
	@echo "  make test        - Run unit tests"

install:
	python3 -m pip install -r requirements.txt
	python3 -m pip install -r requirements_dev.txt
	npm ci

dev:
	site-generator develop --host 0.0.0.0

build:
	site-generator build

frontend:
	npm run build:frontend -- --outdir=build

schemas:
	site-generator schemas

blogs:
	meta-updater blogs all $(ID_ARG)

books:
	meta-updater books $(ID_ARG)

communities:
	meta-updater communities $(ID_ARG)

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
	meta-updater youtube all $(ID_ARG)

update-all: blogs books communities events packages youtube

serve: build
	python3 -m http.server --directory build 1313

clean:
	rm -rf build

format-python:
	python3 -m autopep8 --in-place --recursive --max-line-length 88 $(PYTHON_PATHS)

check-format-python:
	@python3 -m autopep8 --diff --exit-code --recursive --max-line-length 88 $(PYTHON_PATHS) || { \
		status=$$?; \
		echo ""; \
		echo "Python formatting check failed. Apply the diff with: make format-python"; \
		exit $$status; \
		}

lint-python:
	python3 -m ruff check $(PYTHON_PATHS)
	python3 -m compileall -q $(PYTHON_PATHS)

test-python:
	PYTHONPATH=updater/src python3 -m unittest discover -s updater/tests -v
	python3 -m unittest discover -s scripts/tests -v

format-templates:
	@djlint --reformat --profile=jinja templates/ || test $$? -eq 1

check-format-templates:
	@djlint --check --profile=jinja templates/ || { \
		status=$$?; \
		echo "Template formatting check failed. Run: make format-templates"; \
		exit $$status; \
		}

lint-templates:
	djlint --lint --profile=jinja --ignore=H021 templates/

format-makefile:
	mbake format Makefile

check-format-makefile:
	@mbake format --check --diff Makefile || { \
		status=$$?; \
		echo "Makefile formatting check failed. Run: make format-makefile"; \
		exit $$status; \
		}

lint-makefile:
	mbake validate Makefile

format-assets:
	npm run format:assets

check-format-assets:
	npm run check:assets

format-yaml:
	npm run format:yaml

check-format-yaml:
	npm run check:yaml

format-frontend:
	npm run format:frontend

check-format-frontend:
	npm run check:frontend

lint-frontend:
	npm run lint:frontend
	npm run typecheck:frontend

test-frontend:
	npm run test:frontend

check-format: check-format-python check-format-templates check-format-makefile check-format-assets check-format-frontend check-format-yaml
format: format-python format-templates format-makefile format-assets format-frontend format-yaml
lint: lint-python lint-templates lint-makefile lint-frontend
test: test-python test-frontend