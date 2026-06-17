# TMS9918 Sprite Editor

A desktop sprite editor for the [TMS9918](https://en.wikipedia.org/wiki/TMS9918) VDP — create 8×8 and 16×16 sprite patterns in the authentic 16-color palette, layer multiple sprites with per-slot stacking, build animations with VDP-timed preview, and export patterns as assembly `BYTE` directives or raw binary. Commonly used for [TI-99/4A](https://en.wikipedia.org/wiki/TI-99/4A) development and other TMS9918-based systems.

Built with Python and Tkinter — no extra dependencies required.

## Features

- **TMS9918 palette** — All 16 VDP colors, including transparent
- **8×8 and 16×16 modes** — Switch sprite size from the Mode menu (clears sprites and animations)
- **Named sprite slots** — Default names `SPR0`, `SPR1`, …; double-click a slot name to rename
- **Stacked editing** — Composite checked sprite layers on the canvas; control stacking per sprite
- **Sprite reordering** — ↑↓ buttons change stack draw order
- **Animations** — Default names `ANIM0`, `ANIM1`, …; per-frame duration in VDP screen frames (~60/sec NTSC)
- **Uniform frame slots** — Every frame in an animation has the same number of sprite slots; adding or removing a sprite in one frame updates all others
- **Frame edit mode** — Edit individual frames with commit/discard and unsaved-change indicators
- **Animation preview** — Play/stop with hardware-aligned timing on the main canvas
- **Project files** — Save and load work as JSON (v2 with animations)
- **Export** — Live assembly panel with format picker, **Copy Assembly**, and **Save Binary…**

## Requirements

- Python 3.6+
- Tkinter (included with most Python installations; on Linux you may need `python3-tk`)

## Quick Start

```bash
python3 src/sprite.py
```

## Interface

The window has three columns:

| Area | Location | Description |
|------|----------|-------------|
| **TMS9918 Palette** | Left | Click a swatch to set the active color. `T` is transparent (erases pixels). Current color shown below the grid. |
| **Project Sprites / Frame Sprites** | Left | Sprite list with stack checkboxes and ↑↓ reorder. Title switches in frame edit mode. |
| **Drawing Canvas** | Center | Stacked sprite view with mode banner (static edit, frame edit, or preview). Grid always visible. |
| **Assembly Export** | Center | Live ASM output with a **Format** picker, **Copy Assembly**, and **Save Binary…** buttons. |
| **Animations** | Right | Animation picker, frame list, frame controls, duration/loop, and preview. |
| **Status bar** | Bottom | Active sprite, color, stacked count, and animation context. |

Frame edit and preview modes use a warm light background; the assembly panel and frame list stay white. During preview, all controls are disabled except **■ Stop**.

## Controls

| Action | Input |
|--------|-------|
| Draw pixel | Left mouse button (click or drag) |
| Erase pixel | Right mouse button (click or drag) |
| Select color | Click palette swatch |
| Select sprite | Click entry in sprite list |
| Rename sprite | Double-click sprite name |
| Toggle stack layer | Checkbox next to sprite slot |
| Reorder stack | ↑↓ buttons in sprite list header |
| Capture animation frame | `Ctrl+Shift+F` |
| Copy assembly | `Ctrl+Shift+C` |
| Toggle preview play/stop | `Space` (animation selected) |
| Cancel frame edit / stop preview | `Escape` |

### Sprite Buttons

- **Add** / **Remove** — Add or remove sprite slots (at least one must remain)
- **Rename** — Rename the current sprite
- **Clear Sprite** — Reset the current sprite to empty
- **Fill Sprite** — Fill the current sprite with the active color
- **Duplicate Sprite** — Copy the current sprite into the next slot

### Animation Workflow

1. Click **+** in the Animations panel to create an animation (defaults to `ANIM0`, `ANIM1`, …).
2. Select the sprite you want in the frame, draw on the canvas, and use stack checkboxes as needed.
3. Click **+ Frame** or press `Ctrl+Shift+F` to capture **only the currently selected sprite** into a new frame.
4. Click a frame in the list to edit it. Use **Commit Frame** / **Discard Changes** to save or revert edits.
5. Set **Duration (sf)** per frame — hold time in VDP screen frames (1–255). **Loop** controls whether preview repeats.
6. Press **▶ Play** or `Space` to preview on the main canvas.
7. Copy or save export output from the assembly panel (**Copy Assembly**, `Ctrl+Shift+C`, or **Save Binary…**).

**Escape** discards uncommitted frame edits and returns to static editing. **Animation → Exit Animation Mode** (`Escape` shown in menu) returns to static editing and prompts if there are unsaved changes.

Unsaved frame edits show a yellow **Unsaved changes** badge; saved frames show a green **All changes saved** badge.

Selecting an animation in the combobox does not enter frame edit — you stay in static edit until you click a frame.

## Menus

### File

| Command | Description |
|---------|-------------|
| **New** | Clear all sprites and animations |
| **Load Project** | Open a `.json` project file |
| **Save Project** | Save the current project as JSON |

### Animation

| Command | Description |
|---------|-------------|
| **New Animation** | Create a new animation |
| **Rename Animation…** | Rename the selected animation |
| **Capture Frame** | Add a frame from current editor state (`Ctrl+Shift+F`) |
| **Duplicate Animation** | Copy the selected animation |
| **Exit Animation Mode** | Return to static editing (`Escape`; prompts if unsaved) |

### Mode

| Command | Description |
|---------|-------------|
| **Switch to 8×8** | Change sprite size (clears project) |
| **Switch to 16×16** | Change sprite size (clears project) |

Assembly and binary export are available from the assembly panel only, not from the menu bar.

## Project Format (JSON v2)

```json
{
  "version": 2,
  "mode": 16,
  "sprites": [
    {
      "pattern": [[0, 1, ...], ...],
      "color": 2,
      "name": "SPR0"
    }
  ],
  "animations": [
    {
      "name": "ANIM0",
      "loop": true,
      "frames": [
        {
          "duration": 4,
          "stack_enabled": true,
          "stack_mask": [true, false],
          "sprites": [
            {"pattern": [[...]], "color": 2, "name": "SPR0"},
            {"pattern": [[...]], "color": 2, "name": "SPR1"}
          ]
        }
      ]
    }
  ],
  "current_animation": 0
}
```

- `version` — `2` for projects with animations; older files without `version` load as v1 (no animations)
- `mode` — Sprite dimensions: `8` or `16`
- `sprites` — Static sprite pool used when not editing an animation frame
- `animations` — Named sequences of frame snapshots
- `current_animation` — Optional index of the selected animation (restored on load)

Each animation frame stores:

- `duration` — Hold time in VDP screen frames (NTSC ~60/sec)
- `sprites` — All sprite slots for that frame (same count in every frame of the animation)
- `stack_mask` — Per-slot stacking flags (length matches `sprites`)
- `stack_enabled` — Legacy field, always `true` in saved projects

On load, frames in each animation are normalized to a common sprite slot count.

## Export Format

### Assembly (text)

Sprites export as `BYTE` directives with 8 hex values per line. An 8×8 sprite is 8 bytes (one row per line, top to bottom). A 16×16 sprite is 32 bytes (four lines) in TMS9918 quadrant order:

1. Top-left (rows 0–7, columns 0–7)
2. Bottom-left (rows 8–15, columns 0–7)
3. Top-right (rows 0–7, columns 8–15)
4. Bottom-right (rows 8–15, columns 8–15)

```
SPR0
; Sprite 00 8x8 Color 2
    BYTE >80,>00,>00,>00,>00,>00,>00,>00
```

#### Assembly panel behavior

| Mode | Panel shows |
|------|-------------|
| Static edit | Current sprite only |
| Frame edit | Full selected animation (uncommitted frame edits merged in) |
| Preview | Full animation |

Only **stacked** sprite slots are included in exported sprite data (matching the canvas composite). Use **Copy Assembly**, `Ctrl+Shift+C`, or select text directly from the panel.

#### TI-99/4A Default (`ti99_default`)

The default format uses a **frame directory** layout: an animation label, a header byte line, per-frame `DATA` address/duration entries, then labeled sprite pattern blocks.

Sprite labels follow `{anim}_{sprite}_F{frame}` — for example `ANIM0_SPR0_F00`, `ANIM0_SPR1_F00`.

Example — two-frame animation with one sprite slot per frame:

```asm
WALK
    BYTE >02,>01    ; Frame count, sprite count
    DATA WALK_SPR0_F00,>0004 ; Frame 0 address and duration
    DATA WALK_SPR0_F01,>0008 ; Frame 1 address and duration

WALK_SPR0_F00
    BYTE >80,>00,>00,>00,>00,>00,>00,>00

WALK_SPR0_F01
    BYTE >80,>80,>00,>00,>00,>00,>00,>00
```

The first header value is the frame count; the second is the sprite slot count (shared by all frames). The frame directory points at the first stacked sprite in each frame.

Example — one frame with two stacked sprites:

```asm
ANIM0
    BYTE >01,>02    ; Frame count, sprite count
    DATA ANIM0_SPR0_F00,>0004 ; Frame 0 address and duration

ANIM0_SPR0_F00
    BYTE >80,>00,>00,>00,>00,>00,>00,>00

ANIM0_SPR1_F00
    BYTE >40,>00,>00,>00,>00,>00,>00,>00
```

#### Generic DB (`generic_db`)

Comment-based layout with `db $XX` directives, per-frame blocks, and a decimal duration table — suited to Z80/6502-style assemblers.

### Custom export formats

ASM output is driven by template directories in [`formats/`](formats/). Each format is a folder containing `format.json` (dialect, labels, layout) and `.tpl` template files. Pick a format from the **Format** dropdown above the assembly panel.

| Format | Description |
|--------|-------------|
| `ti99_default/` | TI-99/4A frame directory with `BYTE` data and `{anim}_{sprite}_F{frame}` labels |
| `generic_db/` | `db $XX` style with duration table |

`format.json` fields:

- **`layout`** — `frame_directory` (TI-99 header + directory) or `default` (frames block + optional duration table)
- **`dialect`** — Comment prefix, data directive, hex prefix/separator, bytes per line, indent
- **`labels.patterns`** — Templates for animation, frame, sprite, and duration table labels

Template files (`.tpl`) use Python `str.format()` placeholders, including:

| Variable | Meaning |
|----------|---------|
| `{anim_name}` / `{anim_label}` | Animation name / sanitized label |
| `{frame_count}` / `{sprite_count}` | Frame count / sprite slots per frame |
| `{frame_count_header_hex}` | Header bytes (frame count + sprite count) for TI-99 layout |
| `{frame_index}` / `{frame_number}` | Frame index (0-based) / display number |
| `{duration}` / `{duration_hex}` | Frame hold time (decimal / hex) |
| `{sprite_name}` / `{sprite_label}` | Sprite slot name / export label |
| `{slot}` / `{slot:02d}` | Sprite slot index |
| `{color}` / `{size}` | VDP color index / sprite size (8 or 16) |
| `{data_lines}` / `{frames_block}` | Formatted pattern bytes / all frame sprite blocks |
| `{frame_directory_lines}` | Per-frame `DATA` directory entries (TI-99 layout) |
| `{duration_table_block}` | Duration table section (generic layout) |
| `{comment}` / `{data_directive}` / `{indent}` | Dialect tokens |

To add a format, copy an existing folder under `formats/`, edit `format.json` and the `.tpl` files, and restart the editor. Invalid format directories are skipped at startup.

### Binary (raw bytes)

Binary export writes **only** the TMS9918 pattern bytes — no headers, colors, or metadata. Byte order matches the assembly `BYTE` values.

| Export | Contents |
|--------|----------|
| **Save Binary…** (panel) | Pattern bytes for the current view: one sprite in static mode, or stacked sprites concatenated in frame edit / preview |
| Animation (via panel in frame edit / preview) | Stacked sprite pattern bytes for each frame, frames concatenated in order |

An 8×8 sprite is 8 bytes; a 16×16 sprite is 32 bytes per sprite.

## Stacking

Stacking is always available. Check the **Stack** box next to each sprite to include it in the canvas composite. Unchecked sprites are hidden from the stack and from exported sprite data.

Stack draw order follows the sprite list order — use ↑↓ to reorder.

In **static edit**, capturing a frame copies only the **currently selected** sprite (always stored as slot 0 in the new frame). Stack checkboxes on other project sprites do not add extra slots to the capture.

In **frame edit**, the sprite list shows that frame's slots. Adding or removing a sprite updates every other frame in the animation to keep slot counts aligned. Padded slots on other frames are empty and stacked by default. Commit saves the current frame; discard reverts it and removes auto-padded slots from other frames.

Adding or removing sprites in frame edit does not modify the static project sprite pool.

## Debug

Set `SPRITE_EDITOR_DEBUG=1` when launching to enable debug logging and approximate screen-frame rate in the status bar during preview.

## Tests

```bash
python3 -m unittest discover -s tests
```

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.