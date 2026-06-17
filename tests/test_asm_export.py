import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import tkinter as tk

from sprite import SpriteEditor
from test_animation import make_frame


class AsmExportTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.editor = SpriteEditor(self.root, create_ui=False)
        self.editor.sprite_size_mode = 8
        self.editor.init_sprites(2)
        self.editor.sprites[0]["pattern"][0][0] = 1
        self.editor.sprites[1]["pattern"][1][1] = 1

    def tearDown(self):
        self.root.destroy()

    def test_build_asm_for_sprite_data_matches_legacy_shape(self):
        asm = self.editor._build_asm_for_sprite_data(self.editor.sprites[0], 0)
        self.assertIn("; TI-99 Sprite 00 8x8 Color", asm)
        self.assertIn("BYTE >80", asm)

    def test_build_animation_asm_includes_timing_and_stacked_slots_only(self):
        frame = make_frame(slots=2, duration=4)
        frame["stack_mask"] = [True, False]
        self.editor.animations = [
            {"name": "walk", "loop": True, "frames": [frame, make_frame(duration=8)]}
        ]
        asm = self.editor.build_animation_asm(0)
        self.assertIn("; Animation 'walk' — 2 frames", asm)
        self.assertIn("; Frame 0: duration=4 screen frames", asm)
        self.assertIn("; Durations (screen frames): 4, 8", asm)
        self.assertIn("Total cycle: 12 screen frames", asm)
        self.assertEqual(asm.count("; TI-99 Sprite 00"), 2)
        self.assertNotIn("; TI-99 Sprite 01", asm)

    def test_build_animation_asm_includes_all_stacked_sprites_per_frame(self):
        frame = make_frame(slots=2, duration=4)
        frame["stack_mask"] = [True, True]
        frame["sprites"][1]["pattern"][1][1] = 1
        self.editor.animations = [
            {"name": "stacked", "loop": True, "frames": [frame]}
        ]
        asm = self.editor.build_animation_asm(0)
        self.assertIn("; TI-99 Sprite 00", asm)
        self.assertIn("; TI-99 Sprite 01", asm)

    def test_panel_text_includes_all_stacked_sprites_in_frame_edit(self):
        frame = make_frame(slots=2, duration=6)
        frame["stack_mask"] = [True, True]
        frame["sprites"][1]["pattern"][1][1] = 1
        self.editor.animations = [
            {"name": "walk", "loop": True, "frames": [frame]}
        ]
        self.editor.current_animation = 0
        self.editor.select_anim_frame(0)
        text = self.editor._build_asm_panel_text()
        self.assertIn("; Animation 'walk' / Frame 0", text)
        self.assertIn("; TI-99 Sprite 00", text)
        self.assertIn("; TI-99 Sprite 01", text)

    def test_panel_text_includes_all_stacked_sprites_in_preview(self):
        frame = make_frame(slots=2, duration=4)
        frame["stack_mask"] = [True, True]
        self.editor.animations = [
            {"name": "walk", "loop": True, "frames": [frame]}
        ]
        self.editor.current_animation = 0
        self.editor.anim_preview_running = True
        self.editor._anim_preview_index = 0
        text = self.editor._build_asm_panel_text()
        self.assertTrue(text.startswith("; Preview frame 1/1\n"))
        self.assertIn("; TI-99 Sprite 00", text)
        self.assertIn("; TI-99 Sprite 01", text)

    def test_panel_text_adds_animation_header_in_static_mode(self):
        self.editor.current_animation = 0
        self.editor.animations = [
            {"name": "idle", "loop": True, "frames": [make_frame()]}
        ]
        text = self.editor._build_asm_panel_text()
        self.assertTrue(text.startswith("; Animation 'idle' (1 frames)\n"))

    def test_panel_text_adds_preview_header(self):
        self.editor.current_animation = 0
        self.editor.animations = [
            {"name": "idle", "loop": True, "frames": [make_frame(), make_frame()]}
        ]
        self.editor.anim_preview_running = True
        self.editor._anim_preview_index = 1
        text = self.editor._build_asm_panel_text()
        self.assertTrue(text.startswith("; Preview frame 2/2\n"))


if __name__ == "__main__":
    unittest.main()