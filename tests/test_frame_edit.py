import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import tkinter as tk

from animation_schema import deep_copy_frame
from sprite import SpriteEditor
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
        self.editor.stack_enabled = tk.BooleanVar(value=True)

    def tearDown(self):
        self.root.destroy()

    def test_select_anim_frame_enters_edit_mode(self):
        self.editor.select_anim_frame(0)
        self.assertTrue(self.editor.anim_edit_mode)
        self.assertIsNotNone(self.editor._frame_edit_snapshot)

    def test_commit_on_frame_switch(self):
        self.editor.select_anim_frame(0)
        self.editor._frame_edit_snapshot["sprites"][0]["pattern"][0][0] = 1
        self.editor.select_anim_frame(1)
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

    def test_capture_frame_does_not_recurse_with_ui(self):
        editor = SpriteEditor(self.root, create_ui=True)
        editor.init_sprites(1)
        editor.animations = [
            {"name": "walk", "loop": True, "frames": [make_frame()]}
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


if __name__ == "__main__":
    unittest.main()