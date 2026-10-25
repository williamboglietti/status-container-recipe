SHELL := /bin/bash
IMAGE ?= status-container-recipe:local
# Empty selects the native Linux architecture in the Python launcher.
PLATFORM ?=
ADMIN_EMAIL ?= admin@example.com
export IMAGE PLATFORM ADMIN_EMAIL

.PHONY: build compose-build compose-up compose-down test test-unit test-image test-healthcheck \
	test-pgsql test-mysql test-mariadb test-compose lint update-dependencies

# Values are passed through the environment, never interpolated into shell text.
build compose-up compose-down test-image test-healthcheck test-pgsql test-mysql test-mariadb test-compose:
	python3 scripts/project.py $@

compose-build: build

test: test-unit test-image test-healthcheck test-pgsql test-mysql test-mariadb test-compose

test-unit:
	PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s test -p 'test_unit*.py'

lint:
	actionlint
	shellcheck docker/entrypoint.sh

update-dependencies:
	python3 scripts/resolve.py --refresh-dependencies
