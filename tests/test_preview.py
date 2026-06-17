import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import tkinter as tk

from sprite import SpriteEditor, VDP_FRAME_SEC
from test_animation import make_frame


class PreviewEngineTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.editor = SpriteEditor(self.root, create_ui=False)
        self.editor.init_sprites(1)
        self.editor.current_animation = 0
        self.editor.animations = [
            {
                "name": "walk",
                "loop": True,
                "frames": [
                    make_frame(duration=2),
                    make_frame(duration=3),
                ],
            }
        ]

    def tearDown(self):
        self.editor.stop_anim_preview_timer_only()
        self.root.destroy()

    def test_vdp_frame_interval(self):
        self.assertAlmostEqual(VDP_FRAME_SEC, 1.0 / 59.94, places=6)

    def test_preview_holds_frame_until_duration(self):
        self.editor.anim_preview_running = True
        self.editor._anim_preview_index = 0
        self.editor.anim_preview_frame_counter = 0
        self.assertTrue(self.editor._process_anim_preview_tick())
        self.assertEqual(self.editor._anim_preview_index, 0)
        self.assertEqual(self.editor.anim_preview_frame_counter, 1)
        self.assertTrue(self.editor._process_anim_preview_tick())
        self.assertEqual(self.editor._anim_preview_index, 1)
        self.assertEqual(self.editor.anim_preview_frame_counter, 0)

    def test_preview_loops_to_frame_zero(self):
        self.editor.anim_preview_running = True
        self.editor._anim_preview_index = 1
        self.editor.anim_preview_frame_counter = 2
        self.assertTrue(self.editor._process_anim_preview_tick())
        self.assertEqual(self.editor._anim_preview_index, 0)

    def test_preview_stops_when_loop_disabled(self):
        self.editor.animations[0]["loop"] = False
        self.editor.anim_preview_running = True
        self.editor._anim_preview_index = 1
        self.editor.anim_preview_frame_counter = 2
        self.assertFalse(self.editor._process_anim_preview_tick())
        self.assertFalse(self.editor.anim_preview_running)

    def test_get_active_sprite_state_uses_preview_frame(self):
        self.editor.anim_preview_running = True
        self.editor._anim_preview_index = 1
        self.editor.animations[0]["frames"][1]["sprites"][0]["pattern"][0][0] = 1
        sprites, _ = self.editor._get_active_sprite_state()
        self.assertEqual(sprites[0]["pattern"][0][0], 1)


if __name__ == "__main__":
    unittest.main()