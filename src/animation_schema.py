"""Pure functions for animation frame validation and project schema (JSON v2)."""

MAX_ANIMATIONS = 32
MAX_FRAMES_PER_ANIM = 64
MAX_FILE_BYTES_WARN = 5_000_000


def deep_copy_sprite(sprite: dict) -> dict:
    return {
        "pattern": [row[:] for row in sprite["pattern"]],
        "color": sprite["color"],
    }


def deep_copy_sprites(sprites: list) -> list:
    return [deep_copy_sprite(sprite) for sprite in sprites]


def deep_copy_animation(anim: dict) -> dict:
    return {
        "name": anim["name"],
        "loop": anim.get("loop", True),
        "frames": [deep_copy_frame(frame) for frame in anim.get("frames", [])],
    }


def deep_copy_frame(frame: dict) -> dict:
    return {
        "duration": frame["duration"],
        "stack_enabled": frame["stack_enabled"],
        "stack_mask": frame["stack_mask"][:],
        "sprites": deep_copy_sprites(frame["sprites"]),
    }


def frames_equal(left: dict, right: dict) -> bool:
    if left.get("duration") != right.get("duration"):
        return False
    if left.get("stack_enabled") != right.get("stack_enabled"):
        return False
    if left.get("stack_mask") != right.get("stack_mask"):
        return False
    left_sprites = left.get("sprites", [])
    right_sprites = right.get("sprites", [])
    if len(left_sprites) != len(right_sprites):
        return False
    for left_sprite, right_sprite in zip(left_sprites, right_sprites):
        if left_sprite.get("color") != right_sprite.get("color"):
            return False
        left_pattern = left_sprite.get("pattern", [])
        right_pattern = right_sprite.get("pattern", [])
        if left_pattern != right_pattern:
            return False
    return True


def create_empty_sprite_dict(size: int, color: int = 2) -> dict:
    return {
        "pattern": [[0 for _ in range(size)] for _ in range(size)],
        "color": color,
    }


def normalize_frame_slots(
    frame: dict, target_count: int, size: int, default_color: int = 2
) -> dict:
    """Pad or trim sprites and stack_mask to match target slot count."""
    sprites = [deep_copy_sprite(sprite) for sprite in frame.get("sprites", [])]
    mask = list(frame.get("stack_mask", []))

    if len(sprites) < target_count:
        for _ in range(target_count - len(sprites)):
            sprites.append(create_empty_sprite_dict(size, default_color))
        mask.extend([False] * (target_count - len(mask)))
    elif len(sprites) > target_count:
        sprites = sprites[:target_count]
        mask = mask[:target_count]

    frame["sprites"] = sprites
    frame["stack_mask"] = mask
    return frame


def validate_frame(frame: dict, size: int) -> bool:
    for sprite in frame.get("sprites", []):
        pattern = sprite.get("pattern", [])
        if len(pattern) != size:
            return False
        if any(len(row) != size for row in pattern):
            return False
    if len(frame.get("stack_mask", [])) != len(frame.get("sprites", [])):
        return False
    if not (1 <= frame.get("duration", 0) <= 255):
        return False
    return True


def validate_and_sanitize_animations(
    anims: list,
    size: int,
    target_slot_count: int,
    max_animations: int = MAX_ANIMATIONS,
    max_frames_per_anim: int = MAX_FRAMES_PER_ANIM,
) -> tuple[list, list[str]]:
    warnings: list[str] = []
    if len(anims) > max_animations:
        warnings.append(
            f"Animation count {len(anims)} exceeds {max_animations}; truncating."
        )
        anims = anims[:max_animations]

    for anim in anims:
        frames = anim.get("frames", [])
        if len(frames) > max_frames_per_anim:
            warnings.append(
                f"Animation '{anim.get('name')}' exceeds {max_frames_per_anim} "
                f"frames; truncating."
            )
            frames = frames[:max_frames_per_anim]

        valid_frames = []
        for index, raw_frame in enumerate(frames):
            frame = {
                "duration": raw_frame.get("duration", 4),
                "stack_enabled": raw_frame.get("stack_enabled", True),
                "stack_mask": list(raw_frame.get("stack_mask", [])),
                "sprites": deep_copy_sprites(raw_frame.get("sprites", [])),
            }
            normalize_frame_slots(frame, target_slot_count, size)
            if validate_frame(frame, size):
                valid_frames.append(frame)
            else:
                warnings.append(
                    f"Invalid frame {index} in '{anim.get('name')}'; dropped."
                )
        anim["frames"] = valid_frames

    return anims, warnings