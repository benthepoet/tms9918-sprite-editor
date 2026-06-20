import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import tkinter as tk

from animation_schema import deep_copy_frame
from sprite import ANIM_EDIT_APP_BG, PANEL_TEXT_BG, SpriteEditor
from test_animation import make_frame


class FrameEditTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.editor = SpriteEditor(self.root, create_ui=False)
        self.editor.init_sprites(1)
        self.editor.animations = [
            {"name": "walk", "loop": True, "frames": [make_frame(), make_frame(duration=8)]}
        ]
        self.editor.current_animation = 0
        self.editor.stack_vars = [tk.BooleanVar(value=True)]

    def tearDown(self):
        self.root.destroy()

    def test_select_anim_frame_enters_edit_mode(self):
        self.editor.select_anim_frame(0)
        self.assertTrue(self.editor.anim_edit_mode)
        self.assertIsNotNone(self.editor._frame_edit_snapshot)

    def test_frame_edit_disables_stack_checkboxes_and_forces_stacked(self):
        editor = SpriteEditor(self.root, create_ui=True)
        editor.sprite_size_mode = 8
        editor.init_sprites(2)
        editor.stack_vars = [
            tk.BooleanVar(value=True),
            tk.BooleanVar(value=False),
        ]
        editor.animations = [
            {
                "name": "walk",
                "loop": True,
                "frames": [make_frame(size=8, slots=2)],
            }
        ]
        editor.animations[0]["frames"][0]["stack_mask"] = [True, False]
        editor.current_animation = 0
        editor.select_anim_frame(0)
        checkboxes = [
            child
            for row in editor._sprite_slot_rows
            for child in row.winfo_children()
            if isinstance(child, tk.Checkbutton)
        ]
        self.assertEqual(len(checkboxes), 2)
        for checkbox in checkboxes:
            self.assertEqual(str(checkbox.cget("state")), "disabled")
        self.assertEqual(editor._frame_edit_snapshot["stack_mask"], [True, True])

    def test_commit_on_frame_switch(self):
        self.editor.select_anim_frame(0)
        self.editor._frame_edit_snapshot["sprites"][0]["pattern"][0][0] = 1
        self.editor.commit_anim_frame()
        self.editor.select_anim_frame(1)
        self.assertEqual(
            self.editor.animations[0]["frames"][0]["sprites"][0]["pattern"][0][0], 1
        )

    def test_frame_edit_dirty_detection(self):
        self.editor.select_anim_frame(0)
        self.assertFalse(self.editor._frame_edit_is_dirty())
        self.editor._frame_edit_snapshot["sprites"][0]["pattern"][1][1] = 1
        self.assertTrue(self.editor._frame_edit_is_dirty())

    def test_discard_restores_committed_frame_without_leaving_edit(self):
        self.editor.select_anim_frame(0)
        original = self.editor.animations[0]["frames"][0]["sprites"][0]["pattern"][0][0]
        self.editor._frame_edit_snapshot["sprites"][0]["pattern"][0][0] = 1
        self.editor.discard_anim_frame_edits()
        self.assertTrue(self.editor.anim_edit_mode)
        self.assertFalse(self.editor._frame_edit_is_dirty())
        self.assertEqual(
            self.editor._frame_edit_snapshot["sprites"][0]["pattern"][0][0], original
        )

    def test_commit_frame_stays_in_edit_mode(self):
        self.editor.select_anim_frame(0)
        self.editor._frame_edit_snapshot["sprites"][0]["pattern"][0][0] = 1
        self.editor.commit_anim_frame_edits()
        self.assertTrue(self.editor.anim_edit_mode)
        self.assertFalse(self.editor._frame_edit_is_dirty())
        self.assertEqual(
            self.editor.animations[0]["frames"][0]["sprites"][0]["pattern"][0][0], 1
        )

    def test_cancel_discards_uncommitted_edits(self):
        self.editor.select_anim_frame(0)
        original = self.editor.animations[0]["frames"][0]["sprites"][0]["pattern"][0][0]
        self.editor._frame_edit_snapshot["sprites"][0]["pattern"][0][0] = 1
        self.editor.cancel_animation_mode()
        self.assertFalse(self.editor.anim_edit_mode)
        self.assertEqual(
            self.editor.animations[0]["frames"][0]["sprites"][0]["pattern"][0][0],
            original,
        )

    def test_capture_frame_appends_from_static_state(self):
        self.editor.sprites[0]["pattern"][0][0] = 1
        self.editor.add_anim_frame()
        self.assertEqual(len(self.editor.animations[0]["frames"]), 3)
        self.assertTrue(self.editor.anim_edit_mode)

    def test_capture_frame_copies_only_stacked_sprites(self):
        self.editor.init_sprites(3)
        self.editor.stack_vars = [
            tk.BooleanVar(value=True),
            tk.BooleanVar(value=True),
            tk.BooleanVar(value=False),
        ]
        self.editor.sprites[0]["pattern"][0][0] = 1
        self.editor.sprites[1]["pattern"][1][1] = 1
        self.editor.sprites[2]["pattern"][2][2] = 1
        self.editor.current_sprite = 2
        self.editor.add_anim_frame()
        frame = self.editor.animations[0]["frames"][-1]
        self.assertEqual(len(frame["sprites"]), 2)
        self.assertEqual(frame["sprites"][0]["pattern"][0][0], 1)
        self.assertEqual(frame["sprites"][1]["pattern"][1][1], 1)
        self.assertEqual(frame["stack_mask"], [True, True])

    @patch("sprite.messagebox.showerror")
    def test_capture_frame_requires_stacked_sprite(self, showerror):
        self.editor.init_sprites(3)
        self.editor.stack_vars = [
            tk.BooleanVar(value=False),
            tk.BooleanVar(value=False),
            tk.BooleanVar(value=False),
        ]
        self.editor.sprites[2]["pattern"][2][2] = 1
        self.editor.current_sprite = 2
        initial_frames = len(self.editor.animations[0]["frames"])
        self.editor.add_anim_frame()
        showerror.assert_called_once()
        self.assertEqual(len(self.editor.animations[0]["frames"]), initial_frames)

    def test_capture_frame_does_not_recurse_with_ui(self):
        editor = SpriteEditor(self.root, create_ui=True)
        editor.sprite_size_mode = 8
        editor.init_sprites(1)
        editor.stack_vars = [tk.BooleanVar(value=True)]
        editor.animations = [
            {"name": "walk", "loop": True, "frames": [make_frame(size=8)]}
        ]
        editor.current_animation = 0
        editor._refresh_animation_ui()

        calls = []
        original = editor.select_anim_frame

        def tracked(index):
            calls.append(index)
            if len(calls) > 5:
                raise RecursionError("select_anim_frame recursion")
            return original(index)

        editor.select_anim_frame = tracked
        editor.add_anim_frame()
        self.root.update_idletasks()
        self.assertEqual(len(calls), 1)
        self.assertEqual(editor.current_anim_frame, 1)
        self.assertTrue(editor.anim_edit_mode)

    def test_capture_frame_while_editing_loads_new_frame(self):
        self.editor.select_anim_frame(0)
        self.editor._frame_edit_snapshot["sprites"][0]["pattern"][0][0] = 1
        self.editor.add_anim_frame()
        self.assertEqual(self.editor.current_anim_frame, 2)
        self.assertTrue(self.editor.anim_edit_mode)
        self.assertEqual(
            self.editor.animations[0]["frames"][0]["sprites"][0]["pattern"][0][0], 1
        )
        self.assertEqual(
            self.editor._frame_edit_snapshot["sprites"][0]["pattern"][0][0], 1
        )

    def test_rename_animation_enforces_unique_names(self):
        self.editor.animations.append(
            {"name": "run", "loop": True, "frames": []}
        )
        with self.assertRaises(ValueError):
            self.editor.rename_animation(0, "run")

    def test_duration_written_to_snapshot(self):
        self.editor.select_anim_frame(0)
        self.editor.anim_duration_var = tk.IntVar(value=4)
        self.editor.anim_duration_var.set(12)
        self.editor._on_duration_changed()
        self.assertEqual(self.editor._frame_edit_snapshot["duration"], 12)

    def test_duration_change_updates_frame_list_label(self):
        editor = SpriteEditor(self.root, create_ui=True)
        editor.sprite_size_mode = 8
        editor.init_sprites(1)
        editor.stack_vars = [tk.BooleanVar(value=True)]
        editor.animations = [
            {
                "name": "walk",
                "loop": True,
                "frames": [make_frame(size=8), make_frame(size=8, duration=8)],
            }
        ]
        editor.current_animation = 0
        editor.select_anim_frame(0)
        editor.anim_duration_var.set(12)
        editor._apply_duration_from_spinbox()
        labels = editor.anim_frame_list.get(0, tk.END)
        self.assertEqual(labels[0], "Frame 0 (12 sf)")
        self.assertEqual(labels[1], "Frame 1 (8 sf)")

    def test_mode_indicator_shows_frame_edit_vs_static(self):
        editor = SpriteEditor(self.root, create_ui=True)
        editor.sprite_size_mode = 8
        editor.init_sprites(1)
        editor.stack_vars = [tk.BooleanVar(value=True)]
        editor.animations = [
            {"name": "walk", "loop": True, "frames": [make_frame(size=8)]}
        ]
        editor.current_animation = 0
        editor.update_status()
        self.assertIn("STATIC EDIT", editor.mode_indicator.cget("text"))
        self.assertEqual(editor.sprites_panel.cget("text"), "Project Sprites")
        static_bg = editor.root.cget("bg")

        editor.select_anim_frame(0)
        self.assertIn("FRAME EDIT", editor.mode_indicator.cget("text"))
        self.assertIn("walk", editor.mode_indicator.cget("text"))
        self.assertEqual(editor.sprites_panel.cget("text"), "Frame Sprites")
        self.assertEqual(editor.root.cget("bg"), ANIM_EDIT_APP_BG)
        self.assertEqual(editor.asm_text.cget("bg"), PANEL_TEXT_BG)
        self.assertEqual(editor.anim_frame_list.cget("bg"), PANEL_TEXT_BG)

        editor.exit_animation_mode()
        self.root.update_idletasks()
        self.assertIn("STATIC EDIT", editor.mode_indicator.cget("text"))
        self.assertEqual(editor.sprites_panel.cget("text"), "Project Sprites")
        self.assertEqual(editor.root.cget("bg"), static_bg)
        self.assertEqual(editor.asm_text.cget("bg"), PANEL_TEXT_BG)
        self.assertEqual(editor.anim_frame_list.cget("bg"), PANEL_TEXT_BG)

    def test_exit_animation_mode_without_selecting_sprite(self):
        editor = SpriteEditor(self.root, create_ui=True)
        editor.sprite_size_mode = 8
        editor.init_sprites(1)
        editor.stack_vars = [tk.BooleanVar(value=True)]
        editor.animations = [
            {"name": "walk", "loop": True, "frames": [make_frame(size=8)]}
        ]
        editor.current_animation = 0
        editor._refresh_animation_ui()
        editor.select_anim_frame(0)
        editor.exit_animation_mode()
        self.root.update_idletasks()
        self.root.update()
        self.assertFalse(editor.anim_edit_mode)
        self.assertIsNone(editor._frame_edit_snapshot)


if __name__ == "__main__":
    unittest.main()