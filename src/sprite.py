import json
import logging
import os
import time
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from animation_schema import (
    MAX_FILE_BYTES_WARN,
    MAX_FRAMES_PER_ANIM,
    compact_frame_slots,
    create_empty_sprite_dict,
    deep_copy_animation,
    deep_copy_frame,
    deep_copy_sprite,
    deep_copy_sprites,
    default_sprite_name,
    ensure_sprite_names,
    frames_equal,
    sprite_display_name,
    validate_and_sanitize_animations,
)

APP_NAME = "TMS9918 Sprite Editor"

# TMS9918 VDP colors (approximate RGB for display)
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
CANVAS_BG = "#777777"
CANVAS_GRID_OUTLINE = "#555555"
CANVAS_OFF_PIXEL = "#555555"

if os.environ.get("SPRITE_EDITOR_DEBUG"):
    logging.basicConfig(level=logging.DEBUG)

class SpriteEditor:
    def __init__(self, root, create_ui=True):
        self.root = root
        self.root.title(APP_NAME)
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
        for index in range(count):
            pattern = [[0 for _ in range(size)] for _ in range(size)]
            self.sprites.append(
                {
                    "pattern": pattern,
                    "color": self.current_color,
                    "name": default_sprite_name(index),
                }
            )

    def create_empty_sprite(self):
        size = self.sprite_size_mode
        return {
            "pattern": [[0 for _ in range(size)] for _ in range(size)],
            "color": self.current_color,
            "name": default_sprite_name(len(self.sprites)),
        }

    def _sprite_display_name(self, index):
        if index < 0 or index >= len(self.sprites):
            return default_sprite_name(index)
        return sprite_display_name(self.sprites[index], index)

    def _active_sprite_count(self):
        if self.anim_edit_mode and self._frame_edit_snapshot is not None:
            return len(self._frame_edit_snapshot["sprites"])
        return len(self.sprites)

    def _current_sprite_display_name(self):
        if self.anim_edit_mode and self._frame_edit_snapshot is not None:
            sprites = self._frame_edit_snapshot["sprites"]
            if 0 <= self.current_sprite < len(sprites):
                return sprite_display_name(sprites[self.current_sprite], self.current_sprite)
        return self._sprite_display_name(self.current_sprite)

    def _sprite_display_name_at(self, index, source="static"):
        if source == "frame" and self._frame_edit_snapshot is not None:
            sprites = self._frame_edit_snapshot["sprites"]
            if 0 <= index < len(sprites):
                return sprite_display_name(sprites[index], index)
        return self._sprite_display_name(index)
    
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

        left_outer = ttk.Frame(main_frame, width=300)
        left_outer.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        left_outer.pack_propagate(False)

        palette_frame = ttk.LabelFrame(
            left_outer, text="TMS9918 Palette (T=Transparent)"
        )
        palette_frame.pack(fill=tk.X)
        for column in range(4):
            palette_frame.columnconfigure(column, weight=1, uniform="palette_col")
        for row in range(4):
            palette_frame.rowconfigure(row, weight=1)

        for i in range(16):
            color_hex = "#aaaaaa" if i == 0 else self.rgb_to_hex(TI_COLORS[i])
            btn = tk.Canvas(
                palette_frame,
                height=28,
                bg=color_hex,
                highlightthickness=1,
                highlightbackground="#888888",
                cursor="hand2",
            )
            if i == 0:

                def _draw_transparent_swatch(event, canvas=btn):
                    width = canvas.winfo_width()
                    height = canvas.winfo_height()
                    if width < 2 or height < 2:
                        return
                    canvas.delete("all")
                    canvas.configure(bg="#aaaaaa")
                    canvas.create_text(
                        width / 2,
                        height / 2,
                        text="T",
                        fill="black",
                        font=("Arial", 10, "bold"),
                    )

                btn.bind("<Configure>", _draw_transparent_swatch)
            btn.bind("<Button-1>", lambda e, c=i: self.set_color(c))
            btn.grid(row=i // 4, column=i % 4, padx=2, pady=2, sticky="nsew")

        color_indicator_row = ttk.Frame(palette_frame)
        color_indicator_row.grid(row=4, column=0, columnspan=4, sticky="ew", padx=5, pady=(4, 5))
        self._current_color_label = ttk.Label(color_indicator_row, text="", anchor="w")
        self._current_color_label.pack(side=tk.LEFT, fill="x", expand=True)
        self._current_color_swatch = tk.Canvas(
            color_indicator_row,
            width=40,
            height=26,
            highlightthickness=2,
            highlightbackground="#333333",
        )
        self._current_color_swatch.pack(side=tk.RIGHT)

        self.sprites_panel = ttk.LabelFrame(left_outer, text="Project Sprites")
        self.sprites_panel.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        
        # Center: Drawing Canvas (now supports stacking)
        self.canvas_frame = ttk.LabelFrame(
            main_frame,
            text="Drawing Canvas - Stacked View (LMB=draw on current, RMB=erase on current)",
        )
        self.canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10)

        self.mode_indicator = tk.Label(
            self.canvas_frame,
            text="",
            font=("Arial", 11, "bold"),
            anchor="w",
            padx=10,
            pady=6,
        )
        self.mode_indicator.pack(fill="x", padx=5, pady=(5, 0))
        
        self.canvas = tk.Canvas(self.canvas_frame, bg="#777777")
        self.canvas.pack(pady=10)
        self.canvas.bind("<Button-1>", self.draw_pixel)
        self.canvas.bind("<B1-Motion>", self.draw_pixel)
        self.canvas.bind("<Button-3>", self.erase_pixel)
        self.canvas.bind("<B3-Motion>", self.erase_pixel)

        asm_frame = ttk.LabelFrame(self.canvas_frame, text="Assembly Export")
        asm_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 5))

        self.asm_text = tk.Text(asm_frame, height=6, font=("Courier", 10), wrap=tk.NONE)
        self.asm_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.asm_text.bind("<Key>", lambda e: "break")
        
        right_outer = ttk.Frame(main_frame, width=280)
        right_outer.pack(side=tk.RIGHT, fill=tk.Y)
        right_outer.pack_propagate(False)

        right_frame = ttk.Frame(right_outer)
        right_frame.pack(fill=tk.BOTH, expand=True)
        list_frame = ttk.Frame(self.sprites_panel)
        list_frame.pack(pady=5, fill="x", padx=5)

        header_row = ttk.Frame(list_frame)
        header_row.pack(fill="x")
        ttk.Label(header_row, text="Stack").pack(side=tk.RIGHT)
        order_controls = ttk.Frame(header_row)
        order_controls.pack(side=tk.RIGHT, padx=(0, 6))
        self._sprite_move_up_btn = ttk.Button(
            order_controls, text="↑", width=2, command=lambda: self.move_sprite(-1)
        )
        self._sprite_move_up_btn.pack(side=tk.LEFT)
        self._sprite_move_down_btn = ttk.Button(
            order_controls, text="↓", width=2, command=lambda: self.move_sprite(1)
        )
        self._sprite_move_down_btn.pack(side=tk.LEFT, padx=(2, 0))
        ttk.Label(header_row, text="Sprite").pack(side=tk.LEFT, fill="x", expand=True)

        slots_scroll_frame = ttk.Frame(list_frame)
        slots_scroll_frame.pack(fill="x", pady=(2, 0))
        slots_scroll_frame.columnconfigure(0, weight=1)
        slots_scroll_frame.rowconfigure(0, weight=1)
        self._sprite_slots_canvas = tk.Canvas(
            slots_scroll_frame,
            height=self._sprite_slot_row_height() * 10,
            highlightthickness=1,
            highlightbackground="#aaaaaa",
            borderwidth=0,
            bg="#ffffff",
        )
        self._sprite_slots_canvas.grid(row=0, column=0, sticky="nsew")
        self._sprite_slots_scrollbar = tk.Scrollbar(
            slots_scroll_frame,
            orient=tk.VERTICAL,
            width=16,
            command=self._sprite_slots_canvas.yview,
        )
        self._sprite_slots_scrollbar.grid(row=0, column=1, sticky="ns")
        self._sprite_slots_canvas.config(
            yscrollcommand=self._sprite_slots_yscrollcommand
        )
        self.sprite_slots_inner = tk.Frame(self._sprite_slots_canvas, bg="#ffffff")
        self._sprite_slots_window = self._sprite_slots_canvas.create_window(
            (0, 0), window=self.sprite_slots_inner, anchor=tk.NW
        )
        self.sprite_slots_inner.bind("<Configure>", self._update_sprite_slots_scroll_region)
        self._sprite_slots_canvas.bind("<Configure>", self._resize_sprite_slots_window)

        self._sprite_slot_rows = []
        self.stack_vars = []
        self.rebuild_sprite_list()

        sprite_btn_frame = ttk.Frame(self.sprites_panel)
        sprite_btn_frame.pack(fill="x", pady=5, padx=5)
        ttk.Button(sprite_btn_frame, text="Add", command=self.add_sprite).pack(
            side=tk.LEFT, expand=True, fill="x", padx=(0, 3)
        )
        ttk.Button(sprite_btn_frame, text="Remove", command=self.remove_sprite).pack(
            side=tk.LEFT, expand=True, fill="x", padx=(3, 0)
        )

        ttk.Button(
            self.sprites_panel, text="Rename", command=self.rename_sprite_dialog
        ).pack(pady=(0, 5), fill="x", padx=5)

        self.stack_enabled_checkbox = ttk.Checkbutton(
            self.sprites_panel,
            text="Enable Stacking",
            variable=self.stack_enabled,
            command=self._on_stack_enabled_changed_static,
        )
        self.stack_enabled_checkbox.pack(anchor="w", padx=5, pady=(0, 5))

        ttk.Button(self.sprites_panel, text="Clear Sprite", command=self.clear_current).pack(
            pady=2, fill="x", padx=5
        )
        ttk.Button(self.sprites_panel, text="Fill Sprite", command=self.fill_sprite).pack(
            pady=2, fill="x", padx=5
        )
        ttk.Button(
            self.sprites_panel, text="Duplicate Sprite", command=self.copy_to_next
        ).pack(pady=2, fill="x", padx=5)

        self._bind_sprite_slots_scroll(left_outer, self.sprites_panel, list_frame)

        anim_panel = ttk.LabelFrame(right_frame, text="Animations")
        anim_panel.pack(fill="x")

        anim_top = ttk.Frame(anim_panel)
        anim_top.pack(fill="x", padx=5, pady=5)
        self.anim_combo = ttk.Combobox(anim_top, state="readonly")
        self.anim_combo.pack(fill="x")
        self.anim_combo.bind("<<ComboboxSelected>>", self._on_animation_selected)

        anim_btn_row = ttk.Frame(anim_top)
        anim_btn_row.pack(fill="x", pady=(5, 0))
        ttk.Button(anim_btn_row, text="+", width=3, command=self.create_animation).pack(
            side=tk.LEFT
        )
        ttk.Button(anim_btn_row, text="−", width=3, command=self.delete_animation).pack(
            side=tk.LEFT, padx=(2, 0)
        )
        ttk.Button(
            anim_btn_row, text="Duplicate", command=self.duplicate_animation
        ).pack(side=tk.LEFT, expand=True, fill="x", padx=(4, 2))
        ttk.Button(
            anim_btn_row, text="Rename", command=self.rename_animation_dialog
        ).pack(side=tk.LEFT, expand=True, fill="x", padx=(2, 0))

        ttk.Label(anim_panel, text="Frames").pack(anchor="w", padx=5)
        frame_list_row = ttk.Frame(anim_panel)
        frame_list_row.pack(fill="x", padx=5, pady=2)
        frame_list_row.columnconfigure(0, weight=1)
        frame_list_row.rowconfigure(0, weight=1)
        self.anim_frame_list = tk.Listbox(frame_list_row, height=6, width=20)
        self.anim_frame_list.grid(row=0, column=0, sticky="nsew")
        self.anim_frame_list.bind("<<ListboxSelect>>", self._on_anim_frame_selected)
        self._anim_frame_scrollbar = tk.Scrollbar(
            frame_list_row,
            orient=tk.VERTICAL,
            width=16,
            command=self.anim_frame_list.yview,
        )
        self._anim_frame_scrollbar.grid(row=0, column=1, sticky="ns")
        self.anim_frame_list.config(yscrollcommand=self._anim_frame_scrollbar.set)

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

        frame_edit_row = ttk.Frame(anim_panel)
        frame_edit_row.pack(fill="x", padx=5, pady=(0, 5))
        self.anim_commit_btn = ttk.Button(
            frame_edit_row, text="Commit Frame", command=self.commit_anim_frame_edits
        )
        self.anim_commit_btn.pack(side=tk.LEFT, expand=True, fill="x", padx=(0, 2))
        self.anim_discard_btn = ttk.Button(
            frame_edit_row, text="Discard Changes", command=self.discard_anim_frame_edits
        )
        self.anim_discard_btn.pack(side=tk.LEFT, expand=True, fill="x", padx=(2, 0))
        self.anim_frame_dirty_label = ttk.Label(anim_panel, text="")
        self.anim_frame_dirty_label.pack(anchor="w", padx=5, pady=(0, 5))

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
        self.anim_duration_var.trace_add("write", self._on_duration_var_changed)

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
        self.anim_play_btn.pack(side=tk.LEFT, expand=True, fill="x", padx=(8, 2))
        self.anim_stop_btn = ttk.Button(
            preview_btn_row, text="■ Stop", command=self.stop_anim_preview
        )
        self.anim_stop_btn.pack(side=tk.LEFT, expand=True, fill="x", padx=(2, 8))
        self.anim_preview_status = ttk.Label(preview_frame, text="")
        self.anim_preview_status.pack(anchor="w", padx=2, pady=2)

        self._bind_anim_frame_list_scroll(right_outer, anim_panel)
        self._refresh_animation_ui()
        
        self.status = ttk.Label(self.root, text="", relief=tk.SUNKEN, anchor=tk.W)
        self.status.pack(side=tk.BOTTOM, fill=tk.X)
        
        self.update_canvas()
        self.update_status()
        self.update_asm_export()

    def _sprite_slot_row_height(self):
        return 26

    def _sprite_slot_colors(self):
        return "#ffffff", "#b8cce8"

    def _apply_sprite_slot_row_bg(self, row, bg):
        row.configure(bg=bg)
        for child in row.winfo_children():
            if isinstance(child, (tk.Label, tk.Checkbutton)):
                child.configure(bg=bg)
                if isinstance(child, tk.Checkbutton):
                    child.configure(activebackground=bg, highlightbackground=bg)

    def _sprite_slots_widget(self, widget):
        while widget is not None:
            if widget in (self._sprite_slots_canvas, self.sprite_slots_inner):
                return True
            if widget in self._sprite_slot_rows:
                return True
            if hasattr(widget, "master") and widget.master in self._sprite_slot_rows:
                return True
            widget = widget.master
        return False

    def _sprite_slots_canvas_height(self):
        height = self._sprite_slots_canvas.winfo_height()
        if height <= 1:
            return self._sprite_slot_row_height() * 10
        return height

    def _sprite_slots_content_height(self):
        self.sprite_slots_inner.update_idletasks()
        return self.sprite_slots_inner.winfo_reqheight()

    def _sprite_slots_needs_scroll(self):
        return self._sprite_slots_content_height() > self._sprite_slots_canvas_height()

    def _clamp_sprite_slots_scroll(self):
        canvas = self._sprite_slots_canvas
        if not self._sprite_slots_needs_scroll():
            canvas.yview_moveto(0)
            return
        top, _bottom = canvas.yview()
        if top < 0:
            canvas.yview_moveto(0)
            return
        content_height = self._sprite_slots_content_height()
        canvas_height = self._sprite_slots_canvas_height()
        max_top = max(0.0, 1.0 - (canvas_height / content_height))
        if top > max_top:
            canvas.yview_moveto(max_top)

    def _sprite_slots_yscrollcommand(self, first, last):
        if self._sprite_slots_needs_scroll():
            self._sprite_slots_scrollbar.set(first, last)
        else:
            self._sprite_slots_canvas.yview_moveto(0)
            self._sprite_slots_scrollbar.set(0, 1)

    def _update_sprite_slots_scroll_region(self, _event=None):
        if not hasattr(self, "_sprite_slots_canvas"):
            return
        canvas = self._sprite_slots_canvas
        inner = self.sprite_slots_inner
        inner.update_idletasks()
        width = max(canvas.winfo_width(), inner.winfo_reqwidth())
        height = inner.winfo_reqheight()
        if width > 0 and height > 0:
            canvas.configure(scrollregion=(0, 0, width, height))
        if self._sprite_slots_needs_scroll():
            self._sprite_slots_scrollbar.grid()
            self._clamp_sprite_slots_scroll()
        else:
            canvas.yview_moveto(0)
            self._sprite_slots_scrollbar.grid_remove()

    def _resize_sprite_slots_window(self, event):
        self._sprite_slots_canvas.itemconfig(self._sprite_slots_window, width=event.width)
        self._update_sprite_slots_scroll_region()

    def _scroll_listbox(self, listbox, delta):
        if not delta:
            return
        if listbox == self._sprite_slots_canvas:
            if not self._sprite_slots_needs_scroll():
                self._sprite_slots_canvas.yview_moveto(0)
                return
        listbox.yview_scroll(delta, "units")
        if listbox == self._sprite_slots_canvas:
            self._clamp_sprite_slots_scroll()

    def _bind_anim_frame_list_scroll(self, *widgets):
        listbox = self.anim_frame_list

        def _wheel_delta(event):
            if event.delta:
                return int(-1 * (event.delta / 120))
            return 0

        def _on_mousewheel(event):
            self._scroll_listbox(listbox, _wheel_delta(event))
            return "break"

        def _on_mousewheel_up(event):
            self._scroll_listbox(listbox, -1)
            return "break"

        def _on_mousewheel_down(event):
            self._scroll_listbox(listbox, 1)
            return "break"

        def _bind_scroll(_event=None):
            listbox.bind_all("<MouseWheel>", _on_mousewheel)
            listbox.bind_all("<Button-4>", _on_mousewheel_up)
            listbox.bind_all("<Button-5>", _on_mousewheel_down)

        def _unbind_scroll(_event=None):
            listbox.unbind_all("<MouseWheel>")
            listbox.unbind_all("<Button-4>")
            listbox.unbind_all("<Button-5>")

        for widget in widgets:
            widget.bind("<Enter>", _bind_scroll)
            widget.bind("<Leave>", _unbind_scroll)

    def _bind_sprite_slots_scroll(self, *widgets):
        canvas = self._sprite_slots_canvas

        def _wheel_delta(event):
            if event.delta:
                return int(-1 * (event.delta / 120))
            return 0

        def _on_mousewheel(event):
            self._scroll_listbox(canvas, _wheel_delta(event))
            return "break"

        def _on_mousewheel_up(event):
            self._scroll_listbox(canvas, -1)
            return "break"

        def _on_mousewheel_down(event):
            self._scroll_listbox(canvas, 1)
            return "break"

        def _bind_scroll(_event=None):
            canvas.bind_all("<MouseWheel>", _on_mousewheel)
            canvas.bind_all("<Button-4>", _on_mousewheel_up)
            canvas.bind_all("<Button-5>", _on_mousewheel_down)

        def _unbind_scroll(_event=None):
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")

        for widget in widgets:
            widget.bind("<Enter>", _bind_scroll)
            widget.bind("<Leave>", _unbind_scroll)

    def rgb_to_hex(self, rgb):
        return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"

    def _color_display_hex(self, color_index):
        if color_index == 0:
            return "#aaaaaa"
        return self.rgb_to_hex(TI_COLORS[color_index])

    def _draw_color_swatch(self, canvas, color_index):
        canvas.delete("all")
        hex_color = self._color_display_hex(color_index)
        canvas.configure(bg=hex_color)
        if color_index == 0:
            width = canvas.winfo_width() or int(canvas["width"])
            height = canvas.winfo_height() or int(canvas["height"])
            canvas.create_text(
                width / 2,
                height / 2,
                text="T",
                fill="black",
                font=("Arial", 9, "bold"),
            )

    def _update_color_indicator(self):
        if not hasattr(self, "_current_color_swatch"):
            return
        color = self.current_color
        self._draw_color_swatch(self._current_color_swatch, color)
        self._current_color_label.config(text=f"{color} — {COLOR_NAMES[color]}")

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
        if not hasattr(self, "sprite_slots_inner"):
            return
        old_stack = [var.get() for var in self.stack_vars]
        for child in self.sprite_slots_inner.winfo_children():
            child.destroy()
        self.stack_vars = []
        self._sprite_slot_rows = []

        slot_count = (
            len(self._frame_edit_snapshot["sprites"])
            if source == "frame" and self._frame_edit_snapshot is not None
            else len(self.sprites)
        )
        if self.current_sprite >= slot_count:
            self.current_sprite = max(0, slot_count - 1)

        normal_bg, _selected_bg = self._sprite_slot_colors()
        for i in range(slot_count):
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
            row = tk.Frame(self.sprite_slots_inner, bg=normal_bg, cursor="hand2")
            row.pack(fill="x", pady=0)
            name = tk.Label(
                row,
                text=self._sprite_display_name_at(i, source),
                bg=normal_bg,
                anchor="w",
                padx=6,
                pady=4,
            )
            name.pack(side=tk.LEFT, fill="x", expand=True)
            cb = tk.Checkbutton(
                row,
                text="",
                variable=var,
                command=self._on_stack_checkbox_changed,
                bg=normal_bg,
                activebackground=normal_bg,
                highlightthickness=0,
                highlightbackground=normal_bg,
                bd=0,
                relief=tk.FLAT,
                cursor="hand2",
            )
            cb.pack(side=tk.RIGHT, padx=(4, 8))
            for widget in (row, name):
                widget.bind(
                    "<Button-1>",
                    lambda _event, index=i: self.select_sprite_index(index),
                )
            name.bind(
                "<Double-Button-1>",
                lambda _event, index=i: self.rename_sprite_dialog(index),
            )
            self.stack_vars.append(var)
            self._sprite_slot_rows.append(row)

        self.root.after_idle(self._update_sprite_slots_scroll_region)
        if slot_count:
            self._highlight_sprite_slot(self.current_sprite)
        self._update_sprite_order_buttons()

    def _update_sprite_order_buttons(self):
        if not hasattr(self, "_sprite_move_up_btn"):
            return
        if self.anim_preview_running:
            state = tk.DISABLED
            self._sprite_move_up_btn.config(state=state)
            self._sprite_move_down_btn.config(state=state)
            return
        count = self._active_sprite_count()
        self._sprite_move_up_btn.config(
            state=tk.NORMAL if self.current_sprite > 0 else tk.DISABLED
        )
        self._sprite_move_down_btn.config(
            state=tk.NORMAL if count > 0 and self.current_sprite < count - 1 else tk.DISABLED
        )

    def _sprite_list_source(self):
        if self.anim_edit_mode and self._frame_edit_snapshot is not None:
            return "frame", self._frame_edit_snapshot["stack_mask"]
        return "static", None

    def add_sprite(self):
        if self.anim_preview_running:
            return
        if self.anim_edit_mode and self._frame_edit_snapshot is not None:
            snapshot = self._frame_edit_snapshot
            size = self.sprite_size_mode
            new_index = len(snapshot["sprites"])
            snapshot["sprites"].append(
                create_empty_sprite_dict(
                    size,
                    self.current_color,
                    default_sprite_name(new_index),
                )
            )
            snapshot["stack_mask"].append(True)
            self.current_sprite = new_index
            self.rebuild_sprite_list(
                source="frame", mask=snapshot["stack_mask"]
            )
            self.refresh_views()
            return
        self.sprites.append(self.create_empty_sprite())
        self.current_sprite = len(self.sprites) - 1
        source, mask = self._sprite_list_source()
        self.rebuild_sprite_list(source=source, mask=mask)
        self.refresh_views()

    def remove_sprite(self):
        if self.anim_preview_running:
            return
        if self.anim_edit_mode and self._frame_edit_snapshot is not None:
            snapshot = self._frame_edit_snapshot
            if len(snapshot["sprites"]) <= 1:
                messagebox.showinfo(
                    "Remove Sprite", "At least one sprite is required in this frame."
                )
                return
            if not messagebox.askyesno(
                "Remove Sprite",
                f"Remove '{self._current_sprite_display_name()}' from this frame?",
            ):
                return
            index = self.current_sprite
            del snapshot["sprites"][index]
            del snapshot["stack_mask"][index]
            self.current_sprite = min(index, len(snapshot["sprites"]) - 1)
            self.rebuild_sprite_list(
                source="frame", mask=snapshot["stack_mask"]
            )
            self.refresh_views()
            return
        if len(self.sprites) <= 1:
            messagebox.showinfo("Remove Sprite", "At least one sprite is required.")
            return
        if not messagebox.askyesno(
            "Remove Sprite",
            f"Remove '{self._sprite_display_name(self.current_sprite)}'?",
        ):
            return
        self._remove_slot_at_index(self.current_sprite)
        source, mask = self._sprite_list_source()
        self.rebuild_sprite_list(source=source, mask=mask)
        self.refresh_views()

    def _remove_slot_at_index(self, index: int):
        if index < 0 or index >= len(self.sprites):
            return
        del self.sprites[index]
        if self.current_sprite >= len(self.sprites):
            self.current_sprite = max(0, len(self.sprites) - 1)

    def _swap_sprite_slot_pair(self, sprites, mask, first, second):
        sprites[first], sprites[second] = sprites[second], sprites[first]
        if mask is not None:
            mask[first], mask[second] = mask[second], mask[first]

    def move_sprite(self, direction: int):
        if self.anim_preview_running:
            return
        index = self.current_sprite
        new_index = index + direction
        if new_index < 0 or new_index >= self._active_sprite_count():
            return
        if self.anim_edit_mode and self._frame_edit_snapshot is not None:
            snapshot = self._frame_edit_snapshot
            self._swap_sprite_slot_pair(
                snapshot["sprites"], snapshot["stack_mask"], index, new_index
            )
            self.current_sprite = new_index
            self.rebuild_sprite_list(
                source="frame", mask=snapshot["stack_mask"]
            )
        else:
            self._swap_sprite_slot_pair(self.sprites, None, index, new_index)
            if index < len(self.stack_vars) and new_index < len(self.stack_vars):
                first_checked = self.stack_vars[index].get()
                second_checked = self.stack_vars[new_index].get()
                self.stack_vars[index].set(second_checked)
                self.stack_vars[new_index].set(first_checked)
            self.current_sprite = new_index
            source, mask = self._sprite_list_source()
            self.rebuild_sprite_list(source=source, mask=mask)
        self.refresh_views()

    def _current_animation_has_frames(self):
        anim = self._current_animation()
        return anim is not None and bool(anim.get("frames"))

    def _apply_anim_frame_for_preview(self, index: int):
        frame = self.animations[self.current_animation]["frames"][index]
        self._anim_preview_index = index
        if hasattr(self, "canvas"):
            size = self.sprite_size_mode
            ps = self.zoom
            self.canvas.delete("all")
            self.canvas.config(width=size * ps, height=size * ps)
            self._render_composite(
                self.canvas,
                frame["sprites"],
                frame["stack_enabled"],
                frame["stack_mask"],
                self.current_sprite,
                pixel_size=ps,
                draw_off_pixels=False,
                transparent_color="#aaaaaa",
                outline=CANVAS_GRID_OUTLINE,
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
        self._update_edit_mode_indicator()

    def _set_preview_ui_state(self, enabled: bool):
        state = tk.NORMAL if enabled else tk.DISABLED
        for widget_name in (
            "anim_play_btn",
            "anim_combo",
            "anim_frame_list",
        ):
            if hasattr(self, widget_name):
                try:
                    getattr(self, widget_name).config(state=state)
                except tk.TclError:
                    pass
        self._set_sprite_slots_enabled(enabled)
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

    def _capture_sprites_for_frame(self, sprites, stack_enabled, stack_mask):
        captured = []
        if stack_enabled:
            for index, sprite in enumerate(sprites):
                if index < len(stack_mask) and stack_mask[index]:
                    captured.append(deep_copy_sprite(sprite))
        elif self.current_sprite < len(sprites):
            captured.append(deep_copy_sprite(sprites[self.current_sprite]))
        return captured

    def _capture_current_state_as_frame(self, duration=4):
        if self.anim_edit_mode and self._frame_edit_snapshot is not None:
            stack_enabled = self._frame_edit_snapshot["stack_enabled"]
            stack_mask = self._frame_edit_snapshot["stack_mask"][:]
            sprites = self._frame_edit_snapshot["sprites"]
        else:
            stack_enabled = self.stack_enabled.get()
            stack_mask = self._capture_stack_mask()
            sprites = self.sprites
        captured_sprites = self._capture_sprites_for_frame(
            sprites, stack_enabled, stack_mask
        )
        if not captured_sprites:
            captured_sprites = [
                create_empty_sprite_dict(
                    self.sprite_size_mode, self.current_color
                )
            ]
        return {
            "duration": duration,
            "stack_enabled": stack_enabled,
            "stack_mask": [True] * len(captured_sprites),
            "sprites": captured_sprites,
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
        if self.anim_edit_mode and not self._try_leave_current_frame_edit("moving this frame"):
            return
        frames[index], frames[new_index] = frames[new_index], frames[index]
        self.current_anim_frame = new_index
        if self.anim_edit_mode:
            self.select_anim_frame(new_index)
        else:
            self._refresh_animation_ui()

    def _committed_anim_frame(self):
        if self.current_animation is None:
            return None
        anim = self._current_animation()
        frames = anim.get("frames", [])
        if not frames or self.current_anim_frame >= len(frames):
            return None
        return frames[self.current_anim_frame]

    def _frame_edit_is_dirty(self):
        if not self.anim_edit_mode or self._frame_edit_snapshot is None:
            return False
        committed = self._committed_anim_frame()
        if committed is None:
            return False
        return not frames_equal(self._frame_edit_snapshot, committed)

    def _try_leave_current_frame_edit(self, action: str) -> bool:
        if not self._frame_edit_is_dirty():
            return True
        result = messagebox.askyesnocancel(
            "Unsaved Frame Changes",
            f"Save changes to frame {self.current_anim_frame} before {action}?",
        )
        if result is None:
            return False
        if result:
            return self.commit_anim_frame()
        return True

    def commit_anim_frame(self):
        if not self.anim_edit_mode or self._frame_edit_snapshot is None:
            return True
        if self.current_animation is None:
            return True
        duration = self._frame_edit_snapshot.get("duration", 4)
        if not (1 <= duration <= 255):
            messagebox.showerror("Invalid Duration", "Duration must be 1–255 screen frames.")
            return False
        self.animations[self.current_animation]["frames"][self.current_anim_frame] = (
            deep_copy_frame(self._frame_edit_snapshot)
        )
        self._update_frame_edit_controls()
        return True

    def commit_anim_frame_edits(self):
        if self.commit_anim_frame():
            self.refresh_views()

    def discard_anim_frame_edits(self):
        if not self.anim_edit_mode or not self._frame_edit_is_dirty():
            return
        if self.current_animation is None:
            return
        committed = self._committed_anim_frame()
        if committed is None:
            return
        self._frame_edit_snapshot = compact_frame_slots(
            deep_copy_frame(committed),
            self.sprite_size_mode,
            self.current_color,
        )
        self.stack_enabled.set(self._frame_edit_snapshot["stack_enabled"])
        self.rebuild_sprite_list(
            source="frame", mask=self._frame_edit_snapshot["stack_mask"]
        )
        self._sync_animation_panel_from_snapshot()
        self.refresh_views()

    def _update_frame_edit_controls(self):
        if not hasattr(self, "anim_commit_btn"):
            return
        dirty = self._frame_edit_is_dirty()
        in_edit = self.anim_edit_mode
        state = tk.NORMAL if in_edit and dirty else tk.DISABLED
        self.anim_commit_btn.config(state=state)
        self.anim_discard_btn.config(state=state)
        if not in_edit:
            self.anim_frame_dirty_label.config(text="")
        elif dirty:
            self.anim_frame_dirty_label.config(text="Unsaved changes")
        else:
            self.anim_frame_dirty_label.config(text="All changes saved")

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
        if (
            self.anim_edit_mode
            and self._frame_edit_snapshot is not None
            and index != self.current_anim_frame
            and not self._try_leave_current_frame_edit("switching frames")
        ):
            return
        if self._static_stack_mask is None:
            self._static_stack_mask = [v.get() for v in self.stack_vars]
            self._static_stack_enabled = self.stack_enabled.get()
        frame = anim["frames"][index]
        self._frame_edit_snapshot = compact_frame_slots(
            deep_copy_frame(frame),
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
        self._refresh_animation_ui(select_frame=False)
        self._clear_anim_frame_list_selection()
        self.refresh_views()

    def exit_animation_mode(self, commit=True):
        if self.anim_edit_mode and self._frame_edit_is_dirty():
            if not self._try_leave_current_frame_edit("exiting frame edit"):
                return
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

    def _clear_anim_frame_list_selection(self):
        if not hasattr(self, "anim_frame_list"):
            return
        self._suppress_anim_ui_events = True
        try:
            self.anim_frame_list.selection_clear(0, tk.END)
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

    def _on_duration_var_changed(self, *_args):
        if self._suppress_anim_ui_events:
            return
        self._apply_duration_from_spinbox()

    def _on_duration_changed(self):
        self._apply_duration_from_spinbox()

    def _apply_duration_from_spinbox(self):
        if not self.anim_edit_mode or self._frame_edit_snapshot is None:
            return
        try:
            duration = int(self.anim_duration_var.get())
        except (tk.TclError, ValueError):
            return
        if 1 <= duration <= 255:
            self._frame_edit_snapshot["duration"] = duration
            self._refresh_animation_ui(select_frame=False)
            self._update_frame_edit_controls()
            self._update_edit_mode_indicator()

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
            anim = self.animations[self.current_animation]
            for index, frame in enumerate(anim["frames"]):
                duration = frame["duration"]
                if (
                    self.anim_edit_mode
                    and self._frame_edit_snapshot is not None
                    and index == self.current_anim_frame
                ):
                    duration = self._frame_edit_snapshot.get("duration", duration)
                label = f"Frame {index} ({duration} sf)"
                self.anim_frame_list.insert(tk.END, label)
            if self.anim_edit_mode and anim["frames"]:
                self._set_anim_frame_list_selection(self.current_anim_frame)
                if select_frame and self._frame_edit_snapshot is not None:
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
        return [i for i, enabled in enumerate(stack_mask) if enabled]

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

    def _draw_sprite_grid(self, target_canvas, size, pixel_size, fill, outline):
        for y in range(size):
            for x in range(size):
                px, py = x * pixel_size, y * pixel_size
                target_canvas.create_rectangle(
                    px,
                    py,
                    px + pixel_size,
                    py + pixel_size,
                    fill=fill,
                    outline=outline,
                )

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
        outline=CANVAS_GRID_OUTLINE,
        grid_empty_fill=CANVAS_BG,
    ):
        size = self.sprite_size_mode
        ps = pixel_size or (160 // size)
        indices = self._resolve_stack_indices(
            stack_mask, stack_enabled, current_sprite
        )

        self._draw_sprite_grid(target_canvas, size, ps, grid_empty_fill, outline)

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
                    if not is_on and not draw_off_pixels:
                        continue
                    fill = fg_hex if is_on else CANVAS_OFF_PIXEL
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
        self.canvas.config(width=size * pixel_size, height=size * pixel_size)
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
            outline=CANVAS_GRID_OUTLINE,
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
    
    def _highlight_sprite_slot(self, index):
        if not hasattr(self, "_sprite_slot_rows"):
            return
        normal_bg, selected_bg = self._sprite_slot_colors()
        for row_index, row in enumerate(self._sprite_slot_rows):
            bg = selected_bg if row_index == index else normal_bg
            self._apply_sprite_slot_row_bg(row, bg)

    def _set_sprite_slots_enabled(self, enabled):
        state = tk.NORMAL if enabled else tk.DISABLED
        for row in getattr(self, "_sprite_slot_rows", []):
            for child in row.winfo_children():
                try:
                    child.configure(state=state)
                except tk.TclError:
                    pass
        if not enabled:
            if hasattr(self, "_sprite_move_up_btn"):
                self._sprite_move_up_btn.config(state=tk.DISABLED)
                self._sprite_move_down_btn.config(state=tk.DISABLED)
        else:
            self._update_sprite_order_buttons()

    def select_sprite_index(self, index):
        if self.anim_preview_running:
            return
        if index < 0 or index >= self._active_sprite_count():
            return
        self.current_sprite = index
        self.current_color = self._active_sprites()[self.current_sprite]["color"]
        self._highlight_sprite_slot(index)
        self._update_sprite_order_buttons()
        self.refresh_views()

    def rename_sprite(self, index, name):
        name = name.strip()
        if not name:
            raise ValueError("Sprite name cannot be empty.")
        if self.anim_edit_mode and self._frame_edit_snapshot is not None:
            sprites = self._frame_edit_snapshot["sprites"]
            if index < 0 or index >= len(sprites):
                raise ValueError("Invalid sprite index.")
            sprites[index]["name"] = name
            return
        if index < 0 or index >= len(self.sprites):
            raise ValueError("Invalid sprite index.")
        self.sprites[index]["name"] = name

    def rename_sprite_dialog(self, index=None):
        if self.anim_preview_running:
            return
        if index is None:
            index = self.current_sprite
        if index < 0 or index >= self._active_sprite_count():
            return
        source, _mask = self._sprite_list_source()
        current_name = self._sprite_display_name_at(index, source)
        name = simpledialog.askstring(
            "Rename Sprite", "Sprite name:", initialvalue=current_name
        )
        if not name:
            return
        try:
            self.rename_sprite(index, name)
        except ValueError as exc:
            messagebox.showerror("Rename Sprite", str(exc))
            return
        source, mask = self._sprite_list_source()
        self.rebuild_sprite_list(source=source, mask=mask)
        self.update_status()

    def select_sprite(self, event=None):
        self.select_sprite_index(self.current_sprite)
    
    def _update_edit_mode_indicator(self):
        if not hasattr(self, "mode_indicator"):
            return

        if self.anim_preview_running and self.current_animation is not None:
            anim = self.animations[self.current_animation]
            frames = anim["frames"]
            text = (
                f"  PREVIEW — '{anim['name']}' "
                f"frame {self._anim_preview_index + 1}/{len(frames)}"
            )
            bg, fg = "#1d4ed8", "#ffffff"
            canvas_title = "Drawing Canvas — animation preview"
        elif self.anim_edit_mode:
            anim_name = "?"
            if self.current_animation is not None:
                anim_name = self.animations[self.current_animation]["name"]
            duration = 4
            if self._frame_edit_snapshot is not None:
                duration = self._frame_edit_snapshot.get("duration", 4)
            dirty_suffix = " — unsaved changes" if self._frame_edit_is_dirty() else ""
            text = (
                f"  FRAME EDIT — '{anim_name}' frame {self.current_anim_frame} "
                f"({duration} screen frames){dirty_suffix}"
            )
            bg, fg = "#b45309", "#ffffff"
            canvas_title = "Drawing Canvas — editing animation frame"
        else:
            text = "  STATIC EDIT — editing project sprite slots"
            if self.current_animation is not None:
                anim = self.animations[self.current_animation]
                text += f" — animation '{anim['name']}' selected"
            bg, fg = "#e5e7eb", "#1f2937"
            canvas_title = (
                "Drawing Canvas - Stacked View (LMB=draw on current, RMB=erase on current)"
            )

        self.mode_indicator.config(text=text, bg=bg, fg=fg)
        self.canvas_frame.config(text=canvas_title)
        if hasattr(self, "sprites_panel"):
            if self.anim_edit_mode or self.anim_preview_running:
                self.sprites_panel.config(text="Frame Sprites")
            else:
                self.sprites_panel.config(text="Project Sprites")

    def update_status(self):
        sprites = self._active_sprites()
        sprite_data = sprites[self.current_sprite]
        col = sprite_data["color"]
        txt = (
            f"{self._current_sprite_display_name()} | "
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
        self._update_color_indicator()
        self._update_frame_edit_controls()
        self._update_edit_mode_indicator()
    
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
            sprites[nxt] = deep_copy_sprite(src)
            source, _mask = self._sprite_list_source()
            target_name = self._sprite_display_name_at(nxt, source)
            messagebox.showinfo("Duplicate Sprite", f"Duplicated to {target_name}")
        else:
            messagebox.showinfo(
                "Duplicate Sprite", "No next sprite. Use Add first."
            )
    
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

    def _flush_pending_edits_for_save(self):
        if self.anim_preview_running:
            self.stop_anim_preview()
        if self.anim_edit_mode:
            self.commit_anim_frame()
        if self.current_animation is not None and hasattr(self, "anim_loop_var"):
            self.animations[self.current_animation]["loop"] = self.anim_loop_var.get()

    def _build_project_data(self) -> dict:
        self._flush_pending_edits_for_save()
        data = {
            "version": 2,
            "mode": self.sprite_size_mode,
            "sprites": self.sprites,
            "animations": self.animations,
        }
        if self.current_animation is not None:
            data["current_animation"] = self.current_animation
        return data

    def save_project(self):
        fn = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("JSON", "*.json")]
        )
        if fn:
            with open(fn, "w", encoding="utf-8") as f:
                json.dump(self._build_project_data(), f, indent=2)
            messagebox.showinfo("Saved", "Project saved.")

    def load_project_data(self, data: dict) -> list[str]:
        """Load project dict into editor state. Returns validation warnings."""
        self.sprite_size_mode = data["mode"]
        self.sprites = data["sprites"]
        if not self.sprites:
            self.init_sprites(1)
        else:
            ensure_sprite_names(self.sprites)
        version = data.get("version", 1)
        anims = data.get("animations", []) if version >= 2 else []
        self.animations, warnings = validate_and_sanitize_animations(
            anims,
            self.sprite_size_mode,
            default_color=self.current_color,
        )
        self._reset_animation_state()
        if self.animations:
            saved_index = data.get("current_animation", 0)
            if isinstance(saved_index, int) and 0 <= saved_index < len(self.animations):
                self.current_animation = saved_index
            else:
                self.current_animation = 0
            self.current_anim_frame = 0
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
        asm = f"; TMS9918 Sprite {slot_index:02d} {size}x{size} Color {col}\n"
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

    def build_frame_asm(self, sprites, stack_enabled, stack_mask, header=""):
        indices = self._resolve_stack_indices(
            stack_mask, stack_enabled, self.current_sprite
        )
        parts = []
        if header:
            parts.append(header.rstrip("\n"))
        for slot_idx in indices:
            parts.append(self._build_asm_for_sprite_data(sprites[slot_idx], slot_idx))
        return "\n".join(parts)

    def build_animation_asm(self, anim_index):
        anim = self.animations[anim_index]
        frames = anim.get("frames", [])
        lines = [f"; Animation '{anim['name']}' — {len(frames)} frames"]
        durations = []
        for index, frame in enumerate(frames):
            durations.append(frame["duration"])
            lines.append(f"; Frame {index}: duration={frame['duration']} screen frames")
            frame_asm = self.build_frame_asm(
                frame["sprites"], frame["stack_enabled"], frame["stack_mask"]
            )
            if frame_asm:
                lines.append(frame_asm)
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
            frame = frames[self._anim_preview_index]
            header = f"; Preview frame {self._anim_preview_index + 1}/{len(frames)}\n"
            return self.build_frame_asm(
                frame["sprites"],
                frame["stack_enabled"],
                frame["stack_mask"],
                header=header,
            )

        if self.anim_edit_mode and self._frame_edit_snapshot is not None:
            snapshot = self._frame_edit_snapshot
            anim_name = ""
            if self.current_animation is not None:
                anim_name = self.animations[self.current_animation]["name"]
            header = (
                f"; Animation '{anim_name}' / Frame {self.current_anim_frame} "
                f"(duration={snapshot['duration']} sf)\n"
            )
            return self.build_frame_asm(
                snapshot["sprites"],
                snapshot["stack_enabled"],
                snapshot["stack_mask"],
                header=header,
            )

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