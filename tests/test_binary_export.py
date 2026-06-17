import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import tkinter as tk

from binary_export import (
    encode_animation_binary,
    encode_panel_binary,
    pattern_to_bytes,
)
from sprite import SpriteEditor
from test_animation import make_frame


class BinaryExportTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.editor = SpriteEditor(self.root, create_ui=False)
        self.editor.sprite_size_mode = 8
        self.editor.init_sprites(2)
        self.editor.sprites[0]["pattern"][0][0] = 1
        self.editor.sprites[0]["color"] = 2
        self.editor.sprites[1]["pattern"][1][1] = 1
        self.editor.sprites[1]["color"] = 4

    def tearDown(self):
        self.root.destroy()

    def test_pattern_to_bytes_matches_asm_export(self):
        asm_bytes = self.editor._pattern_to_bytes(self.editor.sprites[0]["pattern"], 8)
        self.assertEqual(
            asm_bytes, list(pattern_to_bytes(self.editor.sprites[0]["pattern"], 8))
        )
        self.assertEqual(asm_bytes[0], 0x80)

    def test_encode_panel_binary_is_raw_pattern_bytes_only(self):
        data = encode_panel_binary(8, [(0, self.editor.sprites[0])])
        self.assertEqual(
            data, pattern_to_bytes(self.editor.sprites[0]["pattern"], 8)
        )
        self.assertEqual(len(data), 8)

    def test_encode_panel_binary_concatenates_stacked_sprites(self):
        data = encode_panel_binary(
            8, [(0, self.editor.sprites[0]), (1, self.editor.sprites[1])]
        )
        self.assertEqual(
            data,
            pattern_to_bytes(self.editor.sprites[0]["pattern"], 8)
            + pattern_to_bytes(self.editor.sprites[1]["pattern"], 8),
        )
        self.assertEqual(len(data), 16)

    def test_get_panel_export_slots_static_mode(self):
        self.editor.current_sprite = 1
        slots = self.editor._get_panel_export_slots()
        self.assertEqual(len(slots), 1)
        self.assertEqual(slots[0][0], 1)
        self.assertEqual(slots[0][1]["pattern"][1][1], 1)

    def test_get_panel_export_slots_frame_edit(self):
        frame = make_frame(slots=2, duration=6)
        frame["stack_mask"] = [True, True]
        frame["sprites"][1]["pattern"][1][1] = 1
        self.editor.animations = [
            {"name": "walk", "loop": True, "frames": [frame]}
        ]
        self.editor.current_animation = 0
        self.editor.select_anim_frame(0)
        slots = self.editor._get_panel_export_slots()
        self.assertEqual(len(slots), 2)
        self.assertEqual(slots[0][0], 0)
        self.assertEqual(slots[1][0], 1)

    def test_encode_animation_binary_is_raw_pattern_bytes_only(self):
        frame = make_frame(slots=2, duration=4)
        frame["stack_mask"] = [True, False]
        animation = {
            "name": "walk",
            "loop": True,
            "frames": [frame, make_frame(duration=8)],
        }
        data = encode_animation_binary(8, animation)
        self.assertEqual(
            data,
            pattern_to_bytes(frame["sprites"][0]["pattern"], 8)
            + pattern_to_bytes(animation["frames"][1]["sprites"][0]["pattern"], 8),
        )
        self.assertEqual(len(data), 16)


if __name__ == "__main__":
    unittest.main()