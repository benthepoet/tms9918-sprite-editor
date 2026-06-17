# TMS9918 Sprite Editor

A desktop sprite editor for the [TMS9918](https://en.wikipedia.org/wiki/TMS9918) VDP — create 8×8 and 16×16 sprite patterns in the authentic 16-color palette, layer multiple sprites with per-slot stacking, build animations with VDP-timed preview, and export patterns as assembly `BYTE` directives or raw binary. Commonly used for [TI-99/4A](https://en.wikipedia.org/wiki/TI-99/4A) development and other TMS9918-based systems.

Built with Python and Tkinter — no extra dependencies required.

## Features

- **TMS9918 palette** — All 16 VDP colors, including transparent
- **8×8 and 16×16 modes** — Switch sprite size from the Mode menu (clears sprites and animations)
- **Named sprite slots** — Rename sprites; double-click a slot name to rename
- **Stacked editing** — Composite checked sprite layers on the canvas; control stacking per sprite
- **Sprite reordering** — ↑↓ buttons change stack draw order
- **Animations** — Named frame sequences with per-frame duration in VDP screen frames (~60/sec NTSC)
- **Frame edit mode** — Edit individual frames with commit/discard and unsaved-change indicators
- **Animation preview** — Play/stop with hardware-aligned timing on the main canvas
- **Project files** — Save and load work as JSON (v2 with animations)
- **Export** — Live assembly panel, clipboard copy, raw binary file export, and customizable ASM format templates

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

Frame edit and preview modes use a warm light background; the assembly panel and frame list stay white.

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

1. Click **+** in the Animations panel to create an animation.
2. Draw on the canvas and use stack checkboxes to choose visible layers.
3. Click **+ Frame** or press `Ctrl+Shift+F` to capture the current state into a new frame.
4. Click a frame in the list to edit it. Use **Commit Frame** / **Discard Changes** to save or revert edits.
5. Set **Duration (sf)** per frame — hold time in VDP screen frames (1–255).
6. Press **▶ Play** or `Space` to preview on the main canvas. Uncheck **Loop animation** to play once.
7. Export via **Animation → Export Animation ASM** (clipboard) or **Export Animation Binary…** (raw bytes).

**Escape** discards uncommitted frame edits and returns to static editing. **Animation → Exit Animation Mode** returns to static editing (prompts if there are unsaved changes).

Unsaved frame edits show a yellow **Unsaved changes** badge; saved frames show a green **All changes saved** badge.

## File Menu

| Command | Description |
|---------|-------------|
| **New** | Clear all sprites and animations |
| **Load Project** | Open a `.json` project file |
| **Save Project** | Save the current project as JSON |
| **Copy Assembly to Clipboard** | Copy the assembly panel output (`Ctrl+Shift+C`) |
| **Export Binary…** | Save raw pattern bytes for the current panel view |

## Animation Menu

| Command | Description |
|---------|-------------|
| **New Animation** | Create a new named animation |
| **Rename Animation…** | Rename the selected animation |
| **Capture Frame** | Add a frame from current editor state (`Ctrl+Shift+F`) |
| **Duplicate Animation** | Copy the selected animation |
| **Export Animation ASM** | Copy all frames with timing comments to clipboard |
| **Export Animation Binary…** | Save raw pattern bytes for all stacked sprites in each frame |
| **Exit Animation Mode** | Return to static editing (prompts if there are unsaved changes) |

## Project Format (JSON v2)

```json
{
  "version": 2,
  "mode": 16,
  "sprites": [
    {
      "pattern": [[0, 1, ...], ...],
      "color": 2,
      "name": "Sprite 0"
    }
  ],
  "animations": [
    {
      "name": "walk",
      "loop": true,
      "frames": [
        {
          "duration": 4,
          "stack_enabled": true,
          "stack_mask": [true, true],
          "sprites": [
            {"pattern": [[...]], "color": 2, "name": "Sprite 0"}
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
- `name` — Optional per-sprite display name

Each animation frame stores:

- `duration` — Hold time in VDP screen frames (NTSC ~60/sec)
- `stack_mask` — Which sprites were stacked when captured (frames store only stacked sprites)
- `sprites` — Pattern and color data for stacked sprites in that frame
- `stack_enabled` — Legacy field, always `true` in saved projects

## Export Format

### Assembly (text)

Sprites export as `BYTE` directives with 8 hex values per line. An 8×8 sprite is 8 bytes (one row per line, top to bottom). A 16×16 sprite is 32 bytes (four lines) in TMS9918 quadrant order:

1. Top-left (rows 0–7, columns 0–7)
2. Bottom-left (rows 8–15, columns 0–7)
3. Top-right (rows 0–7, columns 8–15)
4. Bottom-right (rows 8–15, columns 8–15)

```
; TMS9918 Sprite 00 16x16 Color 2
BYTE >FF,>00,>FF,>00,>FF,>00,>FF,>00
BYTE >FF,>00,>FF,>00,>FF,>00,>FF,>00
BYTE >FF,>00,>FF,>00,>FF,>00,>FF,>00
BYTE >FF,>00,>FF,>00,>FF,>00,>FF,>00
```

**Animation → Export Animation ASM** produces all frames with timing metadata. Only **stacked** sprite slots are exported per frame (matching the canvas composite).

Example — two-frame walk cycle (one stacked sprite per frame):

```asm
; Animation 'walk' — 2 frames
; Frame 0: duration=4 screen frames
; TMS9918 Sprite 00 8x8 Color 2
BYTE >80,>00,>00,>00,>00,>00,>00,>00


; Frame 1: duration=8 screen frames
; TMS9918 Sprite 00 8x8 Color 2
BYTE >80,>80,>00,>00,>00,>00,>00,>00


; Durations (screen frames): 4, 8
; Total cycle: 12 screen frames (~200 ms)
```

Example — single frame with two stacked sprites (body + detail layer):

```asm
; Animation 'hero' — 1 frames
; Frame 0: duration=6 screen frames
; TMS9918 Sprite 00 8x8 Color 2
BYTE >80,>00,>00,>00,>00,>00,>00,>00

; TMS9918 Sprite 01 8x8 Color 4
BYTE >80,>40,>00,>00,>00,>00,>00,>00


; Durations (screen frames): 6
; Total cycle: 6 screen frames (~100 ms)
```

Each frame section lists its hold time in VDP screen frames, then one `BYTE` block per stacked sprite. The summary at the end totals frame durations for the full loop.

The live assembly panel shows the current sprite, frame-edit stack, or previewed frame. Use **Copy Assembly**, **Ctrl+Shift+C**, or select text directly from the panel. Choose a different output style from the **Format** dropdown above the panel.

### Custom export formats

ASM output is driven by JSON templates in [`formats/`](formats/). Pick a format from the **Format** dropdown to change comments, labels, directives, and optional animation metadata.

| File | Description |
|------|-------------|
| `ti99_default.json` | Current TI-99/4A style (`BYTE >XX`, timing comments) |
| `ti99_labeled.json` | TI-99 dialect with frame labels and a `BYTE` duration table |
| `generic_db.json` | `db $XX` style for Z80/6502-like assemblers |

Each format file defines:

- **`dialect`** — Comment prefix, data directive, hex prefix/separator, bytes per line
- **`labels.patterns`** — Templates for animation, frame, sprite, duration table, and frame-count labels
- **`animation.sections`** — Toggleable header, per-frame blocks, duration table, frame count, footer
- **`sprite.sections`** — Single-sprite panel export (comment, optional label, data lines)

Template placeholders include:

| Variable | Meaning |
|----------|---------|
| `{anim_name}` | Animation name |
| `{anim_label}` | Sanitized animation label |
| `{frame_count}` | Number of frames |
| `{frame_index}` | Frame index (0-based) |
| `{duration}` | Frame hold time in screen frames |
| `{frame_label}` | Sanitized per-frame label |
| `{slot}` / `{slot:02d}` | Sprite slot index |
| `{color}` | VDP color index |
| `{size}` | Sprite size (8 or 16) |
| `{durations_csv}` | Comma-separated frame durations |
| `{total_duration}` / `{total_ms}` | Full loop length |
| `{comment}` | Dialect comment prefix (`;`) |
| `{data_directive}` / `{data_line}` | Assembler data directive and formatted byte line |

Example labeled output (`ti99_labeled.json`):

```asm
; Animation: walk
; Frames: 2
WALK_F00:
; Duration: 4 screen frames
; Sprite 00 8x8 Color 2
BYTE >80,>00,>00,>00,>00,>00,>00,>00

WALK_F01:
; Duration: 8 screen frames
; Sprite 00 8x8 Color 2
BYTE >80,>80,>00,>00,>00,>00,>00,>00

WALK_DUR:
; Frame durations (screen frames)
BYTE 4,8

; Total cycle: 12 screen frames (~200 ms)
```

To add a format, copy an existing file in `formats/`, edit the templates, and restart the editor. Invalid files are skipped at startup.

### Binary (raw bytes)

Binary export writes **only** the TMS9918 pattern bytes — no headers, colors, or metadata. Byte order matches the assembly `BYTE` values.

| Export | Contents |
|--------|----------|
| **Save Binary…** (panel) | Pattern bytes for the current view: one sprite in static mode, or stacked sprites concatenated in frame edit / preview |
| **Export Binary…** (File menu) | Same as **Save Binary…** |
| **Export Animation Binary…** | Stacked sprite pattern bytes for each frame, frames concatenated in order |

An 8×8 sprite is 8 bytes; a 16×16 sprite is 32 bytes per sprite.

## Stacking

Stacking is always available. Check the **Stack** box next to each sprite to include it in the canvas composite. Unchecked sprites are hidden from the stack (and from animation frame capture). The current sprite is always included when capturing a frame.

Stack draw order follows the sprite list order — use ↑↓ to reorder. In frame edit mode, only sprites stored in that frame are shown; adding sprites in frame edit does not modify the static sprite pool.

## Debug

Set `SPRITE_EDITOR_DEBUG=1` when launching to enable debug logging and approximate screen-frame rate in the status bar during preview.

## Tests

```bash
python3 -m unittest discover -s tests
```

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.