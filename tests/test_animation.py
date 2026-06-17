import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import tkinter as tk

from animation_schema import (
    compact_frame_slots,
    deep_copy_frame,
    deep_copy_sprite,
    default_sprite_name,
    ensure_sprite_names,
    frames_equal,
    normalize_frame_slots,
    sprite_display_name,
    validate_and_sanitize_animations,
    validate_frame,
)
from sprite import SpriteEditor


def make_frame(size=8, slots=1, duration=4):
    sprite = {
        "pattern": [[1 if x == 0 and y == 0 else 0 for x in range(size)] for y in range(size)],
        "color": 2,
    }
    return {
        "duration": duration,
        "stack_enabled": True,
        "stack_mask": [True] * slots,
        "sprites": [deep_copy_sprite(sprite) for _ in range(slots)],
    }


class AnimationSchemaTests(unittest.TestCase):
    def test_validate_frame_accepts_valid_frame(self):
        self.assertTrue(validate_frame(make_frame(), 8))

    def test_validate_frame_rejects_bad_duration(self):
        frame = make_frame()
        frame["duration"] = 0
        self.assertFalse(validate_frame(frame, 8))

    def test_validate_frame_rejects_mask_length_mismatch(self):
        frame = make_frame(slots=2)
        frame["stack_mask"] = [True]
        self.assertFalse(validate_frame(frame, 8))

    def test_normalize_frame_slots_pads(self):
        frame = make_frame(slots=1)
        normalize_frame_slots(frame, target_count=3, size=8)
        self.assertEqual(len(frame["sprites"]), 3)
        self.assertEqual(len(frame["stack_mask"]), 3)
        self.assertEqual(frame["stack_mask"][2], False)

    def test_normalize_frame_slots_trims(self):
        frame = make_frame(slots=3)
        normalize_frame_slots(frame, target_count=1, size=8)
        self.assertEqual(len(frame["sprites"]), 1)
        self.assertEqual(len(frame["stack_mask"]), 1)

    def test_deep_copy_frame_is_independent(self):
        frame = make_frame()
        copy = deep_copy_frame(frame)
        copy["sprites"][0]["pattern"][0][0] = 0
        self.assertEqual(frame["sprites"][0]["pattern"][0][0], 1)

    def test_frames_equal_detects_sprite_changes(self):
        left = make_frame()
        right = deep_copy_frame(left)
        self.assertTrue(frames_equal(left, right))
        right["sprites"][0]["pattern"][0][0] = 0
        self.assertFalse(frames_equal(left, right))

    def test_deep_copy_sprite_preserves_name(self):
        sprite = {"pattern": [[0]], "color": 2, "name": "Hero"}
        copy = deep_copy_sprite(sprite)
        self.assertEqual(copy["name"], "Hero")

    def test_ensure_sprite_names_fills_missing_names(self):
        sprites = [{"pattern": [[0]], "color": 2}]
        ensure_sprite_names(sprites)
        self.assertEqual(sprites[0]["name"], default_sprite_name(0))

    def test_sprite_display_name_uses_default_when_blank(self):
        sprite = {"pattern": [[0]], "color": 2, "name": "  "}
        self.assertEqual(sprite_display_name(sprite, 3), default_sprite_name(3))

    def test_compact_frame_slots_keeps_only_stacked_sprites(self):
        frame = make_frame(slots=3)
        frame["stack_mask"] = [True, True, False]
        compacted = compact_frame_slots(frame, 8)
        self.assertEqual(len(compacted["sprites"]), 2)
        self.assertEqual(compacted["stack_mask"], [True, True])

    def test_validate_and_sanitize_drops_invalid_frame(self):
        anims = [{"name": "test", "loop": True, "frames": [make_frame(), {"duration": 0}]}]
        result, warnings = validate_and_sanitize_animations(anims, 8)
        self.assertEqual(len(result[0]["frames"]), 1)
        self.assertTrue(any("dropped" in warning for warning in warnings))

    def test_validate_and_sanitize_truncates_animation_count(self):
        anims = [{"name": f"a{i}", "loop": True, "frames": []} for i in range(40)]
        result, warnings = validate_and_sanitize_animations(anims, 8, max_animations=32)
        self.assertEqual(len(result), 32)
        self.assertTrue(any("truncating" in warning for warning in warnings))


class SpriteEditorAnimationTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.editor = SpriteEditor(self.root, create_ui=False)

    def tearDown(self):
        self.root.destroy()

    def test_remove_slot_at_index_middle_only_affects_static_sprites(self):
        self.editor.init_sprites(3)
        self.editor.animations = [
            {
                "name": "walk",
                "loop": True,
                "frames": [make_frame(slots=3), make_frame(slots=3)],
            }
        ]
        self.editor._remove_slot_at_index(1)
        self.assertEqual(len(self.editor.sprites), 2)
        for frame in self.editor.animations[0]["frames"]:
            self.assertEqual(len(frame["sprites"]), 3)
            self.assertEqual(len(frame["stack_mask"]), 3)

    def test_sprite_order_buttons_follow_selection(self):
        editor = SpriteEditor(self.root, create_ui=True)
        editor.init_sprites(2)
        editor.rebuild_sprite_list()
        editor.select_sprite_index(0)
        self.assertEqual(str(editor._sprite_move_up_btn.cget("state")), "disabled")
        self.assertEqual(str(editor._sprite_move_down_btn.cget("state")), "normal")
        editor.select_sprite_index(1)
        self.assertEqual(str(editor._sprite_move_up_btn.cget("state")), "normal")
        self.assertEqual(str(editor._sprite_move_down_btn.cget("state")), "disabled")

    def test_move_sprite_reorders_static_sprites(self):
        self.editor.init_sprites(2)
        self.editor.sprites[0]["name"] = "Bottom"
        self.editor.sprites[1]["name"] = "Top"
        self.editor.current_sprite = 0
        self.editor.move_sprite(1)
        self.assertEqual(self.editor.sprites[0]["name"], "Top")
        self.assertEqual(self.editor.sprites[1]["name"], "Bottom")
        self.assertEqual(self.editor.current_sprite, 1)

    def test_move_sprite_reorders_frame_sprites_only(self):
        self.editor.init_sprites(1)
        self.editor.animations = [
            {"name": "idle", "loop": True, "frames": [make_frame(slots=2)]}
        ]
        self.editor.animations[0]["frames"][0]["sprites"][0]["name"] = "Back"
        self.editor.animations[0]["frames"][0]["sprites"][1]["name"] = "Front"
        self.editor.current_animation = 0
        self.editor.select_anim_frame(0)
        self.editor.current_sprite = 0
        self.editor.move_sprite(1)
        snapshot = self.editor._frame_edit_snapshot
        self.assertEqual(snapshot["sprites"][0]["name"], "Front")
        self.assertEqual(snapshot["sprites"][1]["name"], "Back")
        self.assertEqual(len(self.editor.sprites), 1)

    def test_add_sprite_in_frame_edit_does_not_change_static_sprites(self):
        self.editor.init_sprites(1)
        self.editor.animations = [
            {"name": "idle", "loop": True, "frames": [make_frame(slots=1)]}
        ]
        self.editor.current_animation = 0
        self.editor.select_anim_frame(0)
        self.editor.add_sprite()
        self.assertEqual(len(self.editor.sprites), 1)
        self.assertEqual(len(self.editor._frame_edit_snapshot["sprites"]), 2)

    def test_reset_animation_state_clears_edit_flags(self):
        self.editor.anim_edit_mode = True
        self.editor._frame_edit_snapshot = make_frame()
        self.editor._static_stack_mask = [True]
        self.editor._reset_animation_state()
        self.assertFalse(self.editor.anim_edit_mode)
        self.assertIsNone(self.editor._frame_edit_snapshot)
        self.assertIsNone(self.editor._static_stack_mask)

    def test_v1_json_load_has_no_animations(self):
        data = {
            "mode": 8,
            "sprites": [{"pattern": [[0] * 8 for _ in range(8)], "color": 2}],
        }
        warnings = self.editor.load_project_data(data)
        self.assertEqual(self.editor.animations, [])
        self.assertEqual(warnings, [])
        self.assertEqual(self.editor.sprites[0]["name"], default_sprite_name(0))

    def test_rename_sprite_updates_project_sprite(self):
        self.editor.init_sprites(2)
        self.editor.rename_sprite(1, "Shield")
        self.assertEqual(self.editor.sprites[1]["name"], "Shield")
        self.assertEqual(self.editor._sprite_display_name(1), "Shield")

    def test_sprite_names_persist_in_save_payload(self):
        self.editor.init_sprites(1)
        self.editor.rename_sprite(0, "Player")
        payload = self.editor._build_project_data()
        self.assertEqual(payload["sprites"][0]["name"], "Player")

    def test_v2_json_round_trip(self):
        self.editor.sprite_size_mode = 8
        self.editor.sprites = [{"pattern": [[0] * 8 for _ in range(8)], "color": 2}]
        self.editor.animations = [
            {"name": "blink", "loop": True, "frames": [make_frame()]}
        ]
        self.editor.current_animation = 0
        payload = self.editor._build_project_data()
        other = SpriteEditor(tk.Tk(), create_ui=False)
        try:
            warnings = other.load_project_data(payload)
            self.assertEqual(len(other.animations), 1)
            self.assertEqual(other.animations[0]["name"], "blink")
            self.assertEqual(len(other.animations[0]["frames"]), 1)
            self.assertEqual(other.current_animation, 0)
            self.assertEqual(warnings, [])
        finally:
            other.root.destroy()

    def test_save_commits_uncommitted_frame_edits(self):
        self.editor.sprite_size_mode = 8
        self.editor.init_sprites(1)
        self.editor.stack_vars = [tk.BooleanVar(value=True)]
        frame = make_frame(size=8)
        frame["sprites"][0]["pattern"][0][0] = 0
        self.editor.animations = [
            {"name": "walk", "loop": True, "frames": [frame]}
        ]
        self.editor.current_animation = 0
        self.editor.select_anim_frame(0)
        self.editor._frame_edit_snapshot["sprites"][0]["pattern"][0][0] = 1
        payload = self.editor._build_project_data()
        self.assertEqual(
            payload["animations"][0]["frames"][0]["sprites"][0]["pattern"][0][0], 1
        )

    def test_load_restores_animation_selection_in_ui(self):
        editor = SpriteEditor(self.root, create_ui=True)
        editor.sprite_size_mode = 8
        editor.sprites = [{"pattern": [[0] * 8 for _ in range(8)], "color": 2}]
        editor.animations = [
            {"name": "walk", "loop": True, "frames": [make_frame(size=8)]}
        ]
        editor.current_animation = 0
        payload = editor._build_project_data()
        editor.load_project_data(payload)
        self.assertEqual(editor.current_animation, 0)
        self.assertEqual(editor.anim_combo.get(), "walk")


if __name__ == "__main__":
    unittest.main()