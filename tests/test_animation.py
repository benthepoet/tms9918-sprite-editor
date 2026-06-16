import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import tkinter as tk

from animation_schema import (
    deep_copy_frame,
    deep_copy_sprite,
    normalize_frame_slots,
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

    def test_validate_and_sanitize_drops_invalid_frame(self):
        anims = [{"name": "test", "loop": True, "frames": [make_frame(), {"duration": 0}]}]
        result, warnings = validate_and_sanitize_animations(anims, 8, 1)
        self.assertEqual(len(result[0]["frames"]), 1)
        self.assertTrue(any("dropped" in warning for warning in warnings))

    def test_validate_and_sanitize_truncates_animation_count(self):
        anims = [{"name": f"a{i}", "loop": True, "frames": []} for i in range(40)]
        result, warnings = validate_and_sanitize_animations(anims, 8, 1, max_animations=32)
        self.assertEqual(len(result), 32)
        self.assertTrue(any("truncating" in warning for warning in warnings))


class SpriteEditorAnimationTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.editor = SpriteEditor(self.root, create_ui=False)

    def tearDown(self):
        self.root.destroy()

    def test_remove_slot_at_index_middle(self):
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
            self.assertEqual(len(frame["sprites"]), 2)
            self.assertEqual(len(frame["stack_mask"]), 2)

    def test_sync_all_animation_slot_counts_on_add(self):
        self.editor.init_sprites(1)
        self.editor.animations = [
            {"name": "idle", "loop": True, "frames": [make_frame(slots=1)]}
        ]
        self.editor.sprites.append(self.editor.create_empty_sprite())
        self.editor._sync_all_animation_slot_counts()
        self.assertEqual(len(self.editor.animations[0]["frames"][0]["sprites"]), 2)

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

    def test_v2_json_round_trip(self):
        self.editor.sprite_size_mode = 8
        self.editor.sprites = [{"pattern": [[0] * 8 for _ in range(8)], "color": 2}]
        self.editor.animations = [
            {"name": "blink", "loop": True, "frames": [make_frame()]}
        ]
        payload = {
            "version": 2,
            "mode": self.editor.sprite_size_mode,
            "sprites": self.editor.sprites,
            "animations": json.loads(json.dumps(self.editor.animations)),
        }
        other = SpriteEditor(tk.Tk(), create_ui=False)
        try:
            warnings = other.load_project_data(payload)
            self.assertEqual(len(other.animations), 1)
            self.assertEqual(other.animations[0]["name"], "blink")
            self.assertEqual(len(other.animations[0]["frames"]), 1)
            self.assertEqual(warnings, [])
        finally:
            other.root.destroy()


if __name__ == "__main__":
    unittest.main()