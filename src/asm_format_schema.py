import json
import re
from pathlib import Path

SUPPORTED_VERSION = 1
DEFAULT_FORMAT_ID = "ti99_default"

_LABEL_SANITIZE_RE = re.compile(r"[^A-Za-z0-9_]+")


def formats_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "formats"


def sanitize_label(
    value: str,
    *,
    case: str = "upper",
    max_length: int = 32,
) -> str:
    cleaned = _LABEL_SANITIZE_RE.sub("_", value.strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    if not cleaned:
        cleaned = "LABEL"
    if cleaned[0].isdigit():
        cleaned = f"L_{cleaned}"
    if case == "upper":
        cleaned = cleaned.upper()
    elif case == "lower":
        cleaned = cleaned.lower()
    return cleaned[:max_length]


def _require_mapping(data: dict, key: str) -> dict:
    value = data.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"Format field '{key}' must be an object")
    return value


def _require_string(data: dict, key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Format field '{key}' must be a non-empty string")
    return value


def _validate_lines(section: dict, path: str) -> None:
    lines = section.get("lines")
    if lines is None:
        raise ValueError(f"{path}.lines is required when enabled")
    if not isinstance(lines, list) or not lines:
        raise ValueError(f"{path}.lines must be a non-empty array")
    for line in lines:
        if not isinstance(line, str):
            raise ValueError(f"{path}.lines must contain strings")


def _validate_template_section(section: dict, path: str) -> None:
    if "template" not in section:
        raise ValueError(f"{path}.template is required when enabled")


def validate_format(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("Format file must be a JSON object")
    version = data.get("version")
    if version != SUPPORTED_VERSION:
        raise ValueError(f"Unsupported format version: {version}")

    _require_string(data, "name")
    dialect = _require_mapping(data, "dialect")
    for key in (
        "comment_prefix",
        "data_directive",
        "hex_prefix",
        "value_separator",
    ):
        _require_string(dialect, key)
    if "hex_width" in dialect and not isinstance(dialect["hex_width"], int):
        raise ValueError("dialect.hex_width must be an integer")
    if "bytes_per_line" in dialect and not isinstance(dialect["bytes_per_line"], int):
        raise ValueError("dialect.bytes_per_line must be an integer")

    labels = data.get("labels", {})
    if not isinstance(labels, dict):
        raise ValueError("labels must be an object")
    patterns = labels.get("patterns", {})
    if patterns and not isinstance(patterns, dict):
        raise ValueError("labels.patterns must be an object")

    animation = _require_mapping(data, "animation")
    anim_sections = _require_mapping(animation, "sections")
    for section_name in ("header", "frames", "footer"):
        if section_name not in anim_sections:
            raise ValueError(f"animation.sections.{section_name} is required")

    frames = _require_mapping(anim_sections, "frames")
    per_frame = _require_mapping(frames, "per_frame")
    per_sprite = _require_mapping(frames, "per_sprite")
    if per_frame.get("enabled", True):
        _validate_lines(per_frame, "animation.sections.frames.per_frame")
    if per_sprite.get("enabled", True):
        for key in ("comment", "data"):
            subsection = per_sprite.get(key, {})
            if subsection.get("enabled", True):
                _validate_template_section(subsection, f"animation.sections.frames.per_sprite.{key}")

    sprite = _require_mapping(data, "sprite")
    sprite_sections = _require_mapping(sprite, "sections")
    for key in ("comment", "data"):
        subsection = sprite_sections.get(key, {})
        if subsection.get("enabled", True):
            _validate_template_section(subsection, f"sprite.sections.{key}")

    return data


def load_format(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    return validate_format(data)


def list_formats() -> list[tuple[str, dict]]:
    directory = formats_dir()
    if not directory.is_dir():
        return []
    formats = []
    for path in sorted(directory.glob("*.json")):
        try:
            formats.append((path.stem, load_format(path)))
        except (OSError, json.JSONDecodeError, ValueError):
            continue
    return formats


def load_format_by_id(format_id: str) -> dict:
    path = formats_dir() / f"{format_id}.json"
    if not path.is_file():
        raise FileNotFoundError(f"Export format not found: {format_id}")
    return load_format(path)


def default_format() -> tuple[str, dict]:
    formats = list_formats()
    for format_id, fmt in formats:
        if format_id == DEFAULT_FORMAT_ID:
            return format_id, fmt
    if formats:
        return formats[0]
    raise FileNotFoundError("No export formats found in formats/")