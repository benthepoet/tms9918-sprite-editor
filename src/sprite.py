import json
import logging
import os
import time
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from animation_schema import (
    MAX_FILE_BYTES_WARN,
    MAX_FRAMES_PER_ANIM,
    deep_copy_animation,
    deep_copy_frame,
    deep_copy_sprite,
    deep_copy_sprites,
    normalize_frame_slots,
    validate_and_sanitize_animations,
)

# TI-99/4A Colors (approximate RGB for display)
TI_COLORS = [
    (0, 0, 0),      # 0 Transparent / Black
    (0, 0, 0),      # 1 Black
    (33, 200, 66),  # 2 Medium Green
    (66, 220, 99),  # 3 Light Green
    (66, 66, 200),  # 4 Dark Blue
    (99, 99, 255),  # 5 Light Blue
    (200, 66, 66),  # 6 Dark Red
    (33, 200, 200), # 7 Cyan
    (200, 66, 66),  # 8 Medium Red
    (255, 99, 99),  # 9 Light Red
    (200, 200, 66), # 10 Dark Yellow
    (200, 200, 99), # 11 Light Yellow
    (66, 200, 66),  # 12 Dark Green
    (200, 66, 200), # 13 Magenta
    (200, 200, 200),# 14 Gray
    (255, 255, 255) # 15 White
]

COLOR_NAMES = [
    "Transparent", "Black", "Med Green", "Lt Green",
    "Dark Blue", "Lt Blue", "Dark Red", "Cyan",
    "Med Red", "Lt Red", "Dark Yellow", "Lt Yellow",
    "Dark Green", "Magenta", "Gray", "White"
]

VDP_FRAME_SEC = 1.0 / 59.94

if os.environ.get("SPRITE_EDITOR_DEBUG"):
    logging.basicConfig(level=logging.DEBUG)

class SpriteEditor:
    def __init__(self, root, create_ui=True):
        self.root = root
        self.root.title("TI-99/4A Sprite Editor - Stacked Editing")
        self.root.geometry("1300x900")

        self.sprite_size_mode = 16
        self.current_sprite = 0
        self.current_color = 2

        self.sprites = []
        self.init_sprites(1)

        self.zoom = 20
        self.stack_enabled = tk.BooleanVar(value=True)
        self.stack_vars = []

        self.animations = []
        self.current_animation = None
        self.current_anim_frame = 0
        self.anim_preview_running = False
        self.anim_preview_frame_counter = 0
        self.anim_edit_mode = False
        self._anim_preview_index = 0
        self._anim_preview_after_id = None
        self._anim_preview_next_tick = 0.0
        self._frame_edit_snapshot = None
        self._static_stack_mask = None
        self._static_stack_enabled = None
        self._preview_return_to_frame_edit = False
        self.mirror_preview_on_canvas = tk.BooleanVar(value=True)
        self._preview_fps_ticks = 0
        self._preview_fps_window_start = 0.0
        self._suppress_anim_ui_events = False

        if create_ui:
            self.create_ui()
            self.root.protocol("WM_DELETE_WINDOW", self._on_window_close)
            self.root.bind("<Control-Shift-C>", self._copy_asm_shortcut)
            self.root.bind("<Control-Shift-F>", self._capture_frame_shortcut)
            self.root.bind("<Escape>", self._on_escape)
            self.root.bind("<space>", self._toggle_preview_shortcut)
    
    def init_sprites(self, count=1):
        size = self.sprite_size_mode
        self.sprites = []
        for _ in range(count):
            pattern = [[0 for _ in range(size)] for _ in range(size)]
            self.sprites.append({"pattern": pattern, "color": self.current_color})

    def create_empty_sprite(self):
        size = self.sprite_size_mode
        return {
            "pattern": [[0 for _ in range(size)] for _ in range(size)],
            "color": self.current_color,
        }
    
    def create_ui(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="New", command=self.new_project)
        file_menu.add_command(label="Load Project", command=self.load_project)
        file_menu.add_command(label="Save Project", command=self.save_project)
        file_menu.add_separator()
        file_menu.add_command(
            label="Copy Assembly to Clipboard",
            command=self.copy_asm,
            accelerator="Ctrl+Shift+C",
        )

        anim_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Animation", menu=anim_menu)
        anim_menu.add_command(label="New Animation", command=self.create_animation)
        anim_menu.add_command(label="Rename Animation…", command=self.rename_animation_dialog)
        anim_menu.add_command(
            label="Capture Frame",
            command=self.add_anim_frame,
            accelerator="Ctrl+Shift+F",
        )
        anim_menu.add_command(label="Duplicate Animation", command=self.duplicate_animation)
        anim_menu.add_separator()
        anim_menu.add_command(
            label="Export Animation ASM",
            command=self.copy_animation_asm,
        )
        anim_menu.add_command(label="Exit Animation Mode", command=self.exit_animation_mode)

        mode_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Mode", menu=mode_menu)
        mode_menu.add_command(label="Switch to 8×8", command=lambda: self.set_mode(8))
        mode_menu.add_command(label="Switch to 16×16", command=lambda: self.set_mode(16))
        
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Left: Palette
        palette_frame = ttk.LabelFrame(main_frame, text="TI Palette (T=Transparent)")
        palette_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0,10))
        
        for i in range(16):
            color_hex = "#aaaaaa" if i == 0 else self.rgb_to_hex(TI_COLORS[i])
            btn = tk.Canvas(palette_frame, width=50, height=30, bg=color_hex, highlightthickness=2)
            if i == 0:
                btn.create_text(25, 15, text="T", fill="black", font=("Arial", 10, "bold"))
            btn.bind("<Button-1>", lambda e, c=i: self.set_color(c))
            btn.grid(row=i//4, column=i%4, padx=3, pady=3)
        
        # Center: Drawing Canvas (now supports stacking)
        canvas_frame = ttk.LabelFrame(main_frame, text="Drawing Canvas - Stacked View (LMB=draw on current, RMB=erase on current)")
        canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10)
        
        self.canvas = tk.Canvas(canvas_frame, bg="#777777")
        self.canvas.pack(pady=10)
        self.canvas.bind("<Button-1>", self.draw_pixel)
        self.canvas.bind("<B1-Motion>", self.draw_pixel)
        self.canvas.bind("<Button-3>", self.erase_pixel)
        self.canvas.bind("<B3-Motion>", self.erase_pixel)

        asm_frame = ttk.LabelFrame(canvas_frame, text="Assembly Export")
        asm_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 5))

        self.asm_text = tk.Text(asm_frame, height=6, font=("Courier", 10), wrap=tk.NONE)
        self.asm_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.asm_text.bind("<Key>", lambda e: "break")
        
        # Right Panel
        right_frame = ttk.Frame(main_frame)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y)
        
        ttk.Label(right_frame, text="Sprite Slots (check to stack)").pack(anchor="w")
        
        list_frame = ttk.Frame(right_frame)
        list_frame.pack(pady=5, fill="x")
        
        self.sprite_list = tk.Listbox(list_frame, height=12, width=18)
        self.sprite_list.pack(side=tk.LEFT)
        self.sprite_list.bind("<<ListboxSelect>>", self.select_sprite)
        
        self.check_frame = ttk.Frame(list_frame)
        self.check_frame.pack(side=tk.RIGHT, fill="y")

        self.stack_vars = []
        self.rebuild_sprite_list()

        sprite_btn_frame = ttk.Frame(right_frame)
        sprite_btn_frame.pack(fill="x", pady=5)
        ttk.Button(sprite_btn_frame, text="Add Sprite", command=self.add_sprite).pack(side=tk.LEFT, expand=True, fill="x", padx=(0, 3))
        ttk.Button(sprite_btn_frame, text="Remove Sprite", command=self.remove_sprite).pack(side=tk.LEFT, expand=True, fill="x", padx=(3, 0))
        
        self.stack_enabled_checkbox = ttk.Checkbutton(
            right_frame,
            text="Enable Stacking (Canvas + Preview)",
            variable=self.stack_enabled,
            command=self._on_stack_enabled_changed_static,
        )
        self.stack_enabled_checkbox.pack(anchor="w", pady=5)
        
        ttk.Label(right_frame, text="Stacked Preview").pack(anchor="w")
        self.preview_canvas = tk.Canvas(right_frame, bg="#777777", width=160, height=160)
        self.preview_canvas.pack(pady=5)
        
        ttk.Button(right_frame, text="Clear Sprite", command=self.clear_current).pack(pady=5, fill="x")
        ttk.Button(right_frame, text="Fill Sprite", command=self.fill_sprite).pack(pady=5, fill="x")
        ttk.Button(right_frame, text="Copy to Next", command=self.copy_to_next).pack(pady=5, fill="x")

        anim_panel = ttk.LabelFrame(right_frame, text="Animations")
        anim_panel.pack(fill="x", pady=(10, 0))

        anim_top = ttk.Frame(anim_panel)
        anim_top.pack(fill="x", padx=5, pady=5)
        self.anim_combo = ttk.Combobox(anim_top, state="readonly", width=14)
        self.anim_combo.pack(side=tk.LEFT, fill="x", expand=True)
        self.anim_combo.bind("<<ComboboxSelected>>", self._on_animation_selected)

        anim_btn_row = ttk.Frame(anim_top)
        anim_btn_row.pack(side=tk.RIGHT)
        ttk.Button(anim_btn_row, text="+", width=3, command=self.create_animation).pack(side=tk.LEFT)
        ttk.Button(anim_btn_row, text="−", width=3, command=self.delete_animation).pack(side=tk.LEFT)
        ttk.Button(anim_btn_row, text="Dup", width=4, command=self.duplicate_animation).pack(side=tk.LEFT)
        ttk.Button(anim_btn_row, text="Ren", width=4, command=self.rename_animation_dialog).pack(side=tk.LEFT)

        ttk.Label(anim_panel, text="Frames").pack(anchor="w", padx=5)
        self.anim_frame_list = tk.Listbox(anim_panel, height=6, width=22)
        self.anim_frame_list.pack(fill="x", padx=5, pady=2)
        self.anim_frame_list.bind("<<ListboxSelect>>", self._on_anim_frame_selected)

        frame_btn_row = ttk.Frame(anim_panel)
        frame_btn_row.pack(fill="x", padx=5, pady=5)
        ttk.Button(frame_btn_row, text="+ Frame", command=self.add_anim_frame).pack(
            side=tk.LEFT, expand=True, fill="x", padx=(0, 2)
        )
        ttk.Button(frame_btn_row, text="− Frame", command=self.delete_anim_frame).pack(
            side=tk.LEFT, expand=True, fill="x", padx=2
        )
        ttk.Button(frame_btn_row, text="↑", width=3, command=lambda: self.move_anim_frame(-1)).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(frame_btn_row, text="↓", width=3, command=lambda: self.move_anim_frame(1)).pack(
            side=tk.LEFT, padx=(2, 0)
        )

        props_row = ttk.Frame(anim_panel)
        props_row.pack(fill="x", padx=5, pady=5)
        ttk.Label(props_row, text="Duration (sf):").pack(side=tk.LEFT)
        self.anim_duration_var = tk.IntVar(value=4)
        self.anim_duration_spin = ttk.Spinbox(
            props_row,
            from_=1,
            to=255,
            width=5,
            textvariable=self.anim_duration_var,
            command=self._on_duration_changed,
        )
        self.anim_duration_spin.pack(side=tk.LEFT, padx=5)

        self.anim_loop_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            anim_panel,
            text="Loop animation",
            variable=self.anim_loop_var,
            command=self._on_loop_changed,
        ).pack(anchor="w", padx=5, pady=(0, 5))

        preview_frame = ttk.LabelFrame(anim_panel, text="Preview")
        preview_frame.pack(fill="x", padx=5, pady=5)
        preview_btn_row = ttk.Frame(preview_frame)
        preview_btn_row.pack(fill="x", pady=2)
        self.anim_play_btn = ttk.Button(
            preview_btn_row, text="▶ Play", command=self.start_anim_preview
        )
        self.anim_play_btn.pack(side=tk.LEFT, expand=True, fill="x", padx=(0, 2))
        self.anim_stop_btn = ttk.Button(
            preview_btn_row, text="■ Stop", command=self.stop_anim_preview
        )
        self.anim_stop_btn.pack(side=tk.LEFT, expand=True, fill="x", padx=(2, 0))
        ttk.Checkbutton(
            preview_frame,
            text="Mirror on canvas",
            variable=self.mirror_preview_on_canvas,
        ).pack(anchor="w", padx=2)
        self.anim_preview_status = ttk.Label(preview_frame, text="")
        self.anim_preview_status.pack(anchor="w", padx=2, pady=2)

        self._refresh_animation_ui()
        
        self.status = ttk.Label(self.root, text="", relief=tk.SUNKEN, anchor=tk.W)
        self.status.pack(side=tk.BOTTOM, fill=tk.X)
        
        self.update_canvas()
        self.update_status()
        self.update_preview()
        self.update_asm_export()
    
    def rgb_to_hex(self, rgb):
        return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
    
    def set_color(self, color):
        if self.anim_preview_running:
            return
        self.current_color = color
        if color == 0:
            pass
        elif self.anim_edit_mode and self._frame_edit_snapshot is not None:
            self._frame_edit_snapshot["sprites"][self.current_sprite]["color"] = color
        else:
            self.sprites[self.current_sprite]["color"] = color
        self.refresh_views()
    
    def refresh_views(self):
        if not hasattr(self, "canvas") or self.anim_preview_running:
            return
        self.update_canvas()
        self.update_preview()
        self.update_status()
        self.update_asm_export()
    
    def set_mode(self, mode):
        if self.sprite_size_mode == mode:
            return
        if messagebox.askyesno(
            "Change Mode",
            "This will clear all sprites and animations. Continue?",
        ):
            self._reset_animation_state()
            self.animations = []
            count = max(1, len(self.sprites))
            self.sprite_size_mode = mode
            self.init_sprites(count)
            self.current_sprite = 0
            self.current_color = 2
            self.rebuild_sprite_list()
            self.refresh_views()

    def rebuild_sprite_list(self, source="static", mask=None):
        if not hasattr(self, "sprite_list"):
            return
        old_stack = [var.get() for var in self.stack_vars]
        self.sprite_list.delete(0, tk.END)
        for child in self.check_frame.winfo_children():
            child.destroy()
        self.stack_vars = []

        if self.current_sprite >= len(self.sprites):
            self.current_sprite = max(0, len(self.sprites) - 1)

        for i in range(len(self.sprites)):
            if source == "frame" and mask is not None:
                stacked = mask[i] if i < len(mask) else False
            elif source == "static" and self._static_stack_mask and i < len(
                self._static_stack_mask
            ):
                stacked = self._static_stack_mask[i]
            elif i < len(old_stack):
                stacked = old_stack[i]
            elif len(self.sprites) == 1:
                stacked = True
            else:
                stacked = i <= 1
            var = tk.BooleanVar(value=stacked)
            cb = ttk.Checkbutton(
                self.check_frame, variable=var, command=self._on_stack_checkbox_changed
            )
            cb.pack(anchor="w")
            self.stack_vars.append(var)
            self.sprite_list.insert(tk.END, f"Sprite {i:02d}")

        if self.sprites:
            self.sprite_list.selection_clear(0, tk.END)
            self.sprite_list.selection_set(self.current_sprite)
            self.sprite_list.activate(self.current_sprite)

    def _sprite_list_source(self):
        if self.anim_edit_mode and self._frame_edit_snapshot is not None:
            return "frame", self._frame_edit_snapshot["stack_mask"]
        return "static", None

    def add_sprite(self):
        if self.anim_preview_running:
            return
        self.sprites.append(self.create_empty_sprite())
        self.current_sprite = len(self.sprites) - 1
        self._sync_all_animation_slot_counts()
        source, mask = self._sprite_list_source()
        self.rebuild_sprite_list(source=source, mask=mask)
        self.refresh_views()

    def remove_sprite(self):
        if self.anim_preview_running:
            return
        if len(self.sprites) <= 1:
            messagebox.showinfo("Remove Sprite", "At least one sprite is required.")
            return
        if not messagebox.askyesno(
            "Remove Sprite", f"Remove Sprite {self.current_sprite:02d}?"
        ):
            return
        self._remove_slot_at_index(self.current_sprite)
        source, mask = self._sprite_list_source()
        self.rebuild_sprite_list(source=source, mask=mask)
        self.refresh_views()

    def _sync_all_animation_slot_counts(self):
        target = len(self.sprites)
        size = self.sprite_size_mode
        for anim in self.animations:
            for index, frame in enumerate(anim.get("frames", [])):
                anim["frames"][index] = normalize_frame_slots(
                    deep_copy_frame(frame), target, size, self.current_color
                )
        if self.anim_edit_mode and self._frame_edit_snapshot is not None:
            self._frame_edit_snapshot = normalize_frame_slots(
                deep_copy_frame(self._frame_edit_snapshot),
                target,
                size,
                self.current_color,
            )

    def _remove_slot_at_index(self, index: int):
        if index < 0 or index >= len(self.sprites):
            return
        del self.sprites[index]
        for anim in self.animations:
            for frame in anim.get("frames", []):
                if index < len(frame["sprites"]):
                    del frame["sprites"][index]
                if index < len(frame["stack_mask"]):
                    del frame["stack_mask"][index]
        if self.anim_edit_mode and self._frame_edit_snapshot is not None:
            snapshot = self._frame_edit_snapshot
            if index < len(snapshot["sprites"]):
                del snapshot["sprites"][index]
            if index < len(snapshot["stack_mask"]):
                del snapshot["stack_mask"][index]
        if self.current_sprite >= len(self.sprites):
            self.current_sprite = max(0, len(self.sprites) - 1)

    def _current_animation_has_frames(self):
        anim = self._current_animation()
        return anim is not None and bool(anim.get("frames"))

    def _apply_anim_frame_for_preview(self, index: int):
        frame = self.animations[self.current_animation]["frames"][index]
        self._anim_preview_index = index
        if hasattr(self, "preview_canvas"):
            self.preview_canvas.delete("all")
            self._render_composite(
                self.preview_canvas,
                frame["sprites"],
                frame["stack_enabled"],
                frame["stack_mask"],
                self.current_sprite,
                pixel_size=160 // self.sprite_size_mode,
                draw_off_pixels=False,
                transparent_color="#000000",
                outline="",
            )
        if self.mirror_preview_on_canvas.get() and hasattr(self, "canvas"):
            size = self.sprite_size_mode
            ps = self.zoom
            self.canvas.delete("all")
            self.canvas.config(width=size * ps + 4, height=size * ps + 4)
            self._render_composite(
                self.canvas,
                frame["sprites"],
                frame["stack_enabled"],
                frame["stack_mask"],
                self.current_sprite,
                pixel_size=ps,
                draw_off_pixels=False,
                transparent_color="#aaaaaa",
                outline="#666666",
            )
        self.update_asm_export()

    def start_anim_preview(self):
        if not self._current_animation_has_frames():
            messagebox.showinfo("Preview", "Add at least one frame to preview.")
            return
        if self.anim_preview_running:
            return
        self._preview_return_to_frame_edit = self.anim_edit_mode
        if self.anim_edit_mode:
            self.commit_anim_frame()
            self._leave_anim_frame_edit()
        start_index = (
            self.current_anim_frame if self._preview_return_to_frame_edit else 0
        )
        self.anim_preview_running = True
        self.anim_preview_frame_counter = 0
        self._anim_preview_index = start_index
        self._preview_fps_ticks = 0
        self._preview_fps_window_start = time.perf_counter()
        self._set_preview_ui_state(False)
        self._apply_anim_frame_for_preview(start_index)
        self._update_preview_status()
        self._anim_preview_next_tick = time.perf_counter()
        logging.debug("preview start animation=%s frame=%s", self.current_animation, start_index)
        self._schedule_anim_preview_tick()

    def stop_anim_preview(self):
        if not self.anim_preview_running and self._anim_preview_after_id is None:
            return
        self.anim_preview_running = False
        if self._anim_preview_after_id is not None:
            self.root.after_cancel(self._anim_preview_after_id)
            self._anim_preview_after_id = None
        self._set_preview_ui_state(True)
        return_to_edit = self._preview_return_to_frame_edit
        self._preview_return_to_frame_edit = False
        logging.debug("preview stop return_to_edit=%s", return_to_edit)
        if return_to_edit:
            self.select_anim_frame(self.current_anim_frame)
        elif hasattr(self, "canvas"):
            self.refresh_views()

    def toggle_anim_preview(self):
        if self.anim_preview_running:
            self.stop_anim_preview()
        else:
            self.start_anim_preview()

    def _schedule_anim_preview_tick(self):
        self._anim_preview_next_tick += VDP_FRAME_SEC
        delay_ms = max(
            1, int((self._anim_preview_next_tick - time.perf_counter()) * 1000)
        )
        self._anim_preview_after_id = self.root.after(
            delay_ms, self._anim_preview_tick
        )

    def _process_anim_preview_tick(self):
        """Advance preview by one VDP screen frame. Returns False if playback stopped."""
        if not self.anim_preview_running or self.current_animation is None:
            return False
        anim = self.animations[self.current_animation]
        frames = anim.get("frames", [])
        if not frames:
            return False

        self.anim_preview_frame_counter += 1
        frame = frames[self._anim_preview_index]
        if self.anim_preview_frame_counter < frame["duration"]:
            return True

        self.anim_preview_frame_counter = 0
        next_index = self._anim_preview_index + 1
        if next_index >= len(frames):
            if anim.get("loop", True):
                next_index = 0
            else:
                self.anim_preview_running = False
                if self._anim_preview_after_id is not None:
                    self.root.after_cancel(self._anim_preview_after_id)
                    self._anim_preview_after_id = None
                self._set_preview_ui_state(True)
                self._preview_return_to_frame_edit = False
                if hasattr(self, "canvas"):
                    self.refresh_views()
                logging.debug("preview finished (no loop)")
                return False

        self._apply_anim_frame_for_preview(next_index)
        logging.debug("preview advanced to frame %s", next_index)
        return True

    def _anim_preview_tick(self):
        if not self.anim_preview_running:
            return
        if self._process_anim_preview_tick():
            self._update_preview_status()
            self._schedule_anim_preview_tick()

    def _update_preview_status(self):
        if not hasattr(self, "status"):
            return
        if not self.anim_preview_running or self.current_animation is None:
            if hasattr(self, "anim_preview_status"):
                self.anim_preview_status.config(text="")
            return

        anim = self.animations[self.current_animation]
        frames = anim["frames"]
        frame = frames[self._anim_preview_index]
        total = len(frames)
        sf_elapsed = self.anim_preview_frame_counter + 1
        sf_total = frame["duration"]
        txt = (
            f"PREVIEW: {anim['name']} | Frame {self._anim_preview_index + 1}/{total} | "
            f"sf {sf_elapsed}/{sf_total}"
        )
        if os.environ.get("SPRITE_EDITOR_DEBUG") and self._preview_fps_window_start:
            self._preview_fps_ticks += 1
            elapsed = time.perf_counter() - self._preview_fps_window_start
            if elapsed >= 1.0:
                fps = self._preview_fps_ticks / elapsed
                txt += f" | {fps:.1f} sf/s"
                self._preview_fps_ticks = 0
                self._preview_fps_window_start = time.perf_counter()
        self.status.config(text=txt)
        if hasattr(self, "anim_preview_status"):
            self.anim_preview_status.config(text=txt)

    def _set_preview_ui_state(self, enabled: bool):
        state = tk.NORMAL if enabled else tk.DISABLED
        for widget_name in (
            "anim_play_btn",
            "anim_combo",
            "anim_frame_list",
            "sprite_list",
        ):
            if hasattr(self, widget_name):
                try:
                    getattr(self, widget_name).config(state=state)
                except tk.TclError:
                    pass
        if hasattr(self, "anim_stop_btn"):
            self.anim_stop_btn.config(
                state=tk.DISABLED if enabled else tk.NORMAL
            )

    def _on_window_close(self):
        self.stop_anim_preview()
        self.root.destroy()

    def _toggle_preview_shortcut(self, event=None):
        if self.current_animation is None:
            return None
        self.toggle_anim_preview()
        return "break"

    def stop_anim_preview_timer_only(self):
        """Cancel scheduled ticks without restoring edit state (for tests)."""
        self.anim_preview_running = False
        if self._anim_preview_after_id is not None:
            self.root.after_cancel(self._anim_preview_after_id)
            self._anim_preview_after_id = None

    def _reset_animation_state(self):
        self.stop_anim_preview()
        self.current_animation = None
        self.current_anim_frame = 0
        self.anim_edit_mode = False
        self.anim_preview_running = False
        self.anim_preview_frame_counter = 0
        self._anim_preview_index = 0
        self._frame_edit_snapshot = None
        self._static_stack_mask = None
        self._static_stack_enabled = None
        self._preview_return_to_frame_edit = False
        if hasattr(self, "stack_enabled_checkbox"):
            self._bind_stack_enabled_handler("static")
        self._refresh_animation_ui()

    def _bind_stack_enabled_handler(self, source):
        if not hasattr(self, "stack_enabled_checkbox"):
            return
        if source == "frame":
            self.stack_enabled_checkbox.config(
                command=self._on_stack_enabled_changed_frame
            )
        else:
            self.stack_enabled_checkbox.config(
                command=self._on_stack_enabled_changed_static
            )

    def _on_stack_enabled_changed_static(self):
        self.refresh_views()

    def _on_stack_enabled_changed_frame(self):
        if self.anim_preview_running:
            return
        if self._frame_edit_snapshot is not None:
            self._frame_edit_snapshot["stack_enabled"] = self.stack_enabled.get()
        self.refresh_views()

    def _on_stack_checkbox_changed(self):
        if self.anim_preview_running:
            return
        if self.anim_edit_mode and self._frame_edit_snapshot is not None:
            self._frame_edit_snapshot["stack_mask"] = [v.get() for v in self.stack_vars]
        self.refresh_views()

    def _capture_stack_mask(self):
        mask = [v.get() for v in self.stack_vars]
        if self.current_sprite < len(mask):
            mask[self.current_sprite] = True
        return mask

    def _capture_current_state_as_frame(self, duration=4):
        if self.anim_edit_mode and self._frame_edit_snapshot is not None:
            return {
                "duration": duration,
                "stack_enabled": self._frame_edit_snapshot["stack_enabled"],
                "stack_mask": self._frame_edit_snapshot["stack_mask"][:],
                "sprites": deep_copy_sprites(self._frame_edit_snapshot["sprites"]),
            }
        return {
            "duration": duration,
            "stack_enabled": self.stack_enabled.get(),
            "stack_mask": self._capture_stack_mask(),
            "sprites": deep_copy_sprites(self.sprites),
        }

    def _unique_animation_name(self, base):
        existing = {anim["name"].lower() for anim in self.animations}
        if base.lower() not in existing:
            return base
        index = 1
        while f"{base}_{index}".lower() in existing:
            index += 1
        return f"{base}_{index}"

    def _current_animation(self):
        if self.current_animation is None:
            return None
        return self.animations[self.current_animation]

    def create_animation(self, name=None):
        if name is None:
            name = self._unique_animation_name(f"anim_{len(self.animations)}")
        self.animations.append({"name": name, "loop": True, "frames": []})
        self.current_animation = len(self.animations) - 1
        self._refresh_animation_ui()

    def rename_animation(self, index, name):
        name = name.strip()
        if not name:
            raise ValueError("Animation name cannot be empty.")
        lowered = name.lower()
        for i, anim in enumerate(self.animations):
            if i != index and anim["name"].lower() == lowered:
                raise ValueError(f"Animation '{name}' already exists.")
        self.animations[index]["name"] = name
        self._refresh_animation_ui()

    def rename_animation_dialog(self):
        if self.current_animation is None:
            messagebox.showinfo("Rename Animation", "Select an animation first.")
            return
        current_name = self.animations[self.current_animation]["name"]
        name = simpledialog.askstring(
            "Rename Animation", "Animation name:", initialvalue=current_name
        )
        if not name:
            return
        try:
            self.rename_animation(self.current_animation, name)
        except ValueError as exc:
            messagebox.showerror("Rename Animation", str(exc))

    def delete_animation(self):
        if self.current_animation is None:
            return
        name = self.animations[self.current_animation]["name"]
        if not messagebox.askyesno("Delete Animation", f"Delete animation '{name}'?"):
            return
        if self.anim_edit_mode:
            self._leave_anim_frame_edit()
        del self.animations[self.current_animation]
        if self.animations:
            self.current_animation = min(self.current_animation, len(self.animations) - 1)
        else:
            self.current_animation = None
        self._refresh_animation_ui()
        self.refresh_views()

    def duplicate_animation(self):
        if self.current_animation is None:
            messagebox.showinfo("Duplicate Animation", "Select an animation first.")
            return
        source = self.animations[self.current_animation]
        copy = deep_copy_animation(source)
        copy["name"] = self._unique_animation_name(f"{source['name']}_copy")
        self.animations.append(copy)
        self.current_animation = len(self.animations) - 1
        self._refresh_animation_ui()

    def add_anim_frame(self):
        if self.current_animation is None:
            messagebox.showinfo("Capture Frame", "Select or create an animation first.")
            return
        anim = self._current_animation()
        if len(anim["frames"]) >= MAX_FRAMES_PER_ANIM:
            messagebox.showinfo(
                "Capture Frame",
                f"Maximum of {MAX_FRAMES_PER_ANIM} frames per animation.",
            )
            return
        duration = self.anim_duration_var.get() if hasattr(self, "anim_duration_var") else 4
        anim["frames"].append(self._capture_current_state_as_frame(duration=duration))
        new_index = len(anim["frames"]) - 1
        self._refresh_animation_ui(select_frame=False)
        self.select_anim_frame(new_index)

    def delete_anim_frame(self):
        if self.current_animation is None:
            return
        anim = self._current_animation()
        if not anim["frames"]:
            return
        index = self.current_anim_frame
        if not messagebox.askyesno("Delete Frame", f"Delete frame {index}?"):
            return
        if self.anim_edit_mode:
            self._leave_anim_frame_edit()
        del anim["frames"][index]
        if anim["frames"]:
            self.current_anim_frame = min(index, len(anim["frames"]) - 1)
            self.select_anim_frame(self.current_anim_frame)
        else:
            self.current_anim_frame = 0
            self._refresh_animation_ui()
            self.refresh_views()

    def move_anim_frame(self, direction):
        if self.current_animation is None:
            return
        anim = self._current_animation()
        frames = anim["frames"]
        if not frames:
            return
        index = self.current_anim_frame
        new_index = index + direction
        if new_index < 0 or new_index >= len(frames):
            return
        if self.anim_edit_mode:
            self.commit_anim_frame()
        frames[index], frames[new_index] = frames[new_index], frames[index]
        self.current_anim_frame = new_index
        if self.anim_edit_mode:
            self.select_anim_frame(new_index)
        else:
            self._refresh_animation_ui()

    def commit_anim_frame(self):
        if not self.anim_edit_mode or self._frame_edit_snapshot is None:
            return
        if self.current_animation is None:
            return
        duration = self._frame_edit_snapshot.get("duration", 4)
        if not (1 <= duration <= 255):
            messagebox.showerror("Invalid Duration", "Duration must be 1–255 screen frames.")
            return
        self.animations[self.current_animation]["frames"][self.current_anim_frame] = (
            deep_copy_frame(self._frame_edit_snapshot)
        )

    def select_anim_frame(self, index):
        if self.anim_preview_running:
            return
        if self.current_animation is None:
            return
        anim = self._current_animation()
        if index < 0 or index >= len(anim["frames"]):
            return
        if (
            self.anim_edit_mode
            and self._frame_edit_snapshot is not None
            and index == self.current_anim_frame
        ):
            return
        if self.anim_edit_mode and self._frame_edit_snapshot is not None:
            self.commit_anim_frame()
        if self._static_stack_mask is None:
            self._static_stack_mask = [v.get() for v in self.stack_vars]
            self._static_stack_enabled = self.stack_enabled.get()
        frame = anim["frames"][index]
        self._frame_edit_snapshot = normalize_frame_slots(
            deep_copy_frame(frame),
            len(self.sprites),
            self.sprite_size_mode,
            self.current_color,
        )
        self.current_anim_frame = index
        self.anim_edit_mode = True
        self.stack_enabled.set(self._frame_edit_snapshot["stack_enabled"])
        self._bind_stack_enabled_handler("frame")
        self.rebuild_sprite_list(
            source="frame", mask=self._frame_edit_snapshot["stack_mask"]
        )
        self._sync_animation_panel_from_snapshot()
        self.refresh_views()

    def _leave_anim_frame_edit(self):
        self._frame_edit_snapshot = None
        self.anim_edit_mode = False
        if self._static_stack_enabled is not None:
            self.stack_enabled.set(self._static_stack_enabled)
        self._bind_stack_enabled_handler("static")
        self.rebuild_sprite_list(source="static")
        self._static_stack_mask = None
        self._static_stack_enabled = None
        self._refresh_animation_ui()
        self.refresh_views()

    def exit_animation_mode(self, commit=True):
        if commit and self.anim_edit_mode:
            self.commit_anim_frame()
        self._leave_anim_frame_edit()

    def cancel_animation_mode(self):
        self._leave_anim_frame_edit()

    def _on_animation_selected(self, _event=None):
        selection = self.anim_combo.get()
        if not selection:
            if self.anim_edit_mode:
                self.cancel_animation_mode()
            self.current_animation = None
            self._refresh_animation_ui()
            self.refresh_views()
            return
        for index, anim in enumerate(self.animations):
            if anim["name"] == selection:
                if self.anim_edit_mode:
                    self.exit_animation_mode(commit=True)
                self.current_animation = index
                self.current_anim_frame = 0
                self._refresh_animation_ui()
                self.refresh_views()
                return

    def _on_anim_frame_selected(self, _event=None):
        if self._suppress_anim_ui_events or self.current_animation is None:
            return
        selection = self.anim_frame_list.curselection()
        if selection:
            self.select_anim_frame(selection[0])

    def _set_anim_frame_list_selection(self, index):
        if not hasattr(self, "anim_frame_list"):
            return
        self._suppress_anim_ui_events = True
        try:
            self.anim_frame_list.selection_clear(0, tk.END)
            self.anim_frame_list.selection_set(index)
            self.anim_frame_list.activate(index)
        finally:
            self._suppress_anim_ui_events = False

    def _set_anim_duration_var(self, value):
        if not hasattr(self, "anim_duration_var"):
            return
        self._suppress_anim_ui_events = True
        try:
            self.anim_duration_var.set(value)
        finally:
            self._suppress_anim_ui_events = False

    def _on_duration_changed(self):
        if self._suppress_anim_ui_events:
            return
        if not self.anim_edit_mode or self._frame_edit_snapshot is None:
            return
        try:
            duration = int(self.anim_duration_var.get())
        except (tk.TclError, ValueError):
            return
        if 1 <= duration <= 255:
            self._frame_edit_snapshot["duration"] = duration
            self._refresh_animation_ui(select_frame=False)

    def _on_loop_changed(self):
        if self.current_animation is None:
            return
        self.animations[self.current_animation]["loop"] = self.anim_loop_var.get()

    def _sync_animation_panel_from_snapshot(self):
        if self._frame_edit_snapshot is None:
            return
        self._set_anim_duration_var(self._frame_edit_snapshot["duration"])
        if self.current_animation is not None and hasattr(self, "anim_loop_var"):
            self.anim_loop_var.set(self.animations[self.current_animation]["loop"])
        self._set_anim_frame_list_selection(self.current_anim_frame)

    def _refresh_animation_ui(self, select_frame=True):
        if not hasattr(self, "anim_combo"):
            return
        names = [anim["name"] for anim in self.animations]
        self.anim_combo["values"] = names
        if self.current_animation is not None and self.current_animation < len(names):
            self.anim_combo.set(names[self.current_animation])
            anim = self.animations[self.current_animation]
            self.anim_loop_var.set(anim.get("loop", True))
        else:
            self.anim_combo.set("")
            self.anim_loop_var.set(True)

        self.anim_frame_list.delete(0, tk.END)
        if self.current_animation is not None:
            for index, frame in enumerate(self.animations[self.current_animation]["frames"]):
                label = f"Frame {index} ({frame['duration']} sf)"
                self.anim_frame_list.insert(tk.END, label)
            if select_frame and self.animations[self.current_animation]["frames"]:
                self._set_anim_frame_list_selection(self.current_anim_frame)
                if self.anim_edit_mode and self._frame_edit_snapshot is not None:
                    self._set_anim_duration_var(self._frame_edit_snapshot["duration"])

    def _on_escape(self, event=None):
        if self.anim_preview_running:
            self.stop_anim_preview()
            return "break"
        if self.anim_edit_mode:
            self.cancel_animation_mode()
            return "break"
        return None

    def _capture_frame_shortcut(self, event=None):
        self.add_anim_frame()
        return "break"

    def get_stacked_sprites(self):
        stacked = [i for i, var in enumerate(self.stack_vars) if var.get()]
        if self.current_sprite not in stacked:
            stacked.append(self.current_sprite)
        return sorted(stacked)

    def _resolve_stack_indices(self, stack_mask, stack_enabled, current_sprite):
        if not stack_enabled:
            return [current_sprite]
        return sorted(i for i, enabled in enumerate(stack_mask) if enabled)

    def _get_active_sprite_state(self):
        if self.anim_preview_running and self.current_animation is not None:
            frame = self.animations[self.current_animation]["frames"][
                self._anim_preview_index
            ]
            return frame["sprites"], frame["stack_enabled"], frame["stack_mask"]
        if self.anim_edit_mode and self._frame_edit_snapshot is not None:
            snapshot = self._frame_edit_snapshot
            return snapshot["sprites"], snapshot["stack_enabled"], snapshot["stack_mask"]
        mask = [var.get() for var in self.stack_vars]
        if self.current_sprite < len(mask):
            mask[self.current_sprite] = True
        return self.sprites, self.stack_enabled.get(), mask

    def _render_composite(
        self,
        target_canvas,
        sprites,
        stack_enabled,
        stack_mask,
        current_sprite,
        *,
        pixel_size=None,
        draw_off_pixels=False,
        transparent_color="#000000",
        outline="#666666",
    ):
        size = self.sprite_size_mode
        ps = pixel_size or (160 // size)
        indices = self._resolve_stack_indices(
            stack_mask, stack_enabled, current_sprite
        )

        if not stack_enabled:
            sprite_data = sprites[current_sprite]
            pattern = sprite_data["pattern"]
            color = sprite_data["color"]
            fg_hex = (
                self.rgb_to_hex(TI_COLORS[color])
                if color != 0
                else transparent_color
            )
            for y in range(size):
                for x in range(size):
                    is_on = pattern[y][x] == 1
                    if is_on or draw_off_pixels:
                        fill = fg_hex if is_on else "#555555"
                        px, py = x * ps, y * ps
                        target_canvas.create_rectangle(
                            px, py, px + ps, py + ps, fill=fill, outline=outline
                        )
            return

        for idx in indices:
            sprite_data = sprites[idx]
            pattern = sprite_data["pattern"]
            color = sprite_data["color"]
            fg_hex = (
                self.rgb_to_hex(TI_COLORS[color])
                if color != 0
                else transparent_color
            )
            for y in range(size):
                for x in range(size):
                    if pattern[y][x] == 1:
                        px, py = x * ps, y * ps
                        target_canvas.create_rectangle(
                            px, py, px + ps, py + ps, fill=fg_hex, outline=outline
                        )

    def update_canvas(self):
        self.canvas.delete("all")
        size = self.sprite_size_mode
        pixel_size = self.zoom
        self.canvas.config(width=size * pixel_size + 4, height=size * pixel_size + 4)
        sprites, stack_enabled, stack_mask = self._get_active_sprite_state()
        self._render_composite(
            self.canvas,
            sprites,
            stack_enabled,
            stack_mask,
            self.current_sprite,
            pixel_size=pixel_size,
            draw_off_pixels=not stack_enabled,
            transparent_color="#aaaaaa",
            outline="#666666",
        )
    
    def _active_sprites(self):
        if self.anim_edit_mode and self._frame_edit_snapshot is not None:
            return self._frame_edit_snapshot["sprites"]
        return self.sprites

    def draw_pixel(self, event):
        if self.anim_preview_running:
            return
        size = self.sprite_size_mode
        ps = self.zoom
        x = event.x // ps
        y = event.y // ps
        if 0 <= x < size and 0 <= y < size:
            sprite_data = self._active_sprites()[self.current_sprite]
            if self.current_color == 0:
                sprite_data["pattern"][y][x] = 0
            else:
                sprite_data["pattern"][y][x] = 1
                sprite_data["color"] = self.current_color
            self.refresh_views()
    
    def erase_pixel(self, event):
        if self.anim_preview_running:
            return
        size = self.sprite_size_mode
        ps = self.zoom
        x = event.x // ps
        y = event.y // ps
        if 0 <= x < size and 0 <= y < size:
            self._active_sprites()[self.current_sprite]["pattern"][y][x] = 0
            self.refresh_views()
    
    def select_sprite(self, event=None):
        if self.anim_preview_running:
            return
        sel = self.sprite_list.curselection()
        if sel:
            self.current_sprite = sel[0]
            self.current_color = self._active_sprites()[self.current_sprite]["color"]
            self.refresh_views()
    
    def update_status(self):
        sprites = self._active_sprites()
        sprite_data = sprites[self.current_sprite]
        col = sprite_data["color"]
        txt = (
            f"Sprite {self.current_sprite:02d} | "
            f"{self.sprite_size_mode}×{self.sprite_size_mode} | "
            f"Color: {col} {COLOR_NAMES[col]} | "
            f"Stacking: {'ON' if self.stack_enabled.get() else 'OFF'}"
        )
        if self.anim_edit_mode:
            anim_name = ""
            if self.current_animation is not None:
                anim_name = self.animations[self.current_animation]["name"]
            txt += f" | ANIM: {anim_name} / Frame {self.current_anim_frame} / EDIT"
        elif self.current_animation is not None:
            anim = self.animations[self.current_animation]
            txt += f" | ANIM: {anim['name']} ({len(anim['frames'])} frames)"
        self.status.config(text=txt)
    
    def update_preview(self):
        self.preview_canvas.delete("all")
        sprites, stack_enabled, stack_mask = self._get_active_sprite_state()
        self._render_composite(
            self.preview_canvas,
            sprites,
            stack_enabled,
            stack_mask,
            self.current_sprite,
            pixel_size=160 // self.sprite_size_mode,
            draw_off_pixels=False,
            transparent_color="#000000",
            outline="",
        )
    
    def clear_current(self):
        if self.anim_preview_running:
            return
        sprite_data = self._active_sprites()[self.current_sprite]
        size = self.sprite_size_mode
        sprite_data["pattern"] = [[0] * size for _ in range(size)]
        self.refresh_views()
    
    def fill_sprite(self):
        if self.anim_preview_running:
            return
        if messagebox.askyesno("Fill", "Fill sprite with current color?"):
            sprite_data = self._active_sprites()[self.current_sprite]
            size = self.sprite_size_mode
            sprite_data["pattern"] = [[1] * size for _ in range(size)]
            if self.current_color != 0:
                sprite_data["color"] = self.current_color
            self.refresh_views()
    
    def copy_to_next(self):
        if self.anim_preview_running:
            return
        sprites = self._active_sprites()
        if self.current_sprite < len(sprites) - 1:
            nxt = self.current_sprite + 1
            src = sprites[self.current_sprite]
            sprites[nxt] = {
                "pattern": [row[:] for row in src["pattern"]],
                "color": src["color"],
            }
            messagebox.showinfo("Copy", f"Copied to Sprite {nxt:02d}")
        else:
            messagebox.showinfo("Copy", "No next sprite. Use Add Sprite first.")
    
    def new_project(self):
        if messagebox.askyesno("New Project", "Clear everything?"):
            self._reset_animation_state()
            self.animations = []
            self.init_sprites(1)
            self.current_sprite = 0
            self.current_color = 2
            self.rebuild_sprite_list()
            self._refresh_animation_ui()
            self.refresh_views()

    def save_project(self):
        fn = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("JSON", "*.json")]
        )
        if fn:
            data = {
                "version": 2,
                "mode": self.sprite_size_mode,
                "sprites": self.sprites,
                "animations": self.animations,
            }
            with open(fn, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            messagebox.showinfo("Saved", "Project saved.")

    def load_project_data(self, data: dict) -> list[str]:
        """Load project dict into editor state. Returns validation warnings."""
        self.sprite_size_mode = data["mode"]
        self.sprites = data["sprites"]
        if not self.sprites:
            self.init_sprites(1)
        version = data.get("version", 1)
        anims = data.get("animations", []) if version >= 2 else []
        self.animations, warnings = validate_and_sanitize_animations(
            anims,
            self.sprite_size_mode,
            target_slot_count=len(self.sprites),
        )
        self._reset_animation_state()
        self.current_sprite = 0
        self.current_color = self.sprites[0]["color"]
        self.rebuild_sprite_list()
        self._refresh_animation_ui()
        self.refresh_views()
        return warnings

    def load_project(self):
        fn = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if fn:
            with open(fn, encoding="utf-8") as f:
                raw = f.read()
            if len(raw) > MAX_FILE_BYTES_WARN:
                messagebox.showwarning(
                    "Large File", "Project file exceeds 5 MB; load may be slow."
                )
            data = json.loads(raw)
            warnings = self.load_project_data(data)
            if warnings:
                messagebox.showwarning("Load Validation", "\n".join(warnings))
            messagebox.showinfo("Loaded", "Project loaded.")
    
    def _pattern_row_byte(self, pattern, y, x0):
        b = 0
        for x in range(8):
            if pattern[y][x0 + x]:
                b |= (1 << (7 - x))
        return b

    def _pattern_to_bytes(self, pattern, size):
        if size == 8:
            return [self._pattern_row_byte(pattern, y, 0) for y in range(8)]
        bytes_list = []
        for y in range(8):
            bytes_list.append(self._pattern_row_byte(pattern, y, 0))
        for y in range(8, 16):
            bytes_list.append(self._pattern_row_byte(pattern, y, 0))
        for y in range(8):
            bytes_list.append(self._pattern_row_byte(pattern, y, 8))
        for y in range(8, 16):
            bytes_list.append(self._pattern_row_byte(pattern, y, 8))
        return bytes_list

    def _build_asm_for_sprite_data(self, sprite, slot_index):
        pattern = sprite["pattern"]
        col = sprite["color"]
        size = self.sprite_size_mode
        bytes_list = self._pattern_to_bytes(pattern, size)
        asm = f"; TI-99 Sprite {slot_index:02d} {size}x{size} Color {col}\n"
        for i in range(0, len(bytes_list), 8):
            chunk = bytes_list[i:i + 8]
            hex_vals = ",".join(f">{b:02X}" for b in chunk)
            asm += f"BYTE {hex_vals}\n"
        return asm

    def build_asm_text(self, sprite_index=None):
        if sprite_index is None:
            sprite_index = self.current_sprite
        sprites, _, _ = self._get_active_sprite_state()
        return self._build_asm_for_sprite_data(sprites[sprite_index], sprite_index)

    def build_animation_asm(self, anim_index):
        anim = self.animations[anim_index]
        frames = anim.get("frames", [])
        lines = [f"; Animation '{anim['name']}' — {len(frames)} frames"]
        durations = []
        for index, frame in enumerate(frames):
            durations.append(frame["duration"])
            lines.append(f"; Frame {index}: duration={frame['duration']} screen frames")
            indices = self._resolve_stack_indices(
                frame["stack_mask"], frame["stack_enabled"], self.current_sprite
            )
            for slot_idx in indices:
                lines.append(
                    self._build_asm_for_sprite_data(frame["sprites"][slot_idx], slot_idx)
                )
            lines.append("")
        total_sf = sum(durations)
        lines.append(f"; Durations (screen frames): {', '.join(str(d) for d in durations)}")
        lines.append(
            f"; Total cycle: {total_sf} screen frames (~{total_sf / 59.94 * 1000:.0f} ms)"
        )
        return "\n".join(lines)

    def _build_asm_panel_text(self):
        if self.anim_preview_running and self.current_animation is not None:
            frames = self.animations[self.current_animation]["frames"]
            header = f"; Preview frame {self._anim_preview_index + 1}/{len(frames)}\n"
            return header + self.build_asm_text()

        asm = self.build_asm_text()
        if (
            not self.anim_edit_mode
            and self.current_animation is not None
            and self.animations[self.current_animation]["frames"]
        ):
            anim = self.animations[self.current_animation]
            header = f"; Animation '{anim['name']}' ({len(anim['frames'])} frames)\n"
            asm = header + asm
        return asm

    def update_asm_export(self):
        if not hasattr(self, "asm_text"):
            return
        asm = self._build_asm_panel_text()
        self.asm_text.delete("1.0", tk.END)
        self.asm_text.insert("1.0", asm)

    def copy_asm(self):
        asm = self._build_asm_panel_text()
        self.root.clipboard_clear()
        self.root.clipboard_append(asm)

    def copy_animation_asm(self):
        if self.current_animation is None:
            messagebox.showinfo(
                "Export Animation ASM", "Select an animation with at least one frame."
            )
            return
        if not self.animations[self.current_animation].get("frames"):
            messagebox.showinfo(
                "Export Animation ASM", "This animation has no frames to export."
            )
            return
        asm = self.build_animation_asm(self.current_animation)
        self.root.clipboard_clear()
        self.root.clipboard_append(asm)
        messagebox.showinfo("Export Animation ASM", "Animation assembly copied to clipboard.")

    def _copy_asm_shortcut(self, event=None):
        self.copy_asm()
        return "break"

if __name__ == "__main__":
    root = tk.Tk()
    app = SpriteEditor(root)
    root.mainloop()