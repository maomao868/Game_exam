"""Trusted adapter profile. Importable without simulator dependencies."""
from config_schema import validate_engine_versions
from contracts import Capabilities


SCHEMA_VERSION = "1.0.0"
BENCHMARK = "towermind"
FIELDS = {"level_id", "engine_versions", "engine_archive_sha256"}
METRICS = {"native_return"}
PROFILES = {"player-rgb-v1"}
REDUCERS = {("family_macro", "1.0.0")}
CAPABILITIES = Capabilities(images=True, action_mode="text", native_truncation=True).to_dict()
ARCHIVE_SHA256 = "153f363150f5e33f4827599498e2d7bda504045a4ae258e013bb504ea4273e19"
ENGINE_VERSIONS = {
    "mlagents-envs": "1.1.0",
    "gym": "0.26.2",
    "numpy": "1.23.5",
    "grpcio": "1.48.2",
    "protobuf": "3.20.3",
    "opencv-python-headless": "4.10.0.84",
}


def validate(value):
    validate_engine_versions(value["engine_versions"], ENGINE_VERSIONS)
    level = value["level_id"]
    if type(level) is not int or not 0 <= level <= 8 or value["env_id"] != f"TowerMind-Level-{level}":
        raise ValueError("unsupported native TowerMind level")
    if value["seed"] == 0:
        raise ValueError("TowerMind profile requires a positive seed")
    if value["engine_archive_sha256"] != ARCHIVE_SHA256:
        raise ValueError("unsupported native TowerMind archive")
    if value["capabilities"] != CAPABILITIES:
        raise ValueError("TowerMind requires the RGB action-stepped profile")
    if value["metric_spec"]["success_label"] != "native_level_completed":
        raise ValueError("unsupported TowerMind success label")
