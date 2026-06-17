import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import tkinter as tk

from sprite import (
    FRAME_STATUS_ROW_HEIGHT,
    PREVIEW_STATUS_ROW_HEIGHT,
    SpriteEditor,
    VDP_FRAME_SEC,
)
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

    def test_preview_without_loop_returns_to_frame_edit(self):
        self.editor.animations[0]["loop"] = False
        self.editor.select_anim_frame(0)
        self.editor._preview_return_to_frame_edit = True
        self.editor.anim_preview_running = True
        self.editor._anim_preview_index = 1
        self.editor.anim_preview_frame_counter = 2
        self.editor._process_anim_preview_tick()
        self.assertFalse(self.editor.anim_preview_running)
        self.assertTrue(self.editor.anim_edit_mode)
        self.assertIsNotNone(self.editor._frame_edit_snapshot)

    def test_get_active_sprite_state_uses_preview_frame(self):
        self.editor.anim_preview_running = True
        self.editor._anim_preview_index = 1
        self.editor.animations[0]["frames"][1]["sprites"][0]["pattern"][0][0] = 1
        sprites, _ = self.editor._get_active_sprite_state()
        self.assertEqual(sprites[0]["pattern"][0][0], 1)

    def test_preview_disables_all_buttons_except_stop(self):
        editor = SpriteEditor(self.root, create_ui=True)
        editor.init_sprites(1)
        editor.stack_vars = [tk.BooleanVar(value=True)]
        editor.animations = [
            {
                "name": "walk",
                "loop": True,
                "frames": [make_frame(), make_frame()],
            }
        ]
        editor.current_animation = 0
        editor._refresh_animation_ui()
        self.root.update_idletasks()

        editor._set_preview_ui_state(False)
        self.root.update_idletasks()

        buttons = list(editor._iter_ui_buttons())
        self.assertGreater(len(buttons), 1)
        for btn in buttons:
            if btn is editor.anim_stop_btn:
                self.assertEqual(str(btn.cget("state")), str(tk.NORMAL))
            else:
                self.assertEqual(str(btn.cget("state")), str(tk.DISABLED))

        editor._set_preview_ui_state(True)
        self.root.update_idletasks()
        self.assertEqual(str(editor.anim_stop_btn.cget("state")), str(tk.DISABLED))
        self.assertEqual(str(editor.anim_play_btn.cget("state")), str(tk.NORMAL))

    def test_preview_does_not_shift_controls(self):
        editor = SpriteEditor(self.root, create_ui=True)
        editor.sprite_size_mode = 8
        editor.init_sprites(1)
        editor.stack_vars = [tk.BooleanVar(value=True)]
        editor.animations = [
            {
                "name": "walk",
                "loop": True,
                "frames": [make_frame(size=8), make_frame(size=8)],
            }
        ]
        editor.current_animation = 0
        editor._refresh_animation_ui()
        editor.select_anim_frame(0)
        self.root.geometry("1300x900")
        self.root.update()

        props_y = editor.anim_duration_spin.winfo_y()
        status_row_height = editor._anim_frame_status_row.winfo_height()
        preview_status_height = editor._anim_preview_status_row.winfo_height()
        self.assertGreaterEqual(status_row_height, FRAME_STATUS_ROW_HEIGHT - 2)
        self.assertGreaterEqual(preview_status_height, PREVIEW_STATUS_ROW_HEIGHT - 2)

        editor.start_anim_preview()
        self.root.update()

        self.assertEqual(editor.anim_duration_spin.winfo_y(), props_y)
        self.assertEqual(editor._anim_frame_status_row.winfo_height(), status_row_height)
        self.assertEqual(
            editor._anim_preview_status_row.winfo_height(), preview_status_height
        )

        editor.stop_anim_preview()
        self.root.update()
        self.assertEqual(editor.anim_duration_spin.winfo_y(), props_y)


if __name__ == "__main__":
    unittest.main()