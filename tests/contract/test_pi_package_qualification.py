import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "apps" / "personal_intelligence_kernel"
BASELINE_PATH = ROOT / "governance" / "manifests" / "ai" / "pi-package-baseline.json"


def load():
    return json.loads((APP / "package.json").read_text()), json.loads((APP / "package-lock.json").read_text()), json.loads(BASELINE_PATH.read_text())


def assert_contract(package, lock, baseline):
    assert baseline["schema"] == "pi-package-baseline-v1"
    assert baseline["candidate"]["status"] in baseline["allowed_statuses"]
    assert package["name"] == baseline["candidate"]["name"]
    assert package["engines"]["node"] == ">=22.19.0"
    assert set(package["dependencies"]) == {entry["name"] for entry in baseline["packages"]}
    for entry in baseline["packages"]:
        assert package["dependencies"][entry["name"]] == entry["version"]
        assert re.fullmatch(r"\d+\.\d+\.\d+", package["dependencies"][entry["name"]])
        node = lock["packages"][f"node_modules/{entry['name']}"]
        assert node["version"] == entry["version"]
        assert node["integrity"].startswith("sha512-")
        assert node["resolved"].startswith("https://registry.npmjs.org/")
        assert node["integrity"] == entry["integrity"]
    assert package["overrides"] == baseline["overrides"]
    assert package["scripts"]["qualify"].endswith("--check")
    assert baseline["install_scripts"]["policy"] == "ignore-scripts"


def test_pi_package_baseline_contract():
    package, lock, baseline = load()
    assert_contract(package, lock, baseline)


def test_rejects_range_dependency():
    package, lock, baseline = load()
    package["dependencies"]["@earendil-works/pi-ai"] = "^0.83.0"
    assert not re.fullmatch(r"\d+\.\d+\.\d+", package["dependencies"]["@earendil-works/pi-ai"])


def test_rejects_missing_integrity():
    package, lock, baseline = load()
    del lock["packages"]["node_modules/@earendil-works/pi-ai"]["integrity"]
    assert "integrity" not in lock["packages"]["node_modules/@earendil-works/pi-ai"]


def test_rejects_version_drift():
    package, lock, baseline = load()
    lock["packages"]["node_modules/@earendil-works/pi-ai"]["version"] = "0.82.1"
    assert lock["packages"]["node_modules/@earendil-works/pi-ai"]["version"] != baseline["packages"][0]["version"]


def test_rejects_non_npm_host():
    package, lock, baseline = load()
    lock["packages"]["node_modules/@earendil-works/pi-ai"]["resolved"] = "https://evil.example/pi-ai.tgz"
    assert not lock["packages"]["node_modules/@earendil-works/pi-ai"]["resolved"].startswith("https://registry.npmjs.org/")


def test_rejects_unknown_install_script():
    package, lock, baseline = load()
    lock["packages"]["node_modules/unknown-script"] = {"version": "1.0.0", "hasInstallScript": True}
    known = {(item["name"], item["version"]) for item in baseline["install_scripts"]["known_ignored_packages"]}
    assert ("unknown-script", "1.0.0") not in known


def test_rejects_status_outside_contract():
    package, lock, baseline = load()
    baseline["candidate"]["status"] = "approved"
    assert baseline["candidate"]["status"] not in baseline["allowed_statuses"]
