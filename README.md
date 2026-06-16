# TI-99/4A Sprite Editor

A desktop sprite editor for creating 8×8 and 16×16 pixel art for the [TI-99/4A](https://en.wikipedia.org/wiki/TI-99/4A) home computer. Draw sprites in the authentic 16-color palette, layer multiple sprites with stacked editing, build animations with VDP-timed preview, and export patterns as assembly `BYTE` directives.

Built with Python and Tkinter — no extra dependencies required.

## Features

- **TI-99/4A palette** — All 16 system colors, including transparent
- **8×8 and 16×16 modes** — Switch sprite size from the Mode menu (clears sprites and animations)
- **Dynamic sprite list** — Start with one sprite; add or remove slots as needed
- **Stacked editing** — Overlay multiple sprites on the canvas and preview to compose layered graphics
- **Animations** — Named frame sequences with per-frame duration in VDP screen frames (~60/sec NTSC)
- **Animation preview** — Play/stop with hardware-aligned timing; optional mirror on main canvas
- **Project files** — Save and load work as JSON (v2 with animations)
- **Export** — Live assembly panel plus full animation export to clipboard

## Requirements

- Python 3.6+
- Tkinter (included with most Python installations; on Linux you may need `python3-tk`)

## Quick Start

```bash
python3 src/sprite.py
```

## Interface

| Area | Description |
|------|-------------|
| **TI Palette** | Click a swatch to set the active color. `T` is transparent (erases pixels). |
| **Drawing Canvas** | Main editing area. Shows stacked layers when stacking is enabled. |
| **Assembly Export** | Live assembly output, updated as you edit or preview. |
| **Sprite Slots** | Select the active sprite. Checkboxes choose which sprites appear in the stack. |
| **Stacked Preview** | Live preview of the composed result. |
| **Animations** | Create animations, manage frames, set duration, preview playback. |
| **Status bar** | Sprite info, animation context, and preview progress. |

## Controls

| Action | Input |
|--------|-------|
| Draw pixel | Left mouse button (click or drag) |
| Erase pixel | Right mouse button (click or drag) |
| Select color | Click palette swatch |
| Select sprite | Click entry in sprite list |
| Toggle stack layer | Checkbox next to sprite slot |
| Capture animation frame | `Ctrl+Shift+F` |
| Copy assembly | `Ctrl+Shift+C` |
| Toggle preview play/stop | `Space` (animation selected) |
| Cancel frame edit / stop preview | `Escape` |

### Sprite Buttons

- **Clear Sprite** — Reset the current sprite to empty
- **Fill Sprite** — Fill the current sprite with the active color
- **Add Sprite** — Append a new empty sprite slot
- **Remove Sprite** — Delete the current sprite (at least one must remain)
- **Copy to Next** — Duplicate the current sprite into the next slot

### Animation Workflow

1. Click **+** in the Animations panel to create an animation.
2. Draw on the canvas (static mode) or edit sprite slots with stacking as needed.
3. Click **+ Frame** or press `Ctrl+Shift+F` to capture the current state into a new frame.
4. Click a frame in the list to edit it. Changes go to a working copy; switching frames auto-commits.
5. Set **Duration (sf)** per frame — hold time in VDP screen frames (1–255).
6. Press **▶ Play** or `Space` to preview. Uncheck **Loop animation** to play once.
7. Use **Animation → Export Animation ASM** to copy the full sequence with timing comments.

**Escape** discards uncommitted frame edits and returns to static editing. **Animation → Exit Animation Mode** commits and exits frame edit.

## File Menu

| Command | Description |
|---------|-------------|
| **New** | Clear all sprites and animations |
| **Load Project** | Open a `.json` project file |
| **Save Project** | Save the current project as JSON |
| **Copy Assembly to Clipboard** | Copy the assembly panel output (`Ctrl+Shift+C`) |

## Animation Menu

| Command | Description |
|---------|-------------|
| **New Animation** | Create a new named animation |
| **Rename Animation…** | Rename the selected animation |
| **Capture Frame** | Add a frame from current editor state (`Ctrl+Shift+F`) |
| **Duplicate Animation** | Copy the selected animation |
| **Export Animation ASM** | Copy all frames with timing comments to clipboard |
| **Exit Animation Mode** | Commit frame edits and return to static editing |

## Project Format (JSON v2)

```json
{
  "version": 2,
  "mode": 16,
  "sprites": [
    {
      "pattern": [[0, 1, ...], ...],
      "color": 2
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
          "stack_mask": [true, false],
          "sprites": [
            {"pattern": [[...]], "color": 2}
          ]
        }
      ]
    }
  ]
}
```

- `version` — `2` for projects with animations; older files without `version` load as v1 (no animations)
- `mode` — Sprite dimensions: `8` or `16`
- `sprites` — Static sprite slots used when not editing an animation frame
- `animations` — Named sequences; each frame is a full snapshot of all slots plus stack configuration

Each animation frame stores:

- `duration` — Hold time in VDP screen frames (NTSC ~60/sec)
- `stack_enabled` — Whether stacking was on when captured
- `stack_mask` — Which sprite slots were visible in the stack
- `sprites` — Deep copy of every slot's pattern and color at capture time

## Export Format

### Single sprite

Sprites export as `BYTE` directives with 8 hex values per line. An 8×8 sprite is 8 bytes (one line, top to bottom). A 16×16 sprite is 32 bytes (four lines) in TMS9918 quadrant order:

1. Top-left (rows 0–7, columns 0–7)
2. Bottom-left (rows 8–15, columns 0–7)
3. Top-right (rows 0–7, columns 8–15)
4. Bottom-right (rows 8–15, columns 8–15)

```
; TI-99 Sprite 00 16x16 Color 2
BYTE >FF,>00,>FF,>00,>FF,>00,>FF,>00
BYTE >FF,>00,>FF,>00,>FF,>00,>FF,>00
BYTE >FF,>00,>FF,>00,>FF,>00,>FF,>00
BYTE >FF,>00,>FF,>00,>FF,>00,>FF,>00
```

### Animation export

**Animation → Export Animation ASM** produces all frames with timing metadata. Only **stacked** sprite slots are exported per frame (matching what you see in a stacked preview):

```asm
; Animation 'walk' — 2 frames
; Frame 0: duration=4 screen frames
; TI-99 Sprite 00 8x8 Color 2
BYTE >80,>00,>00,>00,>00,>00,>00,>00

; Frame 1: duration=8 screen frames
; TI-99 Sprite 00 8x8 Color 2
BYTE >40,>00,>00,>00,>00,>00,>00,>00

; Durations (screen frames): 4, 8
; Total cycle: 12 screen frames (~200 ms)
```

The live assembly panel below the canvas shows the current sprite (or previewed frame). Use **Ctrl+Shift+C** or select text directly from the panel.

## Stacking

When **Enable Stacking** is on, the canvas and preview composite all checked sprite slots (plus the current sprite) from bottom to top. Animation frames capture this stack configuration so layered characters animate correctly.

## Debug

Set `SPRITE_EDITOR_DEBUG=1` when launching to enable debug logging and approximate screen-frame rate in the status bar during preview.

## Tests

```bash
python3 -m unittest discover -s tests
```

## License

See repository for license information.