"""Trusted development profile for the upstream two-chef environment."""
from config_schema import validate_engine_versions

SCHEMA_VERSION = "1.0.0"
BENCHMARK = "overcooked"
FIELDS = {"source_commit", "engine_versions", "horizon", "player_index", "partner"}
PROFILES = {"kitchen-rgb-v1"}
METRICS = {"native_return"}
REDUCERS = {("family_macro", "1.0.0")}
COMMIT = "739950a079cdaed5a44fcc662efc40244c205d06"
VERSIONS = {"overcooked-ai": "2.0.0", "numpy": "1.26.4", "scipy": "1.15.3", "pygame": "2.6.1"}
CAPABILITIES = {"images": True, "action_mode": "enum", "timing": "action-stepped", "native_truncation": True}


def validate(value):
    validate_engine_versions(value["engine_versions"], VERSIONS)
    if value["source_commit"] != COMMIT or value["env_id"] != "asymmetric_advantages":
        raise ValueError("unsupported Overcooked source or layout")
    if type(value["horizon"]) is not int or value["horizon"] != 400:
        raise ValueError("expected a 400-step native horizon")
    if type(value["player_index"]) is not int or value["player_index"] not in (0, 1):
        raise ValueError("expected player index 0 or 1")
    if value["partner"] != "GreedyHumanModel" or value["capabilities"] != CAPABILITIES:
        raise ValueError("unsupported Overcooked partner or capabilities")
    if value["metric_spec"]["success_label"] != "episode_completed":
        raise ValueError("unsupported Overcooked completion label")
