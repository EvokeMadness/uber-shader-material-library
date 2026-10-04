import json
import os
import queue
import shutil
import subprocess
import threading
from tkinter import *
from tkinter import ttk
from tkinter import filedialog

base_dir = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
category_cache = {}
current_target_dir = base_dir

def get_image_height():
    try:
        return int(root.getvar("image_height"))
    except Exception:
        return 384

def get_canvas_width():
    return 2 * get_image_height()

def get_scroll_step():
    try:
        return int(root.getvar("scroll_step"))
    except Exception:
        return 2

def get_manifests_dir(target_dir=None):
    d = target_dir or current_target_dir
    rel = "manifests"
    try:
        rel = root.getvar("manifests_path")
    except Exception:
        pass
    return os.path.join(d, rel)

def get_category_data(target_dir=None, cat_name=None):
    if not cat_name:
        return {}
    d = get_manifests_dir(target_dir)
    key = (d, cat_name)
    if key in category_cache:
        return category_cache[key]
    path = os.path.join(d, f"{cat_name}.json")
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                category_cache[key] = data
                return data
        except Exception:
            pass
    return {}

def load_tcl_config(app_root, base_dir):
    if app_root is None or not isinstance(base_dir, str):
        return
    cfg = os.path.join(base_dir, "config.tcl")
    if os.path.isfile(cfg):
        app_root.tk.call("source", cfg)

def load_style_config(app_root, base_dir):
    if app_root is None or not isinstance(base_dir, str):
        return
    style_file = os.path.join(base_dir, "style.tcl")
    if os.path.isfile(style_file):
        app_root.tk.call("source", style_file)

def load_debug_config(app_root, base_dir):
    if app_root is None or not isinstance(base_dir, str):
        return
    try:
        is_debug = str(app_root.getvar("debug")) == "1"
    except Exception:
        is_debug = False

    if is_debug:
        if not log.grid_info():
            log.grid()
        info_text.set("Debug")
        info.configure(style="Debug.TLabel")

    dbg = os.path.join(base_dir, "debug.tcl")
    if is_debug and os.path.isfile(dbg):
        app_root.tk.call("source", dbg)

def populate_materials(target_dir=None, selected_cat=None):
    d = get_manifests_dir(target_dir)
    if not os.path.isdir(d):
        return

    cat = selected_cat or category_var.get()
    data = get_category_data(target_dir, cat)
    mats = list(data.get("materials", {}).keys())

    material_list.delete(0, END)
    if mats:
        sorted_mats = sorted(mats)
        material_list.insert(END, *sorted_mats)
        material_list.selection_set(0)
        material_list.activate(0)
    materials_in_cat_var.set(f"Materials in category: {len(mats)}")
    on_material_select()

def populate_categories(target_dir=None):
    global current_target_dir
    current_target_dir = target_dir or base_dir
    d = get_manifests_dir(current_target_dir)
    if not os.path.isdir(d):
        return

    path = os.path.join(d, "index.json")
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                cats = sorted(json.load(f).get("categories", {}).keys())
        except Exception:
            cats = []
    else:
        cats = sorted([
            os.path.splitext(f)[0]
            for f in os.listdir(d)
            if f.endswith(".json")
        ])

    if cats:
        category["values"] = cats
        category.current(0)
        populate_materials(current_target_dir, cats[0])

def open_library(title="Open Directory"):
    if not isinstance(title, str):
        title = "Open Directory"
    if shutil.which("zenity"):
        proc = subprocess.run(
            ["zenity", "--file-selection", "--directory", f"--title={title}"],
            capture_output=True,
            text=True
        )
        d = proc.stdout.strip() if proc.returncode == 0 else ""
    else:
        d = filedialog.askdirectory(title=title)

    if not d or not os.path.isfile(os.path.join(d, "radeon-prorender-material-library.blend")):
        return

    script = os.path.join(base_dir, "generate_manifest.py")
    if not os.path.isfile(script):
        return

    blend_files = [
        f for f in os.listdir(d)
        if f.endswith(".blend") and f != "radeon-prorender-material-library.blend"
    ]
    total_categories = len(blend_files)

    progress["maximum"] = max(1, total_categories)
    progress["value"] = 0
    progress.grid()
    operation_text.set(f"Generating manifests (0/{total_categories})...")

    q = queue.Queue()

    def process_queue():
        try:
            while True:
                msg = q.get_nowait()
                if msg is None:
                    progress["value"] = progress["maximum"]
                    progress.grid_remove()
                    operation_text.set("")
                    category_cache.clear()
                    populate_categories(d)
                    return
                action, payload = msg
                if action == "log":
                    append_log(payload)
                elif action == "step":
                    val, name = payload
                    progress["value"] = val
                    operation_text.set(f"Generating manifests ({val}/{total_categories}): {name}")
        except queue.Empty:
            pass
        root.after(50, process_queue)

    root.after(50, process_queue)

    def run_worker():
        try:
            env = dict(os.environ, PYTHONUNBUFFERED="1")
            proc = subprocess.Popen(
                ["blender", "--factory-startup", "-b", "--python", script, "--", d],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env
            )
            completed = 0
            for line in iter(proc.stdout.readline, ""):
                if line.startswith("Blender "):
                    continue
                q.put(("log", line))
                stripped = line.strip()
                if ": " in stripped and (stripped.endswith("materials") or stripped.endswith("material")):
                    completed += 1
                    cat_name = stripped.split(":", 1)[0].strip()
                    q.put(("step", (completed, cat_name)))
            proc.stdout.close()
            proc.wait()
        except Exception as e:
            q.put(("log", f"Error: {e}\n"))
        finally:
            q.put(None)

    threading.Thread(target=run_worker, daemon=True).start()

def filename_strip(parent, text="Name:"):
    if parent is None:
        return
    banner = ttk.Frame(parent, height=25, style="Strip.TFrame")
    banner.grid(column=0, row=0, sticky=(N, W, E))
    banner.columnconfigure(0, weight=1)

    lbl = ttk.Label(banner, text=text, anchor="center", style="Strip.TLabel")
    lbl.grid(column=0, row=0, sticky=(W, E))

def photo_slot(parent):
    if parent is None:
        return
    slot = Label(parent, bg="black")
    slot.grid(column=0, row=1, sticky=(N, S, E, W))

def resolution_strip(parent, text="Resolution"):
    if parent is None:
        return
    parent.grid_propagate(False)
    parent.rowconfigure(1, weight=1)
    parent.columnconfigure(0, weight=1)

    banner = ttk.Frame(parent, height=25, style="Strip.TFrame")
    banner.grid(column=0, row=2, sticky=(S, W, E))
    banner.columnconfigure(0, weight=1)

    lbl = ttk.Label(banner, text=text, anchor="w", style="Strip.TLabel")
    lbl.grid(column=0, row=0, sticky=(W, E))

def append_log(text):
    log_output.configure(state="normal")
    log_output.insert(END, text)
    log_output.see(END)
    log_output.configure(state="disabled")

def write_to_log(msg):
    log_output.configure(state="normal")
    if log_output.index("end-1c") != "1.0":
        log_output.insert(END, "\n")
    log_output.insert(END, str(msg))
    log_output.see(END)
    log_output.configure(state="disabled")

def add_pair(parent, pair_index, img_h=None):
    if parent is None or not isinstance(pair_index, int):
        return
    if img_h is None:
        img_h = get_image_height()
    src = ttk.Labelframe(parent, text="Source", width=img_h, height=img_h)
    src.grid(column=0, row=pair_index)
    rep = ttk.Labelframe(parent, text="Replace with", width=img_h, height=img_h)
    rep.grid(column=1, row=pair_index)

    filename_strip(src)
    photo_slot(src)
    resolution_strip(src)

    filename_strip(rep)
    photo_slot(rep)
    resolution_strip(rep)

def _build_canvas_section(canvas, title, count, start_y):
    img_h = get_image_height()
    canvas_w = get_canvas_width()
    if count == 0:
        lf = ttk.Labelframe(canvas, text=title, width=canvas_w, height=img_h)
        lf.grid_propagate(False)
        lf.columnconfigure(0, weight=1)
        lf.rowconfigure(0, weight=1)
        ttk.Label(lf, text="None", anchor="center").grid(column=0, row=0, sticky=(N, S, W, E))
    else:
        lf = ttk.Labelframe(canvas, text=title, width=canvas_w)
        lf.columnconfigure(0, weight=1)
        lf.columnconfigure(1, weight=1)
        for i in range(count):
            add_pair(lf, i, img_h)

    canvas.create_window((0, start_y), window=lf, anchor="nw")
    lf.update_idletasks()
    return start_y + lf.winfo_reqheight()

def set_preview_image_counts(num_previews=1, num_images=1):
    try:
        n_prev = max(0, int(num_previews))
        n_img = max(0, int(num_images))
    except (ValueError, TypeError):
        return

    content_canvas.delete("all")
    for child in list(content_canvas.winfo_children()):
        child.destroy()

    y = _build_canvas_section(content_canvas, "Previews", n_prev, 0)
    y = _build_canvas_section(content_canvas, "Images", n_img, y)

    canvas_w = get_canvas_width()
    content_canvas.update_idletasks()
    content_canvas.configure(scrollregion=(0, 0, canvas_w, y))
    content_canvas.yview_moveto(0)

def _on_mousewheel(event):
    if content_canvas.yview() == (0.0, 1.0):
        return
    if event.num == 4:
        content_canvas.yview_scroll(-get_scroll_step(), "units")
    elif event.num == 5:
        content_canvas.yview_scroll(get_scroll_step(), "units")
    elif getattr(event, "delta", 0):
        content_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

def _bind_mousewheel(event):
    content_canvas.bind_all("<Button-4>", _on_mousewheel)
    content_canvas.bind_all("<Button-5>", _on_mousewheel)
    content_canvas.bind_all("<MouseWheel>", _on_mousewheel)

def _unbind_mousewheel(event):
    content_canvas.unbind_all("<Button-4>")
    content_canvas.unbind_all("<Button-5>")
    content_canvas.unbind_all("<MouseWheel>")

def on_category_select(event=None):
    populate_materials(current_target_dir, category_var.get())

def on_material_select(event=None):
    sel = material_list.curselection()
    if not sel:
        set_preview_image_counts(0, 0)
        return

    item = material_list.get(sel[0])
    cat = category_var.get()
    data = get_category_data(current_target_dir, cat)
    mat = data.get("materials", {}).get(item, {})
    n_prev = 1 if mat.get("preview") else 0
    imgs = mat.get("images", [])
    n_img = len(imgs) if isinstance(imgs, list) else 0
    set_preview_image_counts(n_prev, n_img)

root = Tk()
root.title("Material Library Workbench")
root.option_add('*tearOff', FALSE)
root.resizable(False, False)

root.createcommand("set_preview_image_counts", set_preview_image_counts)
load_tcl_config(root, base_dir)

load_style_config(root, base_dir)

category_var = StringVar()
materials_in_cat_var = StringVar(value="Materials in category: 0")

output_var = StringVar()
materials_in_out_var = StringVar(value="Output directory")

mainframe = ttk.Frame(root)
mainframe.grid(column=0, row=0, sticky=(N, W, E, S))

menubar = Menu(root)
file_menu = Menu(menubar)
menubar.add_cascade(menu=file_menu, label="File")
file_menu.add_command(label='Open...', command=open_library)
root['menu'] = menubar

material = ttk.LabelFrame(mainframe, text="Material")
material.grid(column=0, row=1, rowspan=2, sticky=(N, S, E, W))
material.rowconfigure(0, weight=1)
material.columnconfigure(0, weight=1)

material_list = Listbox(material, exportselection=False)
material_list.grid(column=0, row=0, sticky=(N, S, E, W))

category = ttk.Combobox(mainframe, textvariable=category_var)
category.state(["readonly"])
category.grid(column=0, row=0, sticky=(W, E))

ttk.Label(mainframe, textvariable=materials_in_cat_var, anchor="w", relief="sunken").grid(column=1, row=0, sticky=(W, E))
ttk.Label(mainframe, textvariable=materials_in_out_var, anchor="w", relief="sunken").grid(column=2, row=0, sticky=(W, E))

content_canvas = Canvas(mainframe, width=get_canvas_width(), height=2 * get_image_height(), yscrollincrement=32)
content_scroll = ttk.Scrollbar(mainframe, orient=VERTICAL, command=content_canvas.yview)
content_canvas.configure(yscrollcommand=content_scroll.set)

content_canvas.grid(column=1, row=1, rowspan=2, columnspan=2, sticky=(N, S, E, W))
content_scroll.grid(column=3, row=1, rowspan=2, sticky=(N, S))

tool_strip = ttk.Frame(mainframe)
tool_strip.grid(column=0, row=3, columnspan=4, sticky=(N, S, E, W))
tool_strip.columnconfigure(1, weight=1)
tool_strip.rowconfigure(0, weight=1)

info_text = StringVar()
operation_text = StringVar()

version = ttk.Label(tool_strip, text=" Version 0.1 ", state="disabled")
version.grid(column=0, row=0, sticky=W)
info = ttk.Label(tool_strip, anchor="center", state="disabled", textvariable=info_text)
info.grid(column=1, row=0, sticky=(W, E))
operation = ttk.Label(tool_strip, anchor="center", state="disabled", textvariable=operation_text)
operation.grid(column=2, row=0, sticky=E)
progress = ttk.Progressbar(tool_strip, orient=HORIZONTAL, length=200, mode='determinate')
progress.grid(column=3, row=0, sticky=W)
progress.grid_remove()
copyright = ttk.Label(tool_strip, text=" © 2026 EvokeMadness ", state="disabled")
copyright.grid(column=4, row=0, sticky=E)

log = ttk.Labelframe(mainframe, text=" Log ")
log.grid(column=0, row=4, columnspan=4, sticky=(N, S, E, W))
log.columnconfigure(0, weight=1)
log.rowconfigure(0, weight=1)

log_output = Text(log, height=8, state="disabled")
log_output.grid(column=0, row=0, sticky=(N, S, E, W))

log_scroll = ttk.Scrollbar(log, orient=VERTICAL, command=log_output.yview)
log_scroll.grid(column=1, row=0, sticky=(N, S))
log_output['yscrollcommand'] = log_scroll.set

def clear_log():
    log_output.configure(state="normal")
    log_output.delete("1.0", END)
    log_output.configure(state="disabled")

def save_log():
    path = filedialog.asksaveasfilename(
        title="Save Log",
        defaultextension=".txt",
        filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")]
    )
    if path:
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(log_output.get("1.0", "end-1c"))
        except Exception:
            pass

def toggle_log(event=None):
    if log.grid_info():
        log.grid_remove()
    else:
        log.grid()

log_tool_strip = ttk.Frame(log)
log_tool_strip.grid(column=0, row=1, columnspan=2, sticky=(W, E))
save_btn = ttk.Button(log_tool_strip, text=" Save ", command=save_log)
save_btn.grid(column=0, row=0, sticky=W)
clear_btn = ttk.Button(log_tool_strip, text=" Clear ", command=clear_log)
clear_btn.grid(column=1, row=0, sticky=W)

log.grid_remove()

for w in (tool_strip, version, info, operation, copyright):
    w.bind("<Button-1>", toggle_log)

root.createcommand("toggleLog", toggle_log)
root.createcommand("clearLog", clear_log)
root.createcommand("writeToLog", write_to_log)

root.columnconfigure(0, weight=1)
root.rowconfigure(0, weight=1)
mainframe.columnconfigure(1, weight=1, uniform="preview_cols")
mainframe.columnconfigure(2, weight=1, uniform="preview_cols")

category.bind("<<ComboboxSelected>>", on_category_select)
content_canvas.bind("<Enter>", _bind_mousewheel)
content_canvas.bind("<Leave>", _unbind_mousewheel)
material_list.bind("<<ListboxSelect>>", on_material_select)

populate_categories(base_dir)
if not category.get():
    set_preview_image_counts(1, 1)

load_debug_config(root, base_dir)

root.mainloop()