import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from asm_export import render_animation, render_frame_block, render_sprite
from animation_schema import default_animation_name, default_sprite_name
from asm_format_schema import (
    get_template,
    load_format_by_id,
    list_formats,
    sanitize_label,
    validate_format,
)
from test_animation import make_frame


class AsmFormatTests(unittest.TestCase):
    def test_list_formats_loads_shipped_templates(self):
        formats = list_formats()
        ids = {format_id for format_id, _fmt in formats}
        self.assertIn("ti99_default", ids)
        self.assertNotIn("ti99_labeled", ids)
        self.assertNotIn("ti99_frame_directory", ids)
        self.assertIn("generic_db", ids)

    def test_sanitize_label(self):
        self.assertEqual(sanitize_label("walk right", case="upper"), "WALK_RIGHT")
        self.assertEqual(sanitize_label("9up", case="upper"), "L_9UP")

    def test_ti99_default_emits_frame_directory_and_sprite_labels(self):
        frame0 = make_frame(slots=1, duration=4)
        frame0["sprites"][0]["pattern"][0][0] = 1
        frame1 = make_frame(slots=1, duration=8)
        frame1["sprites"][0]["pattern"][1][0] = 1
        anim = {"name": "walk", "loop": True, "frames": [frame0, frame1]}
        fmt = load_format_by_id("ti99_default")
        asm = render_animation(anim, 8, fmt)
        self.assertEqual(
            asm.splitlines()[:3],
            [
                "WALK",
                "    BYTE >02,>01    ; Frame count, sprite count",
                "    DATA WALK_SPR0_F00,>0004 ; Frame 0 address and duration",
            ],
        )
        self.assertIn("    DATA WALK_SPR0_F01,>0008 ; Frame 1 address and duration", asm)
        self.assertIn("WALK_SPR0_F00", asm)
        self.assertIn("WALK_SPR0_F01", asm)
        self.assertIn("    BYTE >80,>00,>00,>00,>00,>00,>00,>00", asm)
        self.assertNotIn("WALK_DUR:", asm)
        self.assertNotIn("WALK_F00:", asm)

    def test_generic_db_uses_db_and_dollar_hex(self):
        frame = make_frame(slots=1, duration=4)
        frame["sprites"][0]["pattern"][0][0] = 1
        anim = {"name": "hero", "loop": True, "frames": [frame]}
        fmt = load_format_by_id("generic_db")
        asm = render_animation(anim, 8, fmt)
        self.assertIn("db $80", asm)
        self.assertNotIn("BYTE", asm)

    def test_validate_format_rejects_invalid_layout(self):
        with self.assertRaises(ValueError):
            validate_format(
                {
                    "name": "bad",
                    "layout": "unknown",
                    "dialect": {
                        "comment_prefix": ";",
                        "data_directive": "BYTE",
                        "hex_prefix": ">",
                        "value_separator": ",",
                    },
                }
            )

    def test_shipped_formats_include_required_templates(self):
        for format_id, fmt in list_formats():
            with self.subTest(format_id=format_id):
                self.assertIn("name", fmt)
                self.assertIn("templates", fmt)
                get_template(fmt, "animation")
                get_template(fmt, "sprite" if "sprite" in fmt["templates"] else "sprite_block")

    def test_ti99_default_matches_anim_header_structure(self):
        frame = make_frame(slots=1, duration=32)
        frame["sprites"][0]["pattern"][2][2] = 1
        frame["sprites"][0]["pattern"][2][3] = 1
        anim = {"name": "ANIM0", "loop": True, "frames": [frame]}
        fmt = load_format_by_id("ti99_default")
        asm = render_animation(anim, 8, fmt)
        self.assertEqual(
            asm.splitlines()[:3],
            [
                "ANIM0",
                "    BYTE >01,>01    ; Frame count, sprite count",
                "    DATA ANIM0_SPR0_F00,>0020 ; Frame 0 address and duration",
            ],
        )
        sprite_section = asm.split("\n\n", 1)[1]
        self.assertTrue(sprite_section.startswith("ANIM0_SPR0_F00\n"))
        self.assertIn("    BYTE ", sprite_section)

    def test_ti99_default_includes_sprite_count(self):
        frame0 = make_frame(slots=2, duration=4)
        frame1 = make_frame(slots=2, duration=8)
        frame0["stack_mask"] = [True, True]
        frame1["stack_mask"] = [True]
        anim = {"name": "ANIM0", "loop": True, "frames": [frame0, frame1]}
        fmt = load_format_by_id("ti99_default")
        asm = render_animation(anim, 8, fmt)
        self.assertIn(
            "    BYTE >02,>02    ; Frame count, sprite count",
            asm,
        )

    def test_ti99_default_uses_sprite_names_as_labels(self):
        frame0 = make_frame(slots=2, duration=4)
        frame1 = make_frame(slots=2, duration=8)
        frame0["sprites"][0]["name"] = "SPR0"
        frame0["sprites"][1]["name"] = "SPR1"
        frame1["sprites"][0]["name"] = "SPR0"
        frame1["sprites"][1]["name"] = "SPR1"
        anim = {"name": "ANIM0", "loop": True, "frames": [frame0, frame1]}
        fmt = load_format_by_id("ti99_default")
        asm = render_animation(anim, 8, fmt)
        labels = [line for line in asm.splitlines() if line.startswith("ANIM0_SPR")]
        self.assertEqual(
            labels,
            [
                "ANIM0_SPR0_F00",
                "ANIM0_SPR1_F00",
                "ANIM0_SPR0_F01",
                "ANIM0_SPR1_F01",
            ],
        )
        directory_lines = [
            line
            for line in asm.splitlines()
            if line.strip().startswith("DATA ")
        ]
        self.assertEqual(
            directory_lines,
            [
                "    DATA ANIM0_SPR0_F00,>0004 ; Frame 0 address and duration",
                "    DATA ANIM0_SPR0_F01,>0008 ; Frame 1 address and duration",
            ],
        )

    def test_sprite_rename_updates_export_label(self):
        frame = make_frame(slots=1, duration=4)
        frame["sprites"][0]["name"] = "Hero"
        frame["sprites"][0]["pattern"][0][0] = 1
        anim = {"name": "walk", "loop": True, "frames": [frame]}
        fmt = load_format_by_id("ti99_default")
        asm = render_animation(anim, 8, fmt)
        self.assertIn("WALK_HERO_F00", asm)
        self.assertNotIn("SPR0", asm)

    def test_ti99_default_renders_frame_block_without_frame_index(self):
        frame = make_frame(slots=1, duration=32)
        fmt = load_format_by_id("ti99_default")
        asm = render_frame_block(
            frame["sprites"],
            frame["stack_mask"],
            size=8,
            fmt=fmt,
            header_lines=["; editing frame 0"],
        )
        self.assertIn("SPR0", asm)
        self.assertIn("    BYTE ", asm)

    def test_default_sprite_name_uses_spr_prefix(self):
        self.assertEqual(default_sprite_name(0), "SPR0")
        self.assertEqual(default_sprite_name(3), "SPR3")

    def test_default_animation_name_uses_anim_prefix(self):
        self.assertEqual(default_animation_name(0), "ANIM0")
        self.assertEqual(default_animation_name(3), "ANIM3")

    def test_render_sprite_uses_format_dialect(self):
        sprite = make_frame(slots=1)["sprites"][0]
        sprite["pattern"][0][0] = 1
        fmt = load_format_by_id("generic_db")
        asm = render_sprite(sprite, 0, 8, fmt)
        self.assertIn("db $80", asm)


if __name__ == "__main__":
    unittest.main()