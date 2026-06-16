# TI-99/4A Sprite Editor

A desktop sprite editor for creating 8×8 and 16×16 pixel art for the [TI-99/4A](https://en.wikipedia.org/wiki/TI-99/4A) home computer. Draw sprites in the authentic 16-color palette, layer multiple sprites with stacked editing, and export patterns as assembly `BYTE` directives.

Built with Python and Tkinter — no extra dependencies required.

## Features

- **TI-99/4A palette** — All 16 system colors, including transparent
- **8×8 and 16×16 modes** — Switch sprite size from the Mode menu (clears sprites)
- **Dynamic sprite list** — Start with one sprite; add or remove slots as needed
- **Stacked editing** — Overlay multiple sprites on the canvas and preview to compose layered graphics
- **Project files** — Save and load work as JSON
- **Export** — Copy assembly output to the clipboard for use in your programs

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
| **Assembly Export** | Live assembly output for the current sprite, updated as you edit. |
| **Sprite Slots** | Select the active sprite. Checkboxes choose which sprites appear in the stack. Use Add/Remove to manage slots. |
| **Stacked Preview** | Live preview of the composed result. |
| **Status bar** | Current sprite, size, color, and stacking state. |

## Controls

| Action | Input |
|--------|-------|
| Draw pixel | Left mouse button (click or drag) |
| Erase pixel | Right mouse button (click or drag) |
| Select color | Click palette swatch |
| Select sprite | Click entry in sprite list |
| Toggle stack layer | Checkbox next to sprite slot |

### Buttons

- **Clear Sprite** — Reset the current sprite to empty
- **Fill Sprite** — Fill the current sprite with the active color
- **Add Sprite** — Append a new empty sprite slot
- **Remove Sprite** — Delete the current sprite (at least one must remain)
- **Copy to Next** — Duplicate the current sprite into the next slot

## File Menu

| Command | Description |
|---------|-------------|
| **New** | Clear all sprites and start fresh |
| **Load Project** | Open a `.json` project file |
| **Save Project** | Save the current project as JSON |
| **Copy Assembly to Clipboard** | Copy the assembly output for the current sprite (`Ctrl+Shift+C`) |

## Project Format

Projects are saved as JSON:

```json
{
  "mode": 16,
  "sprites": [
    {
      "pattern": [[0, 1, ...], ...],
      "color": 2
    }
  ]
}
```

- `mode` — Sprite dimensions: `8` or `16`
- `sprites` — Array of sprite objects, each with a 2D `pattern` (0 = off, 1 = on) and a `color` index (0–15)

## Export Format

Sprites export as `BYTE` directives with 8 hex values per line. An 8×8 sprite is 8 bytes (one line, top to bottom). A 16×16 sprite is 32 bytes (four lines) in TMS9918 quadrant order:

1. Top-left (rows 0–7, columns 0–7)
2. Bottom-left (rows 8–15, columns 0–7)
3. Top-right (rows 0–7, columns 8–15)
4. Bottom-right (rows 8–15, columns 8–15)

```
BYTE >FF,>00,>FF,>00,>FF,>00,>FF,>00   ; top-left
BYTE >FF,>00,>FF,>00,>FF,>00,>FF,>00   ; bottom-left
BYTE >FF,>00,>FF,>00,>FF,>00,>FF,>00   ; top-right
BYTE >FF,>00,>FF,>00,>FF,>00,>FF,>00   ; bottom-right
```

Assembly output is shown live below the canvas. Press **Ctrl+Shift+C** or use **File → Copy Assembly to Clipboard** to copy it. You can also select text directly from the panel.

## Stacking

When **Enable Stacking** is on, the canvas and preview composite all checked sprite slots (plus the current sprite) from bottom to top. Uncheck layers to hide them, or disable stacking entirely to edit a single sprite in isolation.

## License

See repository for license information.