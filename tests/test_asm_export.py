import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import tkinter as tk
from tkinter import simpledialog

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

    def test_build_asm_for_sprite_data_matches_default_shape(self):
        asm = self.editor._build_asm_for_sprite_data(self.editor.sprites[0], 0)
        self.assertIn("SPR0", asm)
        self.assertIn("; Sprite 00 8x8 Color", asm)
        self.assertIn("    BYTE >80", asm)

    def test_build_animation_asm_includes_frame_directory_and_stacked_slots_only(self):
        frame = make_frame(slots=2, duration=4)
        frame["stack_mask"] = [True, False]
        self.editor.animations = [
            {"name": "walk", "loop": True, "frames": [frame, make_frame(duration=8)]}
        ]
        asm = self.editor.build_animation_asm(0)
        self.assertIn("WALK", asm)
        self.assertIn("    BYTE >02    ; Frame count", asm)
        self.assertIn("    DATA WALK_SPR0_F00,>0004 ; Frame 0 address and duration", asm)
        self.assertIn("    DATA WALK_SPR0_F01,>0008 ; Frame 1 address and duration", asm)
        sprite_labels = [
            line for line in asm.splitlines() if line.startswith("WALK_SPR")
        ]
        self.assertEqual(sprite_labels, ["WALK_SPR0_F00", "WALK_SPR0_F01"])
        self.assertNotIn("SPR1", asm)
        self.assertNotIn("WALK_DUR:", asm)

    def test_build_animation_asm_includes_all_stacked_sprites_per_frame(self):
        frame = make_frame(slots=2, duration=4)
        frame["stack_mask"] = [True, True]
        frame["sprites"][1]["pattern"][1][1] = 1
        self.editor.animations = [
            {"name": "stacked", "loop": True, "frames": [frame]}
        ]
        asm = self.editor.build_animation_asm(0)
        self.assertIn("STACKED_SPR0_F00", asm)
        self.assertIn("STACKED_SPR1_F00", asm)
        self.assertIn("    DATA STACKED_SPR0_F00,>0004 ; Frame 0 address and duration", asm)

    def test_panel_text_shows_full_animation_in_frame_edit(self):
        frame = make_frame(slots=2, duration=6)
        frame["stack_mask"] = [True, True]
        frame["sprites"][1]["pattern"][1][1] = 1
        self.editor.animations = [
            {"name": "walk", "loop": True, "frames": [frame]}
        ]
        self.editor.current_animation = 0
        self.editor.select_anim_frame(0)
        text = self.editor._build_asm_panel_text()
        self.assertIn("WALK", text)
        self.assertIn("    BYTE >01    ; Frame count", text)
        self.assertIn("    DATA WALK_SPR0_F00,>0006 ; Frame 0 address and duration", text)
        self.assertIn("WALK_SPR0_F00", text)
        self.assertIn("WALK_SPR1_F00", text)

    def test_panel_text_shows_full_animation_in_preview(self):
        frame = make_frame(slots=2, duration=4)
        frame["stack_mask"] = [True, True]
        self.editor.animations = [
            {"name": "walk", "loop": True, "frames": [frame]}
        ]
        self.editor.current_animation = 0
        self.editor.anim_preview_running = True
        self.editor._anim_preview_index = 0
        text = self.editor._build_asm_panel_text()
        self.assertEqual(text, self.editor.build_animation_asm(0))
        self.assertIn("WALK_SPR0_F00", text)
        self.assertIn("WALK_SPR1_F00", text)

    def test_panel_text_omits_animation_header_in_static_mode(self):
        self.editor.current_animation = 0
        self.editor.animations = [
            {"name": "idle", "loop": True, "frames": [make_frame()]}
        ]
        text = self.editor._build_asm_panel_text()
        self.assertNotIn("Animation 'idle'", text)
        self.assertIn("SPR0", text)

    def test_rename_sprite_dialog_refreshes_asm_panel(self):
        editor = SpriteEditor(self.root, create_ui=True)
        editor.init_sprites(1)
        editor.rebuild_sprite_list()
        with patch.object(simpledialog, "askstring", return_value="Hero"):
            editor.rename_sprite_dialog(0)
        asm = editor.asm_text.get("1.0", "end-1c")
        self.assertIn("HERO", asm)

    def test_panel_text_includes_all_frames_during_preview(self):
        self.editor.current_animation = 0
        self.editor.animations = [
            {"name": "idle", "loop": True, "frames": [make_frame(), make_frame(duration=8)]}
        ]
        self.editor.anim_preview_running = True
        self.editor._anim_preview_index = 1
        text = self.editor._build_asm_panel_text()
        self.assertIn("IDLE", text)
        self.assertIn("    BYTE >02    ; Frame count", text)
        self.assertIn("    DATA IDLE_SPR0_F00,>0004 ; Frame 0 address and duration", text)
        self.assertIn("    DATA IDLE_SPR0_F01,>0008 ; Frame 1 address and duration", text)


if __name__ == "__main__":
    unittest.main()