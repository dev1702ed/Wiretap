"""The vendored OpenLineage schema is intact and matches what the bridge emits."""

import hashlib
import json
import pathlib

import jsonschema

from dcp_openlineage import OPENLINEAGE_SCHEMA_URL

SCHEMA = pathlib.Path(__file__).parents[1] / "schema" / "OpenLineage.json"
VENDORED_SHA256 = "69f68bee00b9beac88a87059c0102410e7bb05f3f43c46d02a0409831eceb0d2"


def test_vendored_schema_is_byte_for_byte_the_recorded_release():
    assert hashlib.sha256(SCHEMA.read_bytes()).hexdigest() == VENDORED_SHA256


def test_vendored_schema_is_a_valid_2020_12_schema():
    jsonschema.Draft202012Validator.check_schema(json.loads(SCHEMA.read_text()))


def test_emitted_schema_url_matches_the_vendored_version():
    assert json.loads(SCHEMA.read_text())["$id"] == OPENLINEAGE_SCHEMA_URL
