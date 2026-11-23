# This file is formatted with ruff format
#
# Validates the XDG tablet profile schema (xdg-tablet/profile.schema.json)
# and the example document against it, plus the semantic rules from
# xdg-tablet/profiles.md that JSON Schema cannot express.

import copy
import json
import os
import tomllib
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")


def source_root() -> Path:
    root = os.environ.get("MESON_SOURCE_ROOT")
    return Path(root) if root else Path(__file__).parent.parent


XDG_DIR = source_root() / "xdg-tablet"


@pytest.fixture(scope="module")
def schema():
    with open(XDG_DIR / "profile.schema.json") as f:
        s = json.load(f)
    jsonschema.Draft202012Validator.check_schema(s)
    return s


@pytest.fixture()
def example():
    with open(XDG_DIR / "example-profiles.toml", "rb") as f:
        return tomllib.load(f)


def semantic_errors(doc: dict) -> list[str]:
    """Checks from profiles.md that the JSON schema can't express."""
    errors = []
    menus = set(doc.get("radial-menu", {}))
    ids = [d["id"] for d in doc.get("device", [])]
    for dup in {i for i in ids if ids.count(i) > 1}:
        errors.append(f"duplicate device id {dup}")

    def check_range(where, r):
        if r is not None and not r[0] < r[1]:
            errors.append(f"{where}: range min must be < max")

    def check_action(where, action, local_menus):
        a = action["action"] if isinstance(action, dict) else action
        if a.startswith("radial-menu:") and a.split(":", 1)[1] not in local_menus:
            errors.append(f"{where}: unknown radial menu {a}")

    def walk_actions(where, table, local_menus):
        if isinstance(table, dict):
            for k, v in table.items():
                if isinstance(v, (str, dict)) and (isinstance(v, str) or "action" in v):
                    if k not in ("label", "name", "id", "app-id", "device", "icon"):
                        check_action(f"{where}.{k}", v, local_menus)
                else:
                    walk_actions(f"{where}.{k}", v, local_menus)
        elif isinstance(table, list):
            for i, v in enumerate(table):
                walk_actions(f"{where}[{i}]", v, local_menus)

    for d in doc.get("device", []):
        area = d.get("mapping", {}).get("area")
        if area is not None and not (area[0] < area[2] and area[1] < area[3]):
            errors.append(f"device {d['id']}: area needs x1 < x2 and y1 < y2")
        for t in d.get("tool", []):
            check_range(f"device {d['id']} tool", t.get("pressure-range"))
            check_range(f"device {d['id']} tool", t.get("eraser-pressure-range"))
        for key in ("tool", "pad"):
            walk_actions(f"device {d['id']}.{key}", d.get(key, {}), menus)

    for name, menu in doc.get("radial-menu", {}).items():
        walk_actions(f"radial-menu {name}", menu["items"], menus)

    for a in doc.get("app", []):
        dev = a.get("device", "*")
        if dev != "*" and dev not in ids:
            errors.append(f"app {a['app-id']}: unknown device {dev}")
        local = menus | set(a.get("radial-menu", {}))
        for key in ("tool", "pad"):
            walk_actions(f"app {a['app-id']}.{key}", a.get(key, {}), local)
        for t in a.get("tool", []):
            check_range(f"app {a['app-id']} tool", t.get("pressure-range"))
    return errors


def schema_errors(schema, doc) -> list[str]:
    v = jsonschema.Draft202012Validator(schema)
    return [f"{list(e.absolute_path)}: {e.message}" for e in v.iter_errors(doc)]


def test_example_is_valid(schema, example):
    assert schema_errors(schema, example) == []
    assert semantic_errors(example) == []


def test_minimal_document(schema):
    assert schema_errors(schema, {"schema-version": 1}) == []


def test_schema_version_required(schema):
    assert schema_errors(schema, {}) != []
    assert schema_errors(schema, {"schema-version": 2}) != []


def test_extension_keys_allowed_typos_rejected(schema, example):
    doc = copy.deepcopy(example)
    doc["device"][0]["x-org.example-flag"] = True
    assert schema_errors(schema, doc) == []
    doc["device"][0]["mapings"] = {}
    assert schema_errors(schema, doc) != []


@pytest.mark.parametrize(
    "curve",
    [
        [0.2, 0.1, 1.2, 0.9],  # x2 > 1
        [-0.1, 0.0, 1.0, 1.0],  # x1 < 0
        [0.2, 0.1, 0.9],  # too short
    ],
)
def test_bad_curve_point(schema, example, curve):
    doc = copy.deepcopy(example)
    doc["device"][0]["tool"][0]["pressure-curve"] = curve
    assert schema_errors(schema, doc) != []


@pytest.mark.parametrize(
    "action",
    [
        "exec:gimp",
        "launch-rocket",
        "button:middle-ish",
        "scroll:sideways",
        "radial-menu:Bad Name",
        "Ctrl+",
        "Ctrl++z",
    ],
)
def test_unknown_action(schema, example, action):
    doc = copy.deepcopy(example)
    doc["device"][1]["pad"]["buttons"]["B"] = action
    assert schema_errors(schema, doc) != [], action


@pytest.mark.parametrize(
    "action",
    [
        "none",
        "passthrough",
        "Ctrl+Shift+z",
        "keys:Ctrl+z",
        "F5",
        "Shift",
        "button:4",
        "scroll:left",
        "mode-set:2",
        "radial-menu:main",
    ],
)
def test_good_action(schema, example, action):
    doc = copy.deepcopy(example)
    doc["device"][1]["pad"]["buttons"]["B"] = action
    assert schema_errors(schema, doc) == [], action


@pytest.mark.parametrize(
    "match",
    [
        "usb:256c:006d",  # wrong separator
        "usb|256c|6d",  # short pid
        "pci|056a|0357",  # unknown bus
        "usb|056a|0357|name|uniq|extra",  # too many fields
    ],
)
def test_bad_match_string(schema, example, match):
    doc = copy.deepcopy(example)
    doc["device"][0]["match"] = [match]
    assert schema_errors(schema, doc) != [], match


def test_good_match_strings(schema, example):
    doc = copy.deepcopy(example)
    doc["device"][0]["match"] = [
        "usb|056a|0357",
        "bluetooth|056A|0360",
        "usb|256c|006d||HUION_T21j",
        "i2c|04f3|2d6f|ELAN2D6F:00 04F3:2D6F",
    ]
    assert schema_errors(schema, doc) == []


def test_edid_target_requires_edid(schema, example):
    doc = copy.deepcopy(example)
    del doc["device"][0]["mapping"]["edid"]
    assert schema_errors(schema, doc) != []


def test_semantic_checks(example):
    doc = copy.deepcopy(example)
    doc["device"][2]["mapping"]["area"] = [0.9, 0.0, 0.1, 1.0]
    doc["device"][0]["tool"][0]["pressure-range"] = [0.8, 0.2]
    doc["device"][3]["pad"]["buttons"]["J"] = "radial-menu:missing"
    doc["device"].append(copy.deepcopy(doc["device"][0]))
    errs = semantic_errors(doc)
    assert any("area" in e for e in errs)
    assert any("range" in e for e in errs)
    assert any("radial-menu:missing" in e for e in errs)
    assert any("duplicate device id" in e for e in errs)


def test_app_local_radial_menu_resolves(example):
    # org.kde.krita refers to radial-menu:krita defined in its own entry
    assert semantic_errors(example) == []
    doc = copy.deepcopy(example)
    del doc["app"][0]["radial-menu"]
    assert any("radial-menu:krita" in e for e in semantic_errors(doc))
