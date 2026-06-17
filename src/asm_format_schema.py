import json
import re
from pathlib import Path

DEFAULT_FORMAT_ID = "ti99_default"
FORMAT_CONFIG_NAME = "format.json"

_LABEL_SANITIZE_RE = re.compile(r"[^A-Za-z0-9_]+")

_REQUIRED_DIALECT_KEYS = (
    "comment_prefix",
    "data_directive",
    "hex_prefix",
    "value_separator",
)


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


def validate_format(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("Format config must be a JSON object")

    _require_string(data, "name")
    dialect = _require_mapping(data, "dialect")
    for key in _REQUIRED_DIALECT_KEYS:
        _require_string(dialect, key)
    if "hex_width" in dialect and not isinstance(dialect["hex_width"], int):
        raise ValueError("dialect.hex_width must be an integer")
    if "bytes_per_line" in dialect and not isinstance(dialect["bytes_per_line"], int):
        raise ValueError("dialect.bytes_per_line must be an integer")

    labels = data.get("labels", {})
    if labels and not isinstance(labels, dict):
        raise ValueError("labels must be an object")
    patterns = labels.get("patterns", {})
    if patterns and not isinstance(patterns, dict):
        raise ValueError("labels.patterns must be an object")

    layout = data.get("layout", "default")
    if layout not in ("default", "frame_directory"):
        raise ValueError(f"Unsupported layout: {layout}")

    templates = data.get("templates")
    if templates is not None and not isinstance(templates, dict):
        raise ValueError("templates must be an object")

    return data


def _load_templates(format_dir: Path) -> dict[str, str]:
    templates = {}
    for path in sorted(format_dir.glob("*.tpl")):
        templates[path.stem] = path.read_text(encoding="utf-8").strip("\n")
    if not templates:
        raise ValueError(f"No .tpl files found in {format_dir}")
    return templates


def load_format(path: Path) -> dict:
    if path.is_dir():
        config_path = path / FORMAT_CONFIG_NAME
        format_dir = path
    else:
        config_path = path
        format_dir = path.parent

    with config_path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    fmt = validate_format(data)
    fmt["templates"] = _load_templates(format_dir)
    fmt["format_id"] = format_dir.name
    return fmt


def list_formats() -> list[tuple[str, dict]]:
    directory = formats_dir()
    if not directory.is_dir():
        return []

    formats = []
    for config_path in sorted(directory.glob(f"*/{FORMAT_CONFIG_NAME}")):
        format_id = config_path.parent.name
        try:
            formats.append((format_id, load_format(config_path.parent)))
        except (OSError, json.JSONDecodeError, ValueError):
            continue
    return formats


def load_format_by_id(format_id: str) -> dict:
    path = formats_dir() / format_id
    config_path = path / FORMAT_CONFIG_NAME
    if not config_path.is_file():
        raise FileNotFoundError(f"Export format not found: {format_id}")
    return load_format(path)


def get_template(fmt: dict, name: str) -> str:
    templates = fmt.get("templates", {})
    if name not in templates:
        raise KeyError(f"Template '{name}' not found for format {fmt.get('format_id', '?')}")
    return templates[name]


def format_animation_only(fmt: dict) -> bool:
    return bool(fmt.get("animation_only"))


def default_format() -> tuple[str, dict]:
    formats = list_formats()
    for format_id, fmt in formats:
        if format_id == DEFAULT_FORMAT_ID:
            return format_id, fmt
    if formats:
        return formats[0]
    raise FileNotFoundError("No export formats found in formats/")