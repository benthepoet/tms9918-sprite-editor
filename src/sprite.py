import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json

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

class SpriteEditor:
    def __init__(self, root):
        self.root = root
        self.root.title("TI-99/4A Sprite Editor - Stacked Editing")
        self.root.geometry("1300x750")
        
        self.sprite_size_mode = 16
        self.num_sprites = 16
        self.current_sprite = 0
        self.current_color = 2
        
        self.sprites = []
        self.init_sprites()
        
        self.zoom = 20
        self.stack_enabled = tk.BooleanVar(value=True)
        self.stack_vars = []
        
        self.create_ui()
    
    def init_sprites(self):
        self.sprites = []
        for _ in range(self.num_sprites):
            size = self.sprite_size_mode
            pattern = [[0 for _ in range(size)] for _ in range(size)]
            self.sprites.append({"pattern": pattern, "color": self.current_color})
    
    def create_ui(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="New", command=self.new_project)
        file_menu.add_command(label="Load Project", command=self.load_project)
        file_menu.add_command(label="Save Project", command=self.save_project)
        file_menu.add_separator()
        file_menu.add_command(label="Export CALL CHAR (BASIC)", command=self.export_basic)
        file_menu.add_command(label="Export Assembly DATA", command=self.export_asm)
        
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
        
        # Right Panel
        right_frame = ttk.Frame(main_frame)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y)
        
        ttk.Label(right_frame, text="Sprite Slots (check to stack)").pack(anchor="w")
        
        list_frame = ttk.Frame(right_frame)
        list_frame.pack(pady=5, fill="x")
        
        self.sprite_list = tk.Listbox(list_frame, height=12, width=18)
        self.sprite_list.pack(side=tk.LEFT)
        self.sprite_list.bind("<<ListboxSelect>>", self.select_sprite)
        
        check_frame = ttk.Frame(list_frame)
        check_frame.pack(side=tk.RIGHT, fill="y")
        
        self.stack_vars = []
        for i in range(self.num_sprites):
            var = tk.BooleanVar(value=(i <= 1))  # default first two on
            cb = ttk.Checkbutton(check_frame, variable=var, command=self.refresh_views)
            cb.pack(anchor="w")
            self.stack_vars.append(var)
            self.sprite_list.insert(tk.END, f"Sprite {i:02d}")
        
        ttk.Checkbutton(right_frame, text="Enable Stacking (Canvas + Preview)", variable=self.stack_enabled, command=self.refresh_views).pack(anchor="w", pady=5)
        
        ttk.Label(right_frame, text="Stacked Preview").pack(anchor="w")
        self.preview_canvas = tk.Canvas(right_frame, bg="#777777", width=160, height=160)
        self.preview_canvas.pack(pady=5)
        
        ttk.Button(right_frame, text="Clear Sprite", command=self.clear_current).pack(pady=5, fill="x")
        ttk.Button(right_frame, text="Fill Sprite", command=self.fill_sprite).pack(pady=5, fill="x")
        ttk.Button(right_frame, text="Copy to Next", command=self.copy_to_next).pack(pady=5, fill="x")
        
        self.status = ttk.Label(self.root, text="", relief=tk.SUNKEN, anchor=tk.W)
        self.status.pack(side=tk.BOTTOM, fill=tk.X)
        
        self.update_canvas()
        self.update_status()
        self.update_preview()
    
    def rgb_to_hex(self, rgb):
        return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
    
    def set_color(self, color):
        self.current_color = color
        if color != 0:
            self.sprites[self.current_sprite]["color"] = color
        self.refresh_views()
    
    def refresh_views(self):
        self.update_canvas()
        self.update_preview()
        self.update_status()
    
    def set_mode(self, mode):
        if self.sprite_size_mode == mode: return
        if messagebox.askyesno("Change Mode", "This will clear all sprites. Continue?"):
            self.sprite_size_mode = mode
            self.init_sprites()
            self.current_sprite = 0
            self.current_color = 2
            self.update_sprite_list()
            self.refresh_views()
    
    def update_sprite_list(self):
        self.sprite_list.delete(0, tk.END)
        self.stack_vars = []
        for i in range(self.num_sprites):
            var = tk.BooleanVar(value=(i <= 1))
            self.stack_vars.append(var)
            self.sprite_list.insert(tk.END, f"Sprite {i:02d}")
    
    def get_stacked_sprites(self):
        stacked = [i for i, var in enumerate(self.stack_vars) if var.get()]
        if self.current_sprite not in stacked:
            stacked.append(self.current_sprite)
        return sorted(stacked)
    
    def update_canvas(self):
        self.canvas.delete("all")
        size = self.sprite_size_mode
        pixel_size = self.zoom
        canvas_size = size * pixel_size
        self.canvas.config(width=canvas_size + 4, height=canvas_size + 4)
        
        if not self.stack_enabled.get():
            # Single sprite mode
            sprite_data = self.sprites[self.current_sprite]
            pattern = sprite_data["pattern"]
            color = sprite_data["color"]
            fg_hex = self.rgb_to_hex(TI_COLORS[color]) if color != 0 else "#aaaaaa"
            for y in range(size):
                for x in range(size):
                    is_on = pattern[y][x] == 1
                    fill = fg_hex if is_on else "#555555"
                    px = x * pixel_size
                    py = y * pixel_size
                    self.canvas.create_rectangle(px, py, px + pixel_size, py + pixel_size,
                                               fill=fill, outline="#666666")
            return
        
        # Stacked view (bottom to top)
        for idx in self.get_stacked_sprites():
            sprite_data = self.sprites[idx]
            pattern = sprite_data["pattern"]
            color = sprite_data["color"]
            fg_hex = self.rgb_to_hex(TI_COLORS[color]) if color != 0 else "#aaaaaa"
            for y in range(size):
                for x in range(size):
                    if pattern[y][x] == 1:
                        px = x * pixel_size
                        py = y * pixel_size
                        self.canvas.create_rectangle(px, py, px + pixel_size, py + pixel_size,
                                                   fill=fg_hex, outline="#666666")
    
    def draw_pixel(self, event):
        size = self.sprite_size_mode
        ps = self.zoom
        x = event.x // ps
        y = event.y // ps
        if 0 <= x < size and 0 <= y < size:
            sprite_data = self.sprites[self.current_sprite]
            if self.current_color == 0:
                sprite_data["pattern"][y][x] = 0
            else:
                sprite_data["pattern"][y][x] = 1
                sprite_data["color"] = self.current_color
            self.refresh_views()
    
    def erase_pixel(self, event):
        size = self.sprite_size_mode
        ps = self.zoom
        x = event.x // ps
        y = event.y // ps
        if 0 <= x < size and 0 <= y < size:
            self.sprites[self.current_sprite]["pattern"][y][x] = 0
            self.refresh_views()
    
    def select_sprite(self, event=None):
        sel = self.sprite_list.curselection()
        if sel:
            self.current_sprite = sel[0]
            self.current_color = self.sprites[self.current_sprite]["color"]
            self.refresh_views()
    
    def update_status(self):
        sprite_data = self.sprites[self.current_sprite]
        col = sprite_data['color']
        txt = f"Sprite {self.current_sprite:02d} | {self.sprite_size_mode}×{self.sprite_size_mode} | Color: {col} {COLOR_NAMES[col]} | Stacking: {'ON' if self.stack_enabled.get() else 'OFF'}"
        self.status.config(text=txt)
    
    def update_preview(self):
        self.preview_canvas.delete("all")
        size = self.sprite_size_mode
        scale = 160 // size
        
        if not self.stack_enabled.get():
            sprite_data = self.sprites[self.current_sprite]
            pattern = sprite_data["pattern"]
            color = sprite_data["color"]
            fg = self.rgb_to_hex(TI_COLORS[color]) if color != 0 else "#000000"
            for y in range(size):
                for x in range(size):
                    if pattern[y][x] == 1:
                        self.preview_canvas.create_rectangle(x*scale, y*scale, (x+1)*scale, (y+1)*scale, fill=fg, outline="")
            return
        
        for idx in self.get_stacked_sprites():
            sprite_data = self.sprites[idx]
            pattern = sprite_data["pattern"]
            color = sprite_data["color"]
            fg = self.rgb_to_hex(TI_COLORS[color]) if color != 0 else "#000000"
            for y in range(size):
                for x in range(size):
                    if pattern[y][x] == 1:
                        self.preview_canvas.create_rectangle(x*scale, y*scale, (x+1)*scale, (y+1)*scale, fill=fg, outline="")
    
    def clear_current(self):
        sprite_data = self.sprites[self.current_sprite]
        size = self.sprite_size_mode
        sprite_data["pattern"] = [[0] * size for _ in range(size)]
        self.refresh_views()
    
    def fill_sprite(self):
        if messagebox.askyesno("Fill", "Fill sprite with current color?"):
            sprite_data = self.sprites[self.current_sprite]
            size = self.sprite_size_mode
            sprite_data["pattern"] = [[1] * size for _ in range(size)]
            if self.current_color != 0:
                sprite_data["color"] = self.current_color
            self.refresh_views()
    
    def copy_to_next(self):
        if self.current_sprite < self.num_sprites - 1:
            nxt = self.current_sprite + 1
            src = self.sprites[self.current_sprite]
            self.sprites[nxt] = {"pattern": [row[:] for row in src["pattern"]], "color": src["color"]}
            messagebox.showinfo("Copy", f"Copied to Sprite {nxt:02d}")
    
    def new_project(self):
        if messagebox.askyesno("New Project", "Clear everything?"):
            self.init_sprites()
            self.current_sprite = 0
            self.current_color = 2
            self.update_sprite_list()
            self.refresh_views()
    
    def save_project(self):
        fn = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if fn:
            data = {"mode": self.sprite_size_mode, "sprites": self.sprites}
            with open(fn, "w") as f:
                json.dump(data, f, indent=2)
            messagebox.showinfo("Saved", "Project saved.")
    
    def load_project(self):
        fn = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if fn:
            with open(fn) as f:
                data = json.load(f)
            self.sprite_size_mode = data["mode"]
            self.sprites = data["sprites"]
            self.current_sprite = 0
            self.current_color = self.sprites[0]["color"] if self.sprites else 2
            self.update_sprite_list()
            self.refresh_views()
            messagebox.showinfo("Loaded", "Project loaded.")
    
    def export_basic(self):
        sprite_data = self.sprites[self.current_sprite]
        pattern = sprite_data["pattern"]
        size = self.sprite_size_mode
        col = sprite_data["color"]
        if size == 8:
            hex_str = ""
            for y in range(8):
                b = 0
                for x in range(8):
                    if pattern[y][x]:
                        b |= (1 << (7 - x))
                hex_str += f"{b:02X}"
            txt = f'CALL CHAR(96,"{hex_str}")  # Sprite {self.current_sprite} Color {col}'
        else:
            txt = f"16x16 Sprite {self.current_sprite} (Color {col}):\n"
            for y in range(16):
                b1 = b2 = 0
                for x in range(8):
                    if pattern[y][x]: b1 |= (1 << (7-x))
                    if pattern[y][x+8]: b2 |= (1 << (7-x))
                txt += f"  {b1:02X}{b2:02X}\n"
        messagebox.showinfo("BASIC Export", txt)
        self.root.clipboard_clear()
        self.root.clipboard_append(txt)
    
    def export_asm(self):
        sprite_data = self.sprites[self.current_sprite]
        pattern = sprite_data["pattern"]
        size = self.sprite_size_mode
        col = sprite_data["color"]
        asm = f"; TI-99 Sprite {self.current_sprite} {size}x{size} Color {col}\n"
        if size == 8:
            asm += f"SP{self.current_sprite:02d} DATA "
            for y in range(8):
                b = 0
                for x in range(8):
                    if pattern[y][x]:
                        b |= (1 << (7 - x))
                asm += f">{b:02X}"
                if y < 7: asm += ","
            asm += "\n"
        else:
            asm += "; 16x16 pattern (32 bytes)\n"
            for y in range(16):
                b1 = b2 = 0
                for x in range(8):
                    if pattern[y][x]: b1 |= (1 << (7-x))
                    if pattern[y][x+8]: b2 |= (1 << (7-x))
                asm += f"    DATA >{b1:02X},>{b2:02X}\n"
        messagebox.showinfo("Assembly Export", asm)
        self.root.clipboard_clear()
        self.root.clipboard_append(asm)

if __name__ == "__main__":
    root = tk.Tk()
    app = SpriteEditor(root)
    root.mainloop()