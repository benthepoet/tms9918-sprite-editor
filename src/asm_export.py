import re

from asm_format_schema import sanitize_label
from binary_export import pattern_to_bytes

VDP_FRAME_SEC = 1.0 / 59.94


def resolve_stack_indices(stack_mask):
    return [index for index, enabled in enumerate(stack_mask) if enabled]


def _section_enabled(section, default=True):
    if not isinstance(section, dict):
        return default
    return section.get("enabled", default)


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


def _format_decimal_line(values, fmt: dict, *, bytes_per_line: int = 16) -> str:
    dialect = fmt["dialect"]
    parts = []
    for index in range(0, len(values), bytes_per_line):
        chunk = values[index : index + bytes_per_line]
        parts.append(
            f"{dialect['data_directive']} {dialect['value_separator'].join(str(v) for v in chunk)}"
        )
    return "\n".join(parts)


def _sprite_name(sprite: dict, slot: int) -> str:
    return sprite.get("name") or f"Sprite {slot:02d}"


def _render_lines(lines, context: dict) -> list[str]:
    return [line.format(**context) for line in lines]


def _append_label_line(lines: list[str], label_line: str, *, colon: bool = True) -> None:
    label_line = label_line.rstrip(":")
    lines.append(f"{label_line}:" if colon else label_line)


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


def _sprite_label_context(
    *,
    frame_index: int,
    slot: int,
    anim_label: str,
    fmt: dict,
    sprites,
    size: int,
    sprite_index: int | None = None,
) -> dict:
    label_settings = _label_settings(fmt)
    context = {
        **_dialect_context(fmt),
        "frame_index": frame_index,
        "frame_number": frame_index + 1,
        "anim_label": anim_label,
        "slot": slot,
        "slot02d": f"{slot:02d}",
        "sprite_name": _sprite_name(sprites[slot], slot),
        "color": sprites[slot]["color"],
        "size": size,
    }
    context["frame_label"] = _format_label(
        label_settings["patterns"].get("frame", "{anim_label}_F{frame_index:02d}"),
        context,
        label_settings,
    )
    resolved_sprite_index = (
        sprite_index if sprite_index is not None else frame_index
    )
    context["sprite_index"] = resolved_sprite_index
    context["sprite_label"] = _format_label(
        label_settings["patterns"].get("sprite", "{frame_label}_S{slot:02d}"),
        context,
        label_settings,
    )
    return context


def _build_frame_context(
    *,
    frame_index: int,
    duration: int,
    anim_label: str,
    fmt: dict,
    sprites,
    stack_mask,
    size: int,
    sprite_indices: dict[tuple[int, int], int] | None = None,
    slot: int | None = None,
) -> dict:
    slots = resolve_stack_indices(stack_mask)
    resolved_slot = slots[0] if slot is None else slot
    if not slots:
        slots = [resolved_slot]

    frame_context = _sprite_label_context(
        frame_index=frame_index,
        slot=resolved_slot,
        anim_label=anim_label,
        fmt=fmt,
        sprites=sprites,
        size=size,
        sprite_index=_resolve_sprite_index(
            frame_index,
            resolved_slot,
            sprite_indices,
        ),
    )
    frame_context["duration"] = duration
    duration_hex_width = fmt["dialect"].get("duration_hex_width", 4)
    frame_context["duration_hex"] = _format_hex_value(
        duration,
        fmt,
        width=duration_hex_width,
    )
    return frame_context


def _normalize_output(text: str) -> str:
    return text.replace("\r\n", "\n").strip("\n")


def _render_sprite_lines(
    sprite: dict,
    slot: int,
    size: int,
    fmt: dict,
    *,
    frame_label: str,
    sprite_sections: dict,
    frame_index: int | None = None,
    sprite_index: int | None = None,
    anim_label: str = "",
) -> list[str]:
    label_settings = _label_settings(fmt)
    byte_values = list(pattern_to_bytes(sprite["pattern"], size))
    resolved_frame_index = 0 if frame_index is None else frame_index
    resolved_sprite_index = (
        sprite_index if sprite_index is not None else resolved_frame_index
    )
    context = {
        **_dialect_context(fmt),
        "slot": slot,
        "slot02d": f"{slot:02d}",
        "sprite_name": _sprite_name(sprite, slot),
        "color": sprite["color"],
        "size": size,
        "byte_count": len(byte_values),
        "frame_label": frame_label,
        "frame_index": resolved_frame_index,
        "frame_number": resolved_frame_index + 1,
        "anim_label": anim_label,
        "sprite_index": resolved_sprite_index,
    }
    context["sprite_label"] = _format_label(
        label_settings["patterns"].get("sprite", "{frame_label}_S{slot:02d}"),
        context,
        label_settings,
    )

    lines = []
    label_section = sprite_sections.get("label", {})
    if _section_enabled(label_section, default=False):
        label_line = label_section["template"].format(**context)
        _append_label_line(
            lines,
            label_line,
            colon=label_section.get("colon", True),
        )

    comment_section = sprite_sections.get("comment", {})
    if _section_enabled(comment_section, default=True):
        lines.append(comment_section["template"].format(**context))

    data_section = sprite_sections.get("data", {})
    if _section_enabled(data_section, default=True):
        bytes_per_line = data_section.get("bytes_per_line", 8)
        data_lines = _format_data_lines(byte_values, fmt, bytes_per_line=bytes_per_line)
        template = data_section.get("template", "{data_line}")
        for data_line in data_lines:
            context["data_line"] = data_line
            context["byte_line"] = data_line
            lines.append(template.format(**context))
    return lines


def render_sprite(sprite: dict, slot: int, size: int, fmt: dict, *, frame_label: str = "") -> str:
    sprite_sections = fmt["sprite"]["sections"]
    lines = _render_sprite_lines(
        sprite,
        slot,
        size,
        fmt,
        frame_label=frame_label,
        sprite_sections=sprite_sections,
    )
    return "\n".join(lines)


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
) -> list[str]:
    frame_sections = fmt["animation"]["sections"]["frames"]
    if not _section_enabled(frame_sections, default=True):
        return []

    per_frame = frame_sections["per_frame"]
    per_sprite = frame_sections["per_sprite"]
    frame_context = _build_frame_context(
        frame_index=frame_index,
        duration=duration,
        anim_label=anim_label,
        fmt=fmt,
        sprites=sprites,
        stack_mask=stack_mask,
        size=size,
        sprite_indices=sprite_indices,
    )

    lines = []
    if _section_enabled(per_frame, default=True):
        if per_frame.get("label", {}).get("enabled", False):
            label_template = per_frame["label"].get("template", "{frame_label}")
            label_line = label_template.format(**frame_context)
            _append_label_line(
                lines,
                label_line,
                colon=per_frame.get("label", {}).get("colon", True),
            )
        lines.extend(_render_lines(per_frame.get("lines", []), frame_context))

    if _section_enabled(per_sprite, default=True):
        for slot in resolve_stack_indices(stack_mask):
            lines.extend(
                _render_sprite_lines(
                    sprites[slot],
                    slot,
                    size,
                    fmt,
                    frame_label=frame_context["frame_label"],
                    sprite_sections=per_sprite,
                    frame_index=frame_index,
                    sprite_index=_resolve_sprite_index(
                        frame_index,
                        slot,
                        sprite_indices,
                    ),
                    anim_label=anim_label,
                )
            )
    return lines


def _render_frame_directory(
    frames,
    *,
    size: int,
    fmt: dict,
    anim_context: dict,
    frame_directory: dict,
    sprite_indices: dict[tuple[int, int], int] | None = None,
) -> list[str]:
    lines = []
    label_section = frame_directory.get("label", {})
    if _section_enabled(label_section, default=True):
        label_line = label_section.get("template", "{anim_label}").format(**anim_context)
        _append_label_line(
            lines,
            label_line,
            colon=label_section.get("colon", False),
        )

    count_section = frame_directory.get("frame_count", {})
    if _section_enabled(count_section, default=True):
        count_context = dict(anim_context)
        count_context["frame_count_hex"] = _format_hex_value(
            count_context["frame_count"],
            fmt,
            width=fmt["dialect"].get("frame_count_hex_width", 2),
        )
        template = count_section.get(
            "template",
            "{indent}{data_directive} {frame_count_hex}{comment} Frame count",
        )
        lines.append(template.format(**count_context))

    per_frame = frame_directory.get("per_frame", {})
    if _section_enabled(per_frame, default=True):
        template = per_frame.get(
            "template",
            "{indent}DATA {sprite_label},{duration_hex}{comment} Frame {frame_index} address and duration",
        )
        for index, frame in enumerate(frames):
            frame_context = _build_frame_context(
                frame_index=index,
                duration=frame.get("duration", 4),
                anim_label=anim_context["anim_label"],
                fmt=fmt,
                sprites=frame.get("sprites", []),
                stack_mask=frame.get("stack_mask", []),
                size=size,
                sprite_indices=sprite_indices,
            )
            lines.append(template.format(**frame_context))

    if lines:
        lines.append("")
    return lines


def render_animation(animation: dict, size: int, fmt: dict) -> str:
    sections = fmt["animation"]["sections"]
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

    lines = []
    header = sections.get("header", {})
    if _section_enabled(header, default=True):
        lines.extend(_render_lines(header["lines"], anim_context))

    frame_directory = sections.get("frame_directory", {})
    if _section_enabled(frame_directory, default=False):
        lines.extend(
            _render_frame_directory(
                frames,
                size=size,
                fmt=fmt,
                anim_context=anim_context,
                frame_directory=frame_directory,
                sprite_indices=sprite_indices,
            )
        )

    frame_sections = sections.get("frames", {})
    if _section_enabled(frame_sections, default=True):
        for index, frame in enumerate(frames):
            frame_lines = render_frame(
                frame.get("sprites", []),
                frame.get("stack_mask", []),
                size=size,
                fmt=fmt,
                frame_index=index,
                duration=frame.get("duration", 4),
                anim_label=anim_context["anim_label"],
                sprite_indices=sprite_indices,
            )
            if frame_lines:
                lines.extend(frame_lines)
                lines.extend(["", ""])

    duration_table = sections.get("duration_table", {})
    if _section_enabled(duration_table, default=False) and durations:
        table_context = dict(anim_context)
        table_context["duration_table_label"] = _format_label(
            label_settings["patterns"].get("duration_table", "{anim_label}_DUR"),
            table_context,
            label_settings,
        )
        table_context["duration_line"] = _format_decimal_line(
            durations,
            fmt,
            bytes_per_line=duration_table.get("bytes_per_line", 16),
        )
        if duration_table.get("label", {}).get("enabled", True):
            label_template = duration_table.get("label", {}).get(
                "template", "{duration_table_label}"
            )
            label_line = label_template.format(**table_context)
            _append_label_line(
                lines,
                label_line,
                colon=duration_table.get("label", {}).get("colon", True),
            )
        comment_template = duration_table.get("comment", {}).get("template")
        if comment_template:
            lines.append(comment_template.format(**table_context))
        data_section = duration_table.get("data", {})
        if _section_enabled(data_section, default=True):
            data_template = data_section.get("template", "{duration_line}")
            lines.append(data_template.format(**table_context))

    frame_count = sections.get("frame_count", {})
    if _section_enabled(frame_count, default=False):
        count_context = dict(anim_context)
        count_context["frame_count_label"] = _format_label(
            label_settings["patterns"].get("frame_count", "{anim_label}_NFRAMES"),
            count_context,
            label_settings,
        )
        if frame_count.get("label", {}).get("enabled", True):
            label_template = frame_count.get("label", {}).get(
                "template", "{frame_count_label}"
            )
            label_line = label_template.format(**count_context)
            _append_label_line(
                lines,
                label_line,
                colon=frame_count.get("label", {}).get("colon", True),
            )
        comment_template = frame_count.get("comment", {}).get("template")
        if comment_template:
            lines.append(comment_template.format(**count_context))
        data_section = frame_count.get("data", {})
        if _section_enabled(data_section, default=True):
            data_template = data_section.get(
                "template",
                "{data_directive} {frame_count}",
            )
            lines.append(data_template.format(**count_context))

    footer = sections.get("footer", {})
    if _section_enabled(footer, default=True):
        lines.extend(_render_lines(footer["lines"], anim_context))

    return _normalize_output("\n".join(lines))


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
) -> str:
    lines = []
    if header_lines:
        lines.extend(header_lines)
    if frame_index is not None and duration is not None:
        lines.extend(
            render_frame(
                sprites,
                stack_mask,
                size=size,
                fmt=fmt,
                frame_index=frame_index,
                duration=duration,
                anim_label=anim_label,
                sprite_indices=sprite_indices,
            )
        )
    else:
        sprite_sections = fmt["animation"]["sections"]["frames"]["per_sprite"]
        for slot in resolve_stack_indices(stack_mask):
            lines.extend(
                _render_sprite_lines(
                    sprites[slot],
                    slot,
                    size,
                    fmt,
                    frame_label="",
                    sprite_sections=sprite_sections,
                    frame_index=frame_index,
                    sprite_index=_resolve_sprite_index(
                        frame_index,
                        slot,
                        sprite_indices,
                    ),
                    anim_label=anim_label,
                )
            )
    return "\n".join(lines)