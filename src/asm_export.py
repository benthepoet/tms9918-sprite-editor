import re

from animation_schema import sprite_display_name
from asm_format_schema import get_template, sanitize_label
from binary_export import pattern_to_bytes

VDP_FRAME_SEC = 1.0 / 59.94


def resolve_stack_indices(stack_mask):
    return [index for index, enabled in enumerate(stack_mask) if enabled]


def _dialect_context(fmt: dict) -> dict:
    dialect = fmt["dialect"]
    return {
        "comment": dialect["comment_prefix"],
        "data_directive": dialect["data_directive"],
        "hex_prefix": dialect["hex_prefix"],
        "indent": dialect.get("indent", ""),
        "value_separator": dialect["value_separator"],
    }


def _label_settings(fmt: dict) -> dict:
    labels = fmt.get("labels", {})
    return {
        "case": labels.get("case", "upper"),
        "max_length": labels.get("max_length", 32),
        "patterns": labels.get("patterns", {}),
    }


def _format_label(pattern: str, context: dict, label_settings: dict) -> str:
    if not pattern:
        return ""
    rendered = pattern.format(**context)
    return sanitize_label(
        rendered,
        case=label_settings["case"],
        max_length=label_settings["max_length"],
    )


def _format_hex_value(value: int, fmt: dict, *, width: int | None = None) -> str:
    dialect = fmt["dialect"]
    prefix = dialect["hex_prefix"]
    hex_width = width if width is not None else dialect.get("hex_width", 2)
    uppercase = dialect.get("hex_uppercase", True)
    text = f"{value:0{hex_width}X}" if uppercase else f"{value:0{hex_width}x}"
    return f"{prefix}{text}"


def _format_hex_values(byte_values, fmt: dict) -> str:
    dialect = fmt["dialect"]
    prefix = dialect["hex_prefix"]
    width = dialect.get("hex_width", 2)
    uppercase = dialect.get("hex_uppercase", True)
    separator = dialect["value_separator"]
    parts = []
    for value in byte_values:
        text = f"{value:0{width}X}" if uppercase else f"{value:0{width}x}"
        parts.append(f"{prefix}{text}")
    return separator.join(parts)


def _format_data_lines(byte_values, fmt: dict, *, bytes_per_line: int | None = None) -> list[str]:
    dialect = fmt["dialect"]
    chunk_size = bytes_per_line or dialect.get("bytes_per_line", 8)
    lines = []
    for index in range(0, len(byte_values), chunk_size):
        chunk = byte_values[index : index + chunk_size]
        lines.append(
            f"{dialect['data_directive']} {_format_hex_values(chunk, fmt)}"
        )
    return lines


def _format_decimal_lines(values, fmt: dict, *, bytes_per_line: int = 16) -> list[str]:
    dialect = fmt["dialect"]
    lines = []
    for index in range(0, len(values), bytes_per_line):
        chunk = values[index : index + bytes_per_line]
        lines.append(
            f"{dialect['data_directive']} {dialect['value_separator'].join(str(v) for v in chunk)}"
        )
    return lines


def _join_indented_lines(lines: list[str], indent: str) -> str:
    if not lines:
        return ""
    return "\n".join(f"{indent}{line}" for line in lines)


def _render_tpl(fmt: dict, name: str, context: dict) -> str:
    template = get_template(fmt, name)
    return template.format(**context)


def _sprite_name(sprite: dict, slot: int) -> str:
    return sprite_display_name(sprite, slot)


def _sprite_label_from_sprite(
    sprite: dict,
    slot: int,
    fmt: dict,
    *,
    frame_index: int | None = None,
    sprite_index: int | None = None,
    frame_label: str = "",
    anim_label: str = "",
) -> str:
    label_settings = _label_settings(fmt)
    resolved_frame_index = 0 if frame_index is None else frame_index
    if sprite_index is not None:
        resolved_sprite_index = sprite_index
    elif frame_index is not None:
        resolved_sprite_index = resolved_frame_index
    else:
        resolved_sprite_index = slot
    context = {
        "sprite_name": _sprite_name(sprite, slot),
        "slot": slot,
        "slot02d": f"{slot:02d}",
        "frame_index": resolved_frame_index,
        "frame_number": resolved_frame_index + 1,
        "sprite_index": resolved_sprite_index,
        "frame_label": frame_label,
        "anim_label": anim_label,
    }
    return _format_label(
        label_settings["patterns"].get("sprite", "{sprite_name}"),
        context,
        label_settings,
    )


def build_sprite_label_map(frames, fmt: dict, anim_label: str = "") -> dict[tuple[int, int], str]:
    used_sprite_labels: set[str] = set()
    labels: dict[tuple[int, int], str] = {}
    sprite_indices = build_sprite_index_map(frames)
    label_settings = _label_settings(fmt)

    for frame_index, frame in enumerate(frames):
        sprites = frame.get("sprites", [])
        stack_mask = frame.get("stack_mask", [])
        frame_label = _format_label(
            label_settings["patterns"].get(
                "frame", "{anim_label}_F{frame_index:02d}"
            ),
            {
                "anim_label": anim_label,
                "frame_index": frame_index,
                "frame_number": frame_index + 1,
            },
            label_settings,
        )
        for slot in resolve_stack_indices(stack_mask):
            sprite = sprites[slot]
            base_label = _sprite_label_from_sprite(
                sprite,
                slot,
                fmt,
                frame_index=frame_index,
                sprite_index=sprite_indices.get((frame_index, slot)),
                frame_label=frame_label,
                anim_label=anim_label,
            )
            if anim_label:
                base_label = f"{anim_label}_{base_label}"
            label = f"{base_label}_F{frame_index:02d}"
            if label in used_sprite_labels:
                label = f"{base_label}_F{frame_index:02d}_S{slot:02d}"
            used_sprite_labels.add(label)
            labels[(frame_index, slot)] = label
    return labels


def build_sprite_index_map(frames) -> dict[tuple[int, int], int]:
    sprite_indices: dict[tuple[int, int], int] = {}
    sprite_index = 0
    for frame_index, frame in enumerate(frames):
        for slot in resolve_stack_indices(frame.get("stack_mask", [])):
            sprite_indices[(frame_index, slot)] = sprite_index
            sprite_index += 1
    return sprite_indices


def _resolve_sprite_index(
    frame_index: int | None,
    slot: int,
    sprite_indices: dict[tuple[int, int], int] | None,
) -> int:
    if sprite_indices is not None:
        resolved_frame_index = 0 if frame_index is None else frame_index
        return sprite_indices.get((resolved_frame_index, slot), 0)
    resolved_frame_index = 0 if frame_index is None else frame_index
    return resolved_frame_index * 32 + slot


def _sprite_context(
    *,
    sprite: dict,
    slot: int,
    size: int,
    fmt: dict,
    frame_index: int | None = None,
    sprite_index: int | None = None,
    frame_label: str = "",
    anim_label: str = "",
    sprite_label: str | None = None,
) -> dict:
    resolved_frame_index = 0 if frame_index is None else frame_index
    if sprite_index is not None:
        resolved_sprite_index = sprite_index
    elif frame_index is not None:
        resolved_sprite_index = resolved_frame_index
    else:
        resolved_sprite_index = slot
    if sprite_label is None:
        sprite_label = _sprite_label_from_sprite(
            sprite,
            slot,
            fmt,
            frame_index=frame_index,
            sprite_index=sprite_index,
            frame_label=frame_label,
            anim_label=anim_label,
        )
    return {
        **_dialect_context(fmt),
        "slot": slot,
        "slot02d": f"{slot:02d}",
        "sprite_name": _sprite_name(sprite, slot),
        "color": sprite["color"],
        "size": size,
        "frame_label": frame_label,
        "frame_index": resolved_frame_index,
        "frame_number": resolved_frame_index + 1,
        "anim_label": anim_label,
        "sprite_index": resolved_sprite_index,
        "sprite_label": sprite_label,
    }


def _data_lines_for_sprite(
    sprite: dict,
    size: int,
    fmt: dict,
    *,
    bytes_per_line: int | None = None,
    indent_data: bool = True,
) -> str:
    byte_values = list(pattern_to_bytes(sprite["pattern"], size))
    lines = _format_data_lines(byte_values, fmt, bytes_per_line=bytes_per_line)
    indent = fmt["dialect"].get("indent", "")
    if indent_data:
        return _join_indented_lines(lines, indent)
    return "\n".join(lines)


def _sprite_template_name(fmt: dict, *, animation_sprite: bool = False) -> str:
    templates = fmt.get("templates", {})
    if animation_sprite and "sprite_block" in templates:
        return "sprite_block"
    return "sprite"


def _render_sprite_block(
    sprite: dict,
    slot: int,
    size: int,
    fmt: dict,
    *,
    frame_index: int | None = None,
    sprite_index: int | None = None,
    frame_label: str = "",
    anim_label: str = "",
    sprite_label: str | None = None,
    bytes_per_line: int | None = None,
    indent_data: bool = True,
    animation_sprite: bool = False,
) -> str:
    context = _sprite_context(
        sprite=sprite,
        slot=slot,
        size=size,
        fmt=fmt,
        frame_index=frame_index,
        sprite_index=sprite_index,
        frame_label=frame_label,
        anim_label=anim_label,
        sprite_label=sprite_label,
    )
    context["byte_count"] = len(pattern_to_bytes(sprite["pattern"], size))
    context["data_lines"] = _data_lines_for_sprite(
        sprite,
        size,
        fmt,
        bytes_per_line=bytes_per_line,
        indent_data=indent_data,
    )
    return _render_tpl(
        fmt,
        _sprite_template_name(fmt, animation_sprite=animation_sprite),
        context,
    )


def _frame_label_for_index(frame_index: int, anim_label: str, fmt: dict) -> str:
    label_settings = _label_settings(fmt)
    return _format_label(
        label_settings["patterns"].get("frame", "{anim_label}_F{frame_index:02d}"),
        {
            "anim_label": anim_label,
            "frame_index": frame_index,
            "frame_number": frame_index + 1,
        },
        label_settings,
    )


def _render_frame_block(
    sprites,
    stack_mask,
    *,
    size: int,
    fmt: dict,
    frame_index: int,
    duration: int,
    anim_label: str,
    sprite_indices: dict[tuple[int, int], int] | None = None,
    sprite_labels: dict[tuple[int, int], str] | None = None,
    bytes_per_line: int | None = None,
    indent_data: bool = True,
) -> str:
    frame_label = _frame_label_for_index(frame_index, anim_label, fmt)
    sprite_blocks = []
    for slot in resolve_stack_indices(stack_mask):
        sprite_blocks.append(
            _render_sprite_block(
                sprites[slot],
                slot,
                size,
                fmt,
                frame_index=frame_index,
                sprite_index=_resolve_sprite_index(
                    frame_index,
                    slot,
                    sprite_indices,
                ),
                frame_label=frame_label,
                anim_label=anim_label,
                sprite_label=(
                    sprite_labels.get((frame_index, slot))
                    if sprite_labels is not None
                    else None
                ),
                bytes_per_line=bytes_per_line,
                indent_data=indent_data,
                animation_sprite=True,
            )
        )
    context = {
        **_dialect_context(fmt),
        "frame_label": frame_label,
        "frame_index": frame_index,
        "frame_number": frame_index + 1,
        "duration": duration,
        "anim_label": anim_label,
        "sprites_block": "\n".join(sprite_blocks),
    }
    return _render_tpl(fmt, "frame", context)


def _render_frames_block(
    frames,
    *,
    size: int,
    fmt: dict,
    anim_label: str,
    sprite_indices: dict[tuple[int, int], int] | None = None,
    sprite_labels: dict[tuple[int, int], str] | None = None,
    bytes_per_line: int | None = None,
    indent_data: bool = True,
    frame_separator: str = "\n\n",
) -> str:
    blocks = []
    for index, frame in enumerate(frames):
        block = _render_frame_block(
            frame.get("sprites", []),
            frame.get("stack_mask", []),
            size=size,
            fmt=fmt,
            frame_index=index,
            duration=frame.get("duration", 4),
            anim_label=anim_label,
            sprite_indices=sprite_indices,
            sprite_labels=sprite_labels,
            bytes_per_line=bytes_per_line,
            indent_data=indent_data,
        )
        if block:
            blocks.append(block)
    if not blocks:
        return ""
    return frame_separator.join(blocks)


def _render_duration_table_block(
    durations,
    fmt: dict,
    anim_context: dict,
) -> str:
    if not durations or "duration_table" not in fmt.get("templates", {}):
        return ""
    label_settings = _label_settings(fmt)
    context = dict(anim_context)
    context["duration_table_label"] = _format_label(
        label_settings["patterns"].get("duration_table", "{anim_label}_DUR"),
        context,
        label_settings,
    )
    bytes_per_line = fmt.get("duration_table_bytes_per_line", 16)
    duration_lines = _format_decimal_lines(
        durations,
        fmt,
        bytes_per_line=bytes_per_line,
    )
    context["duration_lines"] = _join_indented_lines(
        duration_lines,
        context["indent"],
    )
    return _render_tpl(fmt, "duration_table", context)


def _render_frame_directory_lines(
    frames,
    *,
    size: int,
    fmt: dict,
    anim_context: dict,
    sprite_indices: dict[tuple[int, int], int] | None = None,
    sprite_labels: dict[tuple[int, int], str] | None = None,
) -> str:
    lines = []
    for index, frame in enumerate(frames):
        stack_mask = frame.get("stack_mask", [])
        slots = resolve_stack_indices(stack_mask)
        primary_slot = slots[0] if slots else 0
        frame_context = _sprite_context(
            sprite=frame.get("sprites", [])[primary_slot],
            slot=primary_slot,
            size=size,
            fmt=fmt,
            frame_index=index,
            sprite_index=_resolve_sprite_index(
                index,
                primary_slot,
                sprite_indices,
            ),
            anim_label=anim_context["anim_label"],
            frame_label=_frame_label_for_index(
                index,
                anim_context["anim_label"],
                fmt,
            ),
            sprite_label=(
                sprite_labels.get((index, primary_slot))
                if sprite_labels is not None
                else None
            ),
        )
        frame_context["duration"] = frame.get("duration", 4)
        duration_hex_width = fmt["dialect"].get("duration_hex_width", 4)
        frame_context["duration_hex"] = _format_hex_value(
            frame_context["duration"],
            fmt,
            width=duration_hex_width,
        )
        lines.append(_render_tpl(fmt, "frame_directory_entry", frame_context))
    return "\n".join(lines)


def _normalize_output(text: str) -> str:
    return text.replace("\r\n", "\n").strip("\n")


def render_sprite(sprite: dict, slot: int, size: int, fmt: dict, *, frame_label: str = "") -> str:
    indent_data = fmt.get(
        "indent_static_sprite_data",
        fmt.get("indent_sprite_data", True),
    )
    return _render_sprite_block(
        sprite,
        slot,
        size,
        fmt,
        frame_label=frame_label,
        indent_data=indent_data,
    )


def render_frame(
    sprites,
    stack_mask,
    *,
    size: int,
    fmt: dict,
    frame_index: int,
    duration: int,
    anim_label: str,
    sprite_indices: dict[tuple[int, int], int] | None = None,
    sprite_labels: dict[tuple[int, int], str] | None = None,
) -> list[str]:
    block = _render_frame_block(
        sprites,
        stack_mask,
        size=size,
        fmt=fmt,
        frame_index=frame_index,
        duration=duration,
        anim_label=anim_label,
        sprite_indices=sprite_indices,
        sprite_labels=sprite_labels,
        indent_data=fmt.get("indent_sprite_data", True),
    )
    if not block:
        return []
    return block.splitlines()


def render_animation(animation: dict, size: int, fmt: dict) -> str:
    label_settings = _label_settings(fmt)
    frames = animation.get("frames", [])
    durations = [frame.get("duration", 4) for frame in frames]
    total_duration = sum(durations)

    anim_context = {
        **_dialect_context(fmt),
        "anim_name": animation.get("name", ""),
        "frame_count": len(frames),
        "loop": 1 if animation.get("loop", True) else 0,
        "durations": durations,
        "durations_csv": ", ".join(str(value) for value in durations),
        "total_duration": total_duration,
        "total_ms": int(total_duration / 59.94 * 1000),
    }
    anim_context["anim_label"] = _format_label(
        label_settings["patterns"].get("animation", "{anim_name}"),
        anim_context,
        label_settings,
    )
    sprite_indices = build_sprite_index_map(frames)
    sprite_labels = build_sprite_label_map(frames, fmt, anim_context["anim_label"])

    layout = fmt.get("layout", "default")
    if layout == "frame_directory":
        frame_count_hex_width = fmt["dialect"].get("frame_count_hex_width", 2)
        anim_context["frame_count_hex"] = _format_hex_value(
            anim_context["frame_count"],
            fmt,
            width=frame_count_hex_width,
        )
        anim_context["frame_count_line"] = _render_tpl(fmt, "frame_count_line", anim_context)
        anim_context["frame_directory_lines"] = _render_frame_directory_lines(
            frames,
            size=size,
            fmt=fmt,
            anim_context=anim_context,
            sprite_indices=sprite_indices,
            sprite_labels=sprite_labels,
        )
        anim_context["frames_block"] = _render_frames_block(
            frames,
            size=size,
            fmt=fmt,
            anim_label=anim_context["anim_label"],
            sprite_indices=sprite_indices,
            sprite_labels=sprite_labels,
            indent_data=fmt.get("indent_sprite_data", True),
            frame_separator="\n\n",
        )
        return _normalize_output(_render_tpl(fmt, "animation", anim_context))

    anim_context["frames_block"] = _render_frames_block(
        frames,
        size=size,
        fmt=fmt,
        anim_label=anim_context["anim_label"],
        sprite_indices=sprite_indices,
        sprite_labels=sprite_labels,
        indent_data=fmt.get("indent_sprite_data", True),
        frame_separator="\n\n",
    )
    anim_context["duration_table_block"] = _render_duration_table_block(
        durations,
        fmt,
        anim_context,
    )
    return _normalize_output(_render_tpl(fmt, "animation", anim_context))


def render_frame_block(
    sprites,
    stack_mask,
    *,
    size: int,
    fmt: dict,
    header_lines: list[str] | None = None,
    frame_index: int | None = None,
    duration: int | None = None,
    anim_label: str = "",
    sprite_indices: dict[tuple[int, int], int] | None = None,
    sprite_labels: dict[tuple[int, int], str] | None = None,
) -> str:
    lines = []
    if header_lines:
        lines.extend(header_lines)
    if frame_index is not None and duration is not None:
        block = _render_frame_block(
            sprites,
            stack_mask,
            size=size,
            fmt=fmt,
            frame_index=frame_index,
            duration=duration,
            anim_label=anim_label,
            sprite_indices=sprite_indices,
            sprite_labels=sprite_labels,
            indent_data=fmt.get("indent_sprite_data", True),
        )
        if block:
            lines.append(block)
    else:
        resolved_frame_index = 0 if frame_index is None else frame_index
        sprite_blocks = []
        for slot in resolve_stack_indices(stack_mask):
            sprite_blocks.append(
                _render_sprite_block(
                    sprites[slot],
                    slot,
                    size,
                    fmt,
                    frame_index=frame_index,
                    sprite_index=_resolve_sprite_index(
                        frame_index,
                        slot,
                        sprite_indices,
                    ),
                    anim_label=anim_label,
                    sprite_label=(
                        sprite_labels.get((resolved_frame_index, slot))
                        if sprite_labels is not None
                        else None
                    ),
                    indent_data=fmt.get("indent_sprite_data", True),
                    animation_sprite=True,
                )
            )
        lines.extend(sprite_blocks)
    return "\n".join(lines)