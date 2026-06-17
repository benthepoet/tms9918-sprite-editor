def pattern_row_byte(pattern, y, x0=0):
    value = 0
    for x in range(8):
        if pattern[y][x0 + x]:
            value |= 1 << (7 - x)
    return value


def pattern_to_bytes(pattern, size):
    if size == 8:
        return bytes(pattern_row_byte(pattern, y) for y in range(8))
    parts = []
    for y in range(8):
        parts.append(pattern_row_byte(pattern, y, 0))
    for y in range(8, 16):
        parts.append(pattern_row_byte(pattern, y, 0))
    for y in range(8):
        parts.append(pattern_row_byte(pattern, y, 8))
    for y in range(8, 16):
        parts.append(pattern_row_byte(pattern, y, 8))
    return bytes(parts)


def _stacked_sprites(sprites, stack_mask):
    stacked = []
    for index, enabled in enumerate(stack_mask):
        if enabled and index < len(sprites):
            stacked.append(sprites[index])
    return stacked


def encode_panel_binary(size, slots):
    """Encode raw TMS9918 pattern bytes for exported sprites."""
    if size not in (8, 16):
        raise ValueError(f"Unsupported sprite size: {size}")
    return b"".join(
        pattern_to_bytes(sprite["pattern"], size) for _slot_index, sprite in slots
    )


def encode_animation_binary(size, animation):
    """Encode raw pattern bytes for stacked sprites in each animation frame."""
    if size not in (8, 16):
        raise ValueError(f"Unsupported sprite size: {size}")
    parts = []
    for frame in animation.get("frames", []):
        for sprite in _stacked_sprites(
            frame.get("sprites", []), frame.get("stack_mask", [])
        ):
            parts.append(pattern_to_bytes(sprite["pattern"], size))
    return b"".join(parts)