import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import tkinter as tk

from sprite import CANVAS_BG, CANVAS_GRID_OUTLINE, CANVAS_OFF_PIXEL, SpriteEditor


class RecordCanvas:
    def __init__(self):
        self.rectangles = []

    def delete(self, *_args, **_kwargs):
        self.rectangles.clear()

    def create_rectangle(self, x1, y1, x2, y2, **kwargs):
        self.rectangles.append((x1, y1, x2, y2, kwargs))


class RenderTests(unittest.TestCase):
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
        self.editor.current_sprite = 1

    def tearDown(self):
        self.root.destroy()

    def _mask(self, values):
        return list(values)

    def test_resolve_stack_indices_follows_list_order(self):
        indices = self.editor._resolve_stack_indices(
            [True, False, True], True, 0
        )
        self.assertEqual(indices, [0, 2])

    def test_resolve_stack_indices_single_mode(self):
        indices = self.editor._resolve_stack_indices([False, False], False, 1)
        self.assertEqual(indices, [1])

    def test_get_active_sprite_state_injects_current_sprite(self):
        mask = self._mask([True, False])
        self.editor.stack_enabled = tk.BooleanVar(value=True)
        self.editor.stack_vars = [tk.BooleanVar(value=value) for value in mask]
        _, _, resolved_mask = self.editor._get_active_sprite_state()
        self.assertTrue(resolved_mask[1])

    def test_render_single_sprite_draws_off_pixels(self):
        canvas = RecordCanvas()
        sprites = self.editor.sprites
        self.editor._render_composite(
            canvas,
            sprites,
            False,
            [True, False],
            0,
            pixel_size=10,
            draw_off_pixels=True,
            transparent_color="#aaaaaa",
            outline="#666666",
        )
        self.assertEqual(len(canvas.rectangles), 128)
        overlay = canvas.rectangles[64:]
        off_pixels = [rect for rect in overlay if rect[4]["fill"] == CANVAS_OFF_PIXEL]
        on_pixels = [rect for rect in overlay if rect[4]["fill"] != CANVAS_OFF_PIXEL]
        self.assertEqual(len(off_pixels), 63)
        self.assertEqual(len(on_pixels), 1)

    def test_render_stacked_includes_injected_current_sprite(self):
        canvas = RecordCanvas()
        sprites = self.editor.sprites
        stack_mask = [True, False]
        stack_mask[self.editor.current_sprite] = True
        self.editor._render_composite(
            canvas,
            sprites,
            True,
            stack_mask,
            self.editor.current_sprite,
            pixel_size=10,
            draw_off_pixels=False,
            transparent_color="#aaaaaa",
            outline="#666666",
        )
        self.assertEqual(len(canvas.rectangles), 66)
        on_pixels = [rect for rect in canvas.rectangles if rect[4]["fill"] != CANVAS_BG]
        fills = {rect[4]["fill"] for rect in on_pixels}
        self.assertEqual(len(on_pixels), 2)
        self.assertEqual(len(fills), 2)

    def test_render_stacked_draws_grid_before_pixels(self):
        canvas = RecordCanvas()
        empty_sprite = {"pattern": [[0] * 8 for _ in range(8)], "color": 2}
        self.editor._render_composite(
            canvas,
            [empty_sprite],
            True,
            [True],
            0,
            pixel_size=10,
            transparent_color="#aaaaaa",
        )
        self.assertEqual(len(canvas.rectangles), 64)
        self.assertTrue(
            all(rect[4]["outline"] == CANVAS_GRID_OUTLINE for rect in canvas.rectangles)
        )

    def test_preview_render_uses_empty_outline(self):
        canvas = RecordCanvas()
        self.editor.stack_enabled = tk.BooleanVar(value=False)
        self.editor.stack_vars = [tk.BooleanVar(value=True) for _ in self.editor.sprites]
        sprites, stack_enabled, stack_mask = self.editor._get_active_sprite_state()
        self.editor._render_composite(
            canvas,
            sprites,
            stack_enabled,
            stack_mask,
            self.editor.current_sprite,
            pixel_size=20,
            draw_off_pixels=False,
            transparent_color="#000000",
            outline="",
        )
        self.assertTrue(all(rect[4]["outline"] == "" for rect in canvas.rectangles))


if __name__ == "__main__":
    unittest.main()