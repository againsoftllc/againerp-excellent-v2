"""Admin-editable slot/label/category config for the PC and CC builders.

The storefront used to hardcode every slot (which catalog category it draws
from, its match/exclude keywords, whether it's required) directly in the
Next.js bundle. These defaults are the exact same data, transcribed here so
an uncustomized install renders identically — a business only sees its own
choices once it actually edits a tool's config in Settings → Plugins →
Again Builder.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.models.builder_tool_config import BuilderToolConfig

DEFAULT_PC_BUILDER_CONFIG: Dict[str, Any] = {
    "groups": [
        {
            "id": "core",
            "name": "Core Components",
            "slots": [
                {"id": "cpu", "name": "Processor", "icon": "memory", "categorySlugs": ["component"], "match": ["processor", "core i", "ryzen"], "required": True, "multiple": False},
                {"id": "motherboard", "name": "Motherboard", "icon": "developer_board", "categorySlugs": ["component"], "match": ["motherboard"], "required": True, "multiple": False},
                {"id": "ram", "name": "RAM", "icon": "memory", "categorySlugs": ["component"], "match": ["ddr", "vengeance"], "required": True, "multiple": True},
                {"id": "storage", "name": "Storage", "icon": "storage", "categorySlugs": ["component"], "match": ["ssd", "nvme", "hdd", "hard disk"], "required": True, "multiple": True},
                {"id": "gpu", "name": "Graphics Card", "icon": "videogame_asset", "categorySlugs": ["component"], "match": ["geforce", "radeon", "rtx", "gtx"], "required": False, "multiple": False},
                {"id": "psu", "name": "Power Supply", "icon": "power", "categorySlugs": ["component"], "match": ["power supply", "psu"], "required": True, "multiple": False},
                {"id": "casing", "name": "Casing", "icon": "dns", "categorySlugs": ["component"], "match": ["casing", "tower"], "required": True, "multiple": False},
                {"id": "cooler", "name": "CPU Cooler", "icon": "ac_unit", "categorySlugs": ["component"], "match": ["cpu cooler", "air cooler", "aio cooler"], "exclude": ["laptop"], "required": False, "multiple": False},
            ],
        },
        {
            "id": "peripherals",
            "name": "Peripherals",
            "slots": [
                {"id": "monitor", "name": "Monitor", "icon": "desktop_windows", "categorySlugs": ["monitor"], "required": False, "multiple": True},
                {"id": "keyboard", "name": "Keyboard", "icon": "keyboard", "categorySlugs": ["accessories", "gaming"], "match": ["keyboard"], "required": False, "multiple": False},
                {"id": "mouse", "name": "Mouse", "icon": "mouse", "categorySlugs": ["accessories", "gaming"], "match": ["mouse"], "exclude": ["mousepad", "mouse pad"], "required": False, "multiple": False},
                {"id": "headphone", "name": "Headphone", "icon": "headset", "categorySlugs": ["accessories", "gaming"], "match": ["headphone", "headset"], "required": False, "multiple": False},
            ],
        },
        {
            "id": "extras",
            "name": "Power & Extras",
            "slots": [
                {"id": "ups", "name": "UPS / IPS", "icon": "battery_charging_full", "categorySlugs": ["power"], "match": ["ups", "ips"], "required": False, "multiple": False},
                {"id": "accessory", "name": "Other Accessories", "icon": "cable", "categorySlugs": ["accessories", "gaming"], "required": False, "multiple": True},
            ],
        },
    ],
}

_SEC = ["Security-Camera"]

DEFAULT_CC_BUILDER_CONFIG: Dict[str, Any] = {
    "slots": [
        {
            "id": "camera", "name": "Camera", "icon": "videocam", "categorySlugs": _SEC,
            "required": True, "multiple": True,
            "types": [
                {"id": "cc", "name": "CC Camera", "match": ["cc camera", "bullet", "dome"], "exclude": ["ip camera"]},
                {"id": "ip", "name": "IP Camera", "match": ["ip camera", "wifi camera"]},
            ],
        },
        {
            "id": "recorder", "name": "Video Recorder", "icon": "dvr", "categorySlugs": _SEC,
            "required": True, "multiple": False,
            "types": [
                {"id": "dvr", "name": "DVR", "match": ["dvr"], "exclude": ["xvr", "nvr"]},
                {"id": "nvr", "name": "NVR", "match": ["nvr"]},
                {"id": "xvr", "name": "XVR", "match": ["xvr"]},
            ],
        },
        {
            "id": "storage", "name": "Storage", "icon": "storage",
            "categorySlugs": [*_SEC, "component"], "match": ["skyhawk", "purple", "hdd", "hard disk"],
            "required": True, "multiple": True,
        },
        {
            "id": "power", "name": "Power Source", "icon": "power", "categorySlugs": _SEC,
            "required": True, "multiple": False,
            "types": [
                {"id": "adapter", "name": "Adapter", "match": ["power adapter", "power supply box"]},
                {"id": "poe", "name": "POE Switch", "match": ["poe switch"]},
            ],
        },
        {
            "id": "connector", "name": "Connector", "icon": "cable", "categorySlugs": _SEC,
            "required": False, "multiple": True,
            "types": [
                {"id": "balun", "name": "Video Baluns", "match": ["balun"]},
                {"id": "rj45", "name": "RJ45", "match": ["rj45"]},
                {"id": "bnc", "name": "BNC", "match": ["bnc"]},
            ],
        },
        {
            "id": "cable", "name": "Cable", "icon": "settings_input_component", "categorySlugs": _SEC,
            "match": ["coaxial cable", "utp cable"], "required": True, "multiple": True,
        },
        {
            "id": "display", "name": "Display", "icon": "desktop_windows", "categorySlugs": ["monitor"],
            "required": False, "multiple": False,
        },
        {
            "id": "input", "name": "Keyboard", "icon": "keyboard", "categorySlugs": ["accessories", "gaming"],
            "required": False, "multiple": False,
            "types": [
                {"id": "keyboard", "name": "Keyboard", "match": ["keyboard"], "exclude": ["combo"]},
                {"id": "mouse", "name": "Mouse", "match": ["mouse"], "exclude": ["mousepad", "mouse pad", "combo"]},
                {"id": "combo", "name": "Combo", "match": ["combo"]},
            ],
        },
        {
            "id": "router", "name": "Router", "icon": "router", "categorySlugs": ["networking"],
            "match": ["router", "mesh"], "required": False, "multiple": False,
        },
    ],
}

DEFAULT_STORAGE_CALCULATOR_CONFIG: Dict[str, Any] = {
    "codecs": [
        {"id": "mjpeg", "label": "MJPEG"},
        {"id": "h264", "label": "H.264"},
        {"id": "h265", "label": "H.265"},
        {"id": "h265plus", "label": "H.265+"},
    ],
    "resolutions": [
        {"label": "33.2MP (8K)", "pixels": 33177600},
        {"label": "12MP (4000x3072)", "pixels": 12288000},
        {"label": "8MP (4K)", "pixels": 8294400},
        {"label": "6MP (3072x2048)", "pixels": 6291456},
        {"label": "5MP (2592x1944)", "pixels": 5038848},
        {"label": "4MP (2688x1520)", "pixels": 4085760},
        {"label": "3MP (2048x1536)", "pixels": 3145728},
        {"label": "2MP (1920x1080)", "pixels": 2073600},
        {"label": "1.3MP (1280x1024)", "pixels": 1310720},
        {"label": "1MP (1280x720)", "pixels": 921600},
        {"label": "D1 (704x480)", "pixels": 337920},
        {"label": "HD1 (704x240)", "pixels": 168960},
        {"label": "CIF (352x240)", "pixels": 84480},
    ],
    "ratios": {
        "mjpeg": {"high": 16, "medium": 25, "low": 31},
        "h264": {
            "high": {"high": 98, "medium": 102, "low": 105},
            "medium": {"high": 160, "medium": 173, "low": 181},
            "low": {"high": 220, "medium": 242, "low": 260},
        },
        "h265": {
            "high": {"high": 260, "medium": 272, "low": 282},
            "medium": {"high": 480, "medium": 510, "low": 536},
            "low": {"high": 620, "medium": 670, "low": 710},
        },
        "h265plus": {
            "high": {"high": 335, "medium": 351, "low": 364},
            "medium": {"high": 590, "medium": 621, "low": 643},
            "low": {"high": 776, "medium": 834, "low": 845},
        },
    },
    "defaults": {
        "cameras": 8,
        "days": 30,
        "hoursPerDay": 24,
        "pixels": 2073600,
        "fps": 15,
        "codec": "h265",
        "quality": "medium",
        "activity": "medium",
    },
    "tips": {
        "format": "MJPEG stores every frame whole and is the least efficient. H.264 suits HD. H.265 and H.265+ are the most efficient — check your recorder supports them before choosing.",
        "resolution": "Higher resolution means more detail but far more storage: 8MP can need three to four times what 2MP does. 2MP is widely supported and keeps costs sensible.",
        "fps": "10-15 fps is usually enough for walking pace. Doubling the frame rate roughly doubles the storage.",
        "quality": "The encoder setting on the camera. If your camera has no such setting, leave it on Medium.",
        "activity": "How much the scene moves. A quiet corridor compresses far better than a busy road, because the codec only stores what changed.",
    },
    "driveCategorySlugs": ["Security-Camera", "component"],
    "surveillanceKeywords": ["skyhawk", "purple", "surveillance"],
}

DEFAULT_POWER_CALCULATOR_CONFIG: Dict[str, Any] = {
    "applianceGroups": [
        {
            "id": "lighting",
            "label": "Lighting & fans",
            "items": [
                {"id": "ceiling-fan", "label": "Ceiling fan", "watts": 75, "icon": "fa:fan", "surge": 1.6},
                {"id": "table-fan", "label": "Table fan", "watts": 50, "icon": "fa:fan", "surge": 1.6},
                {"id": "led-bulb", "label": "LED bulb", "watts": 9, "icon": "lightbulb", "surge": 1},
                {"id": "energy-bulb", "label": "Energy saving bulb", "watts": 25, "icon": "lightbulb", "surge": 1},
                {"id": "tube-light", "label": "Tube light", "watts": 20, "icon": "light", "surge": 1},
            ],
        },
        {
            "id": "computing",
            "label": "Computing & network",
            "items": [
                {"id": "desktop", "label": "Desktop PC", "watts": 200, "icon": "computer", "surge": 1},
                {"id": "laptop", "label": "Laptop", "watts": 65, "icon": "laptop", "surge": 1},
                {"id": "monitor", "label": "Monitor", "watts": 30, "icon": "desktop_windows", "surge": 1},
                {"id": "printer", "label": "Printer", "watts": 50, "icon": "print", "surge": 1.4},
                {"id": "router", "label": "Router / ONU", "watts": 12, "icon": "router", "surge": 1},
            ],
        },
        {
            "id": "surveillance",
            "label": "Surveillance",
            "items": [
                {"id": "cc-camera", "label": "CC camera", "watts": 5, "icon": "videocam", "surge": 1},
                {"id": "recorder", "label": "DVR / NVR", "watts": 30, "icon": "dvr", "surge": 1},
                {"id": "poe-switch", "label": "PoE switch", "watts": 60, "icon": "lan", "surge": 1},
            ],
        },
        {
            "id": "household",
            "label": "Household",
            "items": [
                {"id": "tv", "label": "LED TV (32\")", "watts": 60, "icon": "tv", "surge": 1},
                {"id": "fridge", "label": "Refrigerator", "watts": 150, "icon": "kitchen", "surge": 3},
                {"id": "water-pump", "label": "Water pump", "watts": 750, "icon": "fa:faucetDrip", "surge": 3},
                {"id": "air-cooler", "label": "Air cooler", "watts": 200, "icon": "air", "surge": 2},
                {
                    "id": "ac",
                    "label": "Air conditioner (1 ton)",
                    "watts": 1200,
                    "icon": "ac_unit",
                    "surge": 3,
                    "tooBigForIps": True,
                },
            ],
        },
    ],
    "defaultSelection": {"ceiling-fan": 2, "led-bulb": 4, "router": 1},
    "defaultSetup": {
        "volts": 12,
        "ah": 130,
        "batteries": 1,
        "batteryType": "agm",
        "inverterType": "modified",
    },
    "tips": {
        "battery": "Flooded batteries should not be taken below 40% charge, AGM and gel handle 70%, lithium 90%. A deeper usable range means longer backup from the same Ah.",
        "inverter": "Some battery energy is lost turning DC into mains AC. A pure sine wave inverter keeps about 90% of it, a modified wave one about 82%.",
    },
    "productCategorySlug": "power",
}

DEFAULTS_BY_TOOL: Dict[str, Dict[str, Any]] = {
    "pc-builder": DEFAULT_PC_BUILDER_CONFIG,
    "cc-builder": DEFAULT_CC_BUILDER_CONFIG,
    "storage-calculator": DEFAULT_STORAGE_CALCULATOR_CONFIG,
    "power-calculator": DEFAULT_POWER_CALCULATOR_CONFIG,
}


def load_tool_config(db: Session, tool_slug: str) -> Dict[str, Any]:
    """The effective config for a tool: the admin's override if one was saved
    and still parses, otherwise the tool's built-in default."""
    default = DEFAULTS_BY_TOOL.get(tool_slug)
    if default is None:
        return {}
    row = db.get(BuilderToolConfig, tool_slug)
    if not row or not row.config_json:
        return default
    try:
        data = json.loads(row.config_json)
    except json.JSONDecodeError:
        return default
    if not isinstance(data, dict):
        return default
    return data


def is_tool_customized(db: Session, tool_slug: str) -> bool:
    row = db.get(BuilderToolConfig, tool_slug)
    return bool(row and row.config_json)


def save_tool_config(db: Session, tool_slug: str, config: Dict[str, Any]) -> Dict[str, Any]:
    if tool_slug not in DEFAULTS_BY_TOOL:
        raise ValueError(f"Unknown builder tool: {tool_slug}")
    row = db.get(BuilderToolConfig, tool_slug)
    if not row:
        row = BuilderToolConfig(id=tool_slug)
        db.add(row)
    row.config_json = json.dumps(config)
    db.commit()
    db.refresh(row)
    return load_tool_config(db, tool_slug)


def reset_tool_config(db: Session, tool_slug: str) -> Dict[str, Any]:
    row = db.get(BuilderToolConfig, tool_slug)
    if row:
        db.delete(row)
        db.commit()
    return DEFAULTS_BY_TOOL.get(tool_slug, {})
