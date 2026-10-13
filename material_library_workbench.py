import hashlib
import json
import os
import queue
import re
import shutil
import subprocess
import threading
import webbrowser
from tkinter import *
from tkinter import filedialog
from tkinter import ttk
from urllib.parse import unquote, urlparse
from PIL import Image, ImageOps, ImageTk

base_dir = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
canvas_sections = {}
category_cache = {}
clipboard_image_path = None
current_target_dir = base_dir
home_dir = os.path.expanduser("~")
image_cache = {}
image_context_menu = None
info_clear_job = None
output_manifest = {}
recent_menu = None
search_state = {"in_images": False, "index": -1, "match_word": False, "query": "", "results": []}
staged_changes = {}


def source_tcl_script(app_root, target_dir, filename):
    if app_root is None or not isinstance(target_dir, str):
        return
    path = os.path.join(target_dir, filename)
    if os.path.isfile(path):
        app_root.tk.call("source", path)


def load_tcl_config(app_root, target_dir):
    source_tcl_script(app_root, target_dir, "config.tcl")


def load_style_config(app_root, target_dir):
    source_tcl_script(app_root, target_dir, "style.tcl")


def load_help_config(app_root, target_dir):
    source_tcl_script(app_root, target_dir, "help.tcl")


def load_find_config(app_root, target_dir):
    source_tcl_script(app_root, target_dir, "find.tcl")


def get_image_height():
    try:
        return int(root.getvar("image_height"))
    except Exception:
        return 384


def get_canvas_width():
    return 2 * get_image_height()


def get_manifests_dir(target_dir=None):
    src_dir = target_dir or current_target_dir
    default_dir = os.path.join(
        os.environ.get("XDG_DATA_HOME") or os.path.join(home_dir, ".local", "share"),
        "material-library-workbench",
        "manifests"
    )
    raw_path = default_dir
    try:
        raw_path = root.getvar("manifests_path") or default_dir
    except Exception:
        pass
    expanded = os.path.expanduser(os.path.expandvars(raw_path))
    if os.path.isabs(expanded):
        return expanded
    return os.path.join(src_dir, expanded)


def get_scroll_step():
    try:
        return int(root.getvar("scroll_step"))
    except Exception:
        return 2


def populate_categories(target_dir=None):
    global current_target_dir
    current_target_dir = target_dir or base_dir
    manifests_dir = get_manifests_dir(current_target_dir)
    if not os.path.isdir(manifests_dir):
        return

    path = os.path.join(manifests_dir, "index.json")
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as file_obj:
                index_data = json.load(file_obj)
            if target_dir is None:
                saved_source = index_data.get("source_dir")
                if saved_source and os.path.isdir(saved_source):
                    current_target_dir = saved_source
            cats = sorted(index_data.get("categories", {}).keys())
        except Exception:
            cats = []
    else:
        cats = sorted([
            os.path.splitext(filename)[0]
            for filename in os.listdir(manifests_dir)
            if filename.endswith(".json")
        ])

    if cats:
        category["values"] = cats
        category.current(0)
        populate_materials(current_target_dir, cats[0])


def populate_materials(target_dir=None, selected_cat=None):
    manifests_dir = get_manifests_dir(target_dir)
    if not os.path.isdir(manifests_dir):
        return

    cat = selected_cat or category_var.get()
    data = get_category_data(target_dir, cat)
    mats = sorted(data.get("materials", {}).keys())

    material_list.delete(0, END)
    if mats:
        material_list.insert(END, *mats)
        material_list.selection_set(0)
        material_list.activate(0)
    materials_in_category_var.set(f"Materials in category: {len(mats)}")
    on_material_select()


def get_category_data(target_dir=None, cat_name=None):
    if not cat_name:
        return {}
    manifests_dir = get_manifests_dir(target_dir)
    key = (manifests_dir, cat_name)
    if key in category_cache:
        return category_cache[key]
    path = os.path.join(manifests_dir, f"{cat_name}.json")
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                category_cache[key] = data
                return data
        except Exception:
            pass
    return {}


def on_material_select(event=None):
    for key in [k for k in image_cache if len(k) > 1 and k[1] == "pil"]:
        image_cache.pop(key, None)
    sel = material_list.curselection()
    if not sel:
        images_in_material_var.set("Images in material: 0")
        update_canvas_display([], [])
        return

    item = material_list.get(sel[0])
    cat = category_var.get()
    data = get_category_data(current_target_dir, cat)
    mat = data.get("materials", {}).get(item, {})
    cat_imgs = data.get("images", {})

    preview_items = []
    prev_rel = mat.get("preview")
    if prev_rel:
        prev_name = os.path.basename(prev_rel)
        prev_path = resolve_image_path(prev_rel)
        prev_res = get_image_resolution(prev_path)
        preview_items.append({
            "rel": prev_rel,
            "src": {
                "name": prev_name,
                "path": prev_path,
                "resolution": prev_res
            },
            "rep": get_rep_data(prev_rel, prev_path)
        })

    image_items = []
    mat_imgs = mat.get("images", [])
    if isinstance(mat_imgs, list):
        for img_name in mat_imgs:
            img_meta = cat_imgs.get(img_name, {})
            img_rel = img_meta.get("relative_path") or f"rprmaterials/Maps/{img_name}"
            img_path = resolve_image_path(img_rel)
            if not os.path.isfile(img_path) and img_meta.get("source_path"):
                candidate = img_meta.get("source_path")
                if os.path.isfile(candidate):
                    img_path = candidate

            img_res = img_meta.get("resolution")
            if not img_res or img_res == "Unknown":
                img_res = get_image_resolution(img_path)

            image_items.append({
                "rel": img_rel,
                "src": {
                    "name": img_name,
                    "path": img_path,
                    "resolution": img_res
                },
                "rep": get_rep_data(img_rel, img_path)
            })

    images_in_material_var.set(f"Images in material: {len(preview_items) + len(image_items)}")
    update_canvas_display(preview_items, image_items)


def resolve_image_path(image_path):
    if not image_path:
        return ""
    if os.path.isabs(image_path):
        return image_path
    candidate = os.path.join(current_target_dir, image_path)
    if os.path.isfile(candidate):
        return candidate
    candidate = os.path.join(base_dir, image_path)
    return candidate if os.path.isfile(candidate) else image_path


def get_image_resolution(image_path):
    path = resolve_image_path(image_path)
    if not path or not os.path.isfile(path):
        return "Unknown"
    try:
        with Image.open(path) as im:
            return f"{im.width} × {im.height} pixels"
    except Exception:
        return "Unknown"


def is_entry_committed(entry):
    return isinstance(entry, dict) and bool(
        entry.get("committed") or entry.get("status") in ("modified", "deleted")
    )


def get_rep_data(rel_path, src_path=None):
    if not rel_path:
        return {}
    entry = output_manifest.get(rel_path)
    was_committed = is_entry_committed(entry)
    staged_path = staged_changes.get(rel_path)
    if staged_path and os.path.isfile(staged_path):
        return {
            "name": os.path.basename(staged_path),
            "path": staged_path,
            "resolution": get_image_resolution(staged_path),
            "style": "Modified.TLabelframe" if was_committed else "Added.TLabelframe"
        }
    out_dir = output_var.get()
    if out_dir:
        out_path = os.path.join(out_dir, rel_path)
        if os.path.isfile(out_path):
            if not isinstance(entry, dict) or entry.get("status") == "deleted":
                update_output_manifest_entry(rel_path, src_path, out_path)
                entry = output_manifest.get(rel_path, {})
            if entry.get("committed"):
                style = "TLabelframe"
            elif entry.get("status") == "modified":
                style = "Modified.TLabelframe"
            else:
                style = "Added.TLabelframe"
            return {
                "name": os.path.basename(out_path),
                "path": out_path,
                "resolution": get_image_resolution(out_path),
                "style": style
            }
        if isinstance(entry, dict) and entry.get("status") == "deleted":
            return {"style": "Deleted.TLabelframe"}
        if rel_path in output_manifest:
            output_manifest.pop(rel_path, None)
            save_output_manifest(out_dir)
    return {}


def update_output_manifest_entry(rel_path, src_path, out_path):
    if not rel_path or not out_path or not os.path.isfile(out_path):
        return
    prev_entry = output_manifest.get(rel_path)
    was_committed = is_entry_committed(prev_entry)
    src_hash = get_file_sha256(src_path) if src_path and os.path.isfile(src_path) else ""
    out_hash = get_file_sha256(out_path)
    output_manifest[rel_path] = {
        "committed": False,
        "status": "modified" if was_committed else "added",
        "source_sha256": src_hash,
        "output_sha256": out_hash,
    }
    save_output_manifest()


def get_file_sha256(path):
    if not path or not os.path.isfile(path):
        return ""
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except Exception:
        return ""


def save_output_manifest(out_dir=None):
    target_out_dir = out_dir or output_var.get()
    if not target_out_dir or not os.path.isdir(target_out_dir) or is_source_dir(target_out_dir):
        return
    path = os.path.join(target_out_dir, "changes.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(output_manifest, f, indent=2, sort_keys=True)
    except Exception:
        pass


def is_source_dir(path):
    if not path:
        return False
    src_dir = current_target_dir or base_dir
    return os.path.realpath(path) in (os.path.realpath(src_dir), os.path.realpath(base_dir))


def update_canvas_display(preview_items=None, image_items=None):
    preview_items = preview_items or []
    image_items = image_items or []

    y, prev_changed = build_canvas_section(content_canvas, "Previews", preview_items, 0)
    y, img_changed = build_canvas_section(content_canvas, "Images", image_items, y)

    if prev_changed or img_changed:
        content_canvas.update_idletasks()
        children = [section["frame"] for section in canvas_sections.values() if section["frame"].winfo_exists()]
        canvas_w = max([get_canvas_width(), int(content_canvas.cget("width"))] + [child.winfo_reqwidth() for child in children])
        for child in children:
            if child.winfo_reqwidth() < canvas_w:
                child.configure(width=canvas_w)
        content_canvas.configure(width=canvas_w, scrollregion=(0, 0, canvas_w, y))
    content_canvas.yview_moveto(0)


def build_canvas_section(canvas, title, items_or_count, start_y):
    img_h = get_image_height()
    canvas_w = get_canvas_width()

    if isinstance(items_or_count, int):
        items = [{} for _ in range(max(0, items_or_count))]
    elif isinstance(items_or_count, list):
        items = items_or_count
    else:
        items = []

    count = len(items)
    section = canvas_sections.get(title)
    if section is None or not section["frame"].winfo_exists():
        section_frame = ttk.Labelframe(canvas, text=title, width=canvas_w)
        section_frame.columnconfigure(0, weight=1)
        section_frame.columnconfigure(1, weight=1)
        section_frame.columnconfigure(2, weight=1)
        none_label = ttk.Label(section_frame, text="None", anchor="center")
        win_id = canvas.create_window((0, start_y), window=section_frame, anchor="nw")
        section = {
            "frame": section_frame,
            "win_id": win_id,
            "none_label": none_label,
            "pairs": [],
            "active_count": None,
            "img_h": None,
            "y": start_y,
            "height": 0,
        }
        canvas_sections[title] = section

    section_frame = section["frame"]
    pairs = section["pairs"]
    active_count = section["active_count"]
    layout_changed = (active_count != count or section["img_h"] != img_h)

    if count == 0:
        if layout_changed:
            if active_count:
                for i in range(active_count):
                    pairs[i]["src"].grid_remove()
                    pairs[i]["edit"].grid_remove()
                    pairs[i]["rep"].grid_remove()
            section_frame.grid_propagate(False)
            section_frame.configure(width=canvas_w, height=img_h)
            section_frame.rowconfigure(0, weight=1)
            section["none_label"].grid(column=0, row=0, columnspan=3, sticky=(N, S, W, E))
    else:
        if active_count == 0 or active_count is None:
            section["none_label"].grid_remove()
            section_frame.rowconfigure(0, weight=0)
            section_frame.grid_propagate(True)
        prev_existing = len(pairs)
        while len(pairs) < count:
            pairs.append(add_pair(section_frame, len(pairs), img_h))
        if active_count != count:
            if active_count is not None and active_count > count:
                for i in range(count, active_count):
                    pairs[i]["src"].grid_remove()
                    pairs[i]["edit"].grid_remove()
                    pairs[i]["rep"].grid_remove()
            else:
                start_idx = max(0, active_count or 0)
                for i in range(start_idx, min(count, prev_existing)):
                    pairs[i]["src"].grid()
                    pairs[i]["edit"].grid()
                    pairs[i]["rep"].grid()
        for i, item_data in enumerate(items):
            src_data = item_data.get("src", item_data)
            rep_data = item_data.get("rep", {})
            rel_path = item_data.get("rel")
            update_pair(pairs[i], img_h, src_data=src_data, rep_data=rep_data, rel_path=rel_path)

    section["active_count"] = count
    section["img_h"] = img_h

    if section["y"] != start_y:
        canvas.coords(section["win_id"], 0, start_y)
        section["y"] = start_y
        layout_changed = True

    if layout_changed:
        section_frame.update_idletasks()
        section["height"] = section_frame.winfo_reqheight()

    return start_y + section["height"], layout_changed


def add_pair(parent, pair_index, img_h=None, src_data=None, rep_data=None, rel_path=None):
    if parent is None or not isinstance(pair_index, int):
        return None
    if img_h is None:
        img_h = get_image_height()
    src = ttk.Labelframe(parent, text="Source", width=img_h, height=img_h)
    src.grid(column=0, row=pair_index)
    edit = ttk.Frame(parent)
    edit.grid(column=1, row=pair_index)
    rep = ttk.Labelframe(parent, text="Replace with", width=img_h, height=img_h)
    rep.grid(column=2, row=pair_index)

    left_button = ttk.Button(edit, text="←")
    left_button.grid(column=0, row=0)
    right_button = ttk.Button(edit, text="→")
    right_button.grid(column=0, row=1)
    clear_button = ttk.Button(edit, text="Clear")
    clear_button.grid(column=0, row=2)

    pair = {
        "src": src,
        "edit": edit,
        "rep": rep,
        "src_name": filename_strip(src),
        "src_slot": photo_slot(src),
        "src_res": resolution_strip(src),
        "rep_name": filename_strip(rep),
        "rep_slot": photo_slot(rep),
        "rep_res": resolution_strip(rep),
        "img_h": img_h,
        "rel_path": rel_path,
        "src_data": src_data or {},
        "rep_data": rep_data or {},
        "zoom": 1.0,
        "pan": (0.5, 0.5),
        "drag_start": None,
        "drag_pan": (0.5, 0.5),
    }
    left_button.configure(command=lambda: on_left_arrow(pair))
    right_button.configure(command=lambda: on_right_arrow(pair))
    clear_button.configure(command=lambda: on_clear_pair(pair))
    pair["rep_slot"].bind("<Button-1>", lambda event: on_rep_click(pair))
    for slot in (pair["src_slot"], pair["rep_slot"]):
        slot.bind("<Button-4>", lambda event, p=pair: on_slot_zoom(event, p))
        slot.bind("<Button-5>", lambda event, p=pair: on_slot_zoom(event, p))
        slot.bind("<MouseWheel>", lambda event, p=pair: on_slot_zoom(event, p))
        slot.bind("<ButtonPress-2>", lambda event, p=pair: on_slot_pan_start(event, p))
        slot.bind("<B2-Motion>", lambda event, p=pair: on_slot_pan_move(event, p))

    src_targets = [pair["src_slot"], pair["src"]]
    if pair["src_name"]:
        src_targets.extend([pair["src_name"], pair["src_name"].master])
    if pair["src_res"]:
        src_targets.extend([pair["src_res"], pair["src_res"].master])
    for w in src_targets:
        w.bind("<Button-3>", lambda event, p=pair: show_image_context_menu(event, True, p))

    rep_targets = [pair["rep_slot"], pair["rep"]]
    if pair["rep_name"]:
        rep_targets.extend([pair["rep_name"], pair["rep_name"].master])
    if pair["rep_res"]:
        rep_targets.extend([pair["rep_res"], pair["rep_res"].master])
    for w in rep_targets:
        w.bind("<Button-3>", lambda event, p=pair: show_image_context_menu(event, False, p))

    if src_data is not None or rep_data is not None or rel_path is not None:
        update_pair(pair, img_h, src_data=src_data, rep_data=rep_data, rel_path=rel_path)
    return pair


def filename_strip(parent, text="Name:"):
    if parent is None:
        return None
    banner = ttk.Frame(parent, height=25, style="Strip.TFrame")
    banner.grid(column=0, row=0, sticky=(N, W, E))
    banner.columnconfigure(0, weight=1)

    display_text = text if text else "Name:"
    label = ttk.Label(banner, text=display_text, anchor="center", style="Strip.TLabel")
    label.grid(column=0, row=0, sticky=(W, E), padx=4)
    return label


def photo_slot(parent, image_path=None, max_size=None):
    if parent is None:
        return None
    slot = Label(parent, bg="black")
    slot.grid(column=0, row=1, sticky=(N, S, E, W))
    slot.image = None
    slot.is_photo_slot = True
    if image_path:
        configure_photo_slot(slot, image_path, max_size)
    return slot


def resolution_strip(parent, text="Resolution:"):
    if parent is None:
        return None
    parent.grid_propagate(False)
    parent.rowconfigure(1, weight=1)
    parent.columnconfigure(0, weight=1)

    banner = ttk.Frame(parent, height=25, style="Strip.TFrame")
    banner.grid(column=0, row=2, sticky=(S, W, E))
    banner.columnconfigure(0, weight=1)

    label = ttk.Label(banner, text=format_resolution_text(text), anchor="w", style="Strip.TLabel")
    label.grid(column=0, row=0, sticky=(W, E), padx=4)
    return label


def format_resolution_text(text=None):
    display_text = text if text else "Resolution:"
    if display_text == "Resolution":
        return "Resolution:"
    if not display_text.startswith("Resolution:"):
        return f"Resolution: {display_text}"
    return display_text


def update_pair(pair, img_h=None, src_data=None, rep_data=None, rel_path=None):
    if not pair:
        return
    if img_h is None:
        img_h = get_image_height()
    if pair.get("img_h") != img_h:
        pair["src"].configure(width=img_h, height=img_h)
        pair["rep"].configure(width=img_h, height=img_h)
        pair["img_h"] = img_h

    if pair.get("rel_path") != rel_path:
        pair["zoom"] = 1.0
        pair["pan"] = (0.5, 0.5)

    src_data = src_data or {}
    rep_data = rep_data or {}
    pair["rel_path"] = rel_path
    pair["src_data"] = src_data
    pair["rep_data"] = rep_data
    max_size = get_slot_max_size(img_h)
    zoom = pair.get("zoom", 1.0)
    pan = pair.get("pan", (0.5, 0.5))

    rep_style = rep_data.get("style", "TLabelframe")
    if pair["rep"].cget("style") != rep_style:
        pair["rep"].configure(style=rep_style)

    for side, data in (("src", src_data), ("rep", rep_data)):
        name_text = data.get("name") or "Name:"
        name_label = pair[f"{side}_name"]
        if name_label.cget("text") != name_text:
            name_label.configure(text=name_text)

        configure_photo_slot(pair[f"{side}_slot"], data.get("path"), max_size, zoom=zoom, pan=pan)

        res_text = format_resolution_text(data.get("resolution"))
        res_label = pair[f"{side}_res"]
        if res_label.cget("text") != res_text:
            res_label.configure(text=res_text)


def get_slot_max_size(img_h=None):
    if img_h is None:
        img_h = get_image_height()
    return (max(1, img_h - 10), max(1, img_h - 75))


def configure_photo_slot(slot, image_path=None, max_size=None, zoom=1.0, pan=(0.5, 0.5)):
    if slot is None:
        return
    if image_path:
        photo = get_slot_photo(image_path, max_size, zoom=zoom, pan=pan)
        if photo:
            if getattr(slot, "image", None) is not photo:
                slot.configure(image=photo, text="")
                slot.image = photo
        else:
            slot.configure(image="", text="🖾", fg="gray", font=("TkDefaultFont", 32))
            slot.image = None
            write_to_log(
                f'Image "{image_path}" was not found on disk!',
                f'Image "{os.path.basename(image_path)}" was not found on disk!'
            )
    elif getattr(slot, "image", None) is not None or slot.cget("text"):
        slot.configure(image="", text="")
        slot.image = None


def get_slot_photo(image_path, max_size=None, zoom=1.0, pan=(0.5, 0.5)):
    path = resolve_image_path(image_path)
    if not path or not os.path.isfile(path):
        return None
    if max_size is None:
        max_size = get_slot_max_size()

    abs_path = os.path.abspath(path)
    if zoom <= 1.0:
        key = (abs_path, max_size)
        if key in image_cache:
            return image_cache[key]
        try:
            with Image.open(path) as im:
                contained = ImageOps.contain(im, max_size, Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(contained)
                image_cache[key] = photo
                return photo
        except Exception:
            return None

    try:
        pil_key = (abs_path, "pil")
        im = image_cache.get(pil_key)
        if im is None:
            with Image.open(path) as src_im:
                src_im.load()
                im = src_im.copy()
            image_cache[pil_key] = im
        scale = min(max_size[0] / im.width, max_size[1] / im.height)
        base_w = max(1, round(im.width * scale))
        base_h = max(1, round(im.height * scale))
        half = 0.5 / zoom
        cx = min(max(pan[0], half), 1.0 - half)
        cy = min(max(pan[1], half), 1.0 - half)
        box = (
            (cx - half) * im.width,
            (cy - half) * im.height,
            (cx + half) * im.width,
            (cy + half) * im.height,
        )
        cropped = im.resize((base_w, base_h), Image.Resampling.BILINEAR, box=box)
        return ImageTk.PhotoImage(cropped)
    except Exception:
        return None


def bind_mousewheel(event):
    content_canvas.bind_all("<Button-4>", on_mousewheel)
    content_canvas.bind_all("<Button-5>", on_mousewheel)
    content_canvas.bind_all("<MouseWheel>", on_mousewheel)


def on_mousewheel(event):
    if getattr(event.widget, "is_photo_slot", False):
        return
    if content_canvas.yview() == (0.0, 1.0):
        return
    if event.num == 4:
        content_canvas.yview_scroll(-get_scroll_step(), "units")
    elif event.num == 5:
        content_canvas.yview_scroll(get_scroll_step(), "units")
    elif getattr(event, "delta", 0):
        content_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")


def unbind_mousewheel(event):
    content_canvas.unbind_all("<Button-4>")
    content_canvas.unbind_all("<Button-5>")
    content_canvas.unbind_all("<MouseWheel>")


def on_slot_zoom(event, pair):
    src_path = pair.get("src_data", {}).get("path")
    rep_path = pair.get("rep_data", {}).get("path")
    if not src_path and not rep_path:
        return
    old_zoom = pair.get("zoom", 1.0)
    if event.num == 4 or getattr(event, "delta", 0) > 0:
        new_zoom = old_zoom * 1.25
    elif event.num == 5 or getattr(event, "delta", 0) < 0:
        new_zoom = max(1.0, old_zoom / 1.25)
    else:
        return
    if new_zoom <= 1.01:
        new_zoom = 1.0
        new_pan = (0.5, 0.5)
    else:
        slot = event.widget
        base_w, base_h = get_slot_base_size(slot, pair.get("img_h"))
        rel_x = min(max((event.x - slot.winfo_width() / 2.0) / base_w, -0.5), 0.5)
        rel_y = min(max((event.y - slot.winfo_height() / 2.0) / base_h, -0.5), 0.5)
        cx, cy = pair.get("pan", (0.5, 0.5))
        pt_x = cx + rel_x / old_zoom
        pt_y = cy + rel_y / old_zoom
        half = 0.5 / new_zoom
        new_cx = min(max(pt_x - rel_x / new_zoom, half), 1.0 - half)
        new_cy = min(max(pt_y - rel_y / new_zoom, half), 1.0 - half)
        new_pan = (new_cx, new_cy)
    if new_zoom == old_zoom and new_pan == pair.get("pan", (0.5, 0.5)):
        return
    pair["zoom"] = new_zoom
    pair["pan"] = new_pan
    refresh_pair_slots(pair)


def on_slot_pan_start(event, pair):
    pair["drag_start"] = (event.x, event.y)
    pair["drag_pan"] = pair.get("pan", (0.5, 0.5))


def on_slot_pan_move(event, pair):
    zoom = pair.get("zoom", 1.0)
    drag_start = pair.get("drag_start")
    if zoom <= 1.0 or not drag_start:
        return
    base_w, base_h = get_slot_base_size(event.widget, pair.get("img_h"))
    dx = event.x - drag_start[0]
    dy = event.y - drag_start[1]
    start_cx, start_cy = pair.get("drag_pan", (0.5, 0.5))
    half = 0.5 / zoom
    new_cx = min(max(start_cx - dx / (base_w * zoom), half), 1.0 - half)
    new_cy = min(max(start_cy - dy / (base_h * zoom), half), 1.0 - half)
    new_pan = (new_cx, new_cy)
    if new_pan != pair.get("pan"):
        pair["pan"] = new_pan
        refresh_pair_slots(pair)


def get_slot_base_size(slot, img_h=None):
    photo = getattr(slot, "image", None)
    if photo:
        return (max(1, photo.width()), max(1, photo.height()))
    return get_slot_max_size(img_h)


def refresh_pair_slots(pair):
    max_size = get_slot_max_size(pair.get("img_h"))
    zoom = pair.get("zoom", 1.0)
    pan = pair.get("pan", (0.5, 0.5))
    configure_photo_slot(pair["src_slot"], pair.get("src_data", {}).get("path"), max_size, zoom=zoom, pan=pan)
    configure_photo_slot(pair["rep_slot"], pair.get("rep_data", {}).get("path"), max_size, zoom=zoom, pan=pan)


def run_zenity_file_dialog(args):
    if shutil.which("zenity"):
        proc = subprocess.run(
            ["zenity", "--file-selection", *args],
            capture_output=True,
            text=True,
        )
        return proc.stdout.strip() if proc.returncode == 0 else ""
    return None


def get_image_format(image_path):
    if not image_path:
        return ""
    if os.path.isfile(image_path):
        try:
            with Image.open(image_path) as img:
                if img.format:
                    return img.format.upper()
        except Exception:
            pass
    ext = os.path.splitext(image_path)[1].lower().lstrip(".")
    return {"jpg": "JPEG", "tif": "TIFF"}.get(ext, ext.upper())


def validate_pair_image_format(pair, image_path):
    rel_path = pair.get("rel_path")
    src_data = pair.get("src_data", {})
    src_fmt = get_image_format(src_data.get("path") or rel_path)
    rep_fmt = get_image_format(image_path)
    if src_fmt and rep_fmt != src_fmt:
        write_to_log(f"Image format mismatch: expected {src_fmt}, got {rep_fmt or 'unknown'}!")
        return False
    return True


def stage_pair_image(pair, path):
    rel_path = pair.get("rel_path")
    if not rel_path:
        return
    src_data = pair.get("src_data", {})
    staged_changes[rel_path] = path
    rep_data = get_rep_data(rel_path, src_data.get("path"))
    update_pair(pair, pair.get("img_h"), src_data=src_data, rep_data=rep_data, rel_path=rel_path)


def on_rep_click(pair):
    rel_path = pair.get("rel_path")
    if not rel_path:
        return
    path = run_zenity_file_dialog([
        "--title=Select Image",
        f"--filename={os.path.join(home_dir, '')}",
        "--file-filter=Image Files | *.png *.jpg *.jpeg *.bmp *.tga *.tif *.tiff *.exr *.hdr *.webp",
        "--file-filter=All Files | *",
    ])
    if path is None:
        path = filedialog.askopenfilename(
            title="Select Image",
            initialdir=home_dir,
            filetypes=[
                ("Image Files", "*.png *.jpg *.jpeg *.bmp *.tga *.tif *.tiff *.exr *.hdr *.webp"),
                ("All Files", "*.*"),
            ]
        )
    if not path or not os.path.isfile(path):
        return
    if not validate_pair_image_format(pair, path):
        return
    stage_pair_image(pair, path)


def on_left_arrow(pair):
    rel_path = pair.get("rel_path")
    if not rel_path:
        return
    rep_path = staged_changes.get(rel_path) or pair.get("rep_data", {}).get("path")
    if not rep_path or not os.path.isfile(rep_path):
        write_to_log("Please select a replacement image first!")
        return
    if not output_var.get():
        write_to_log("You have to save first!")
        return
    commit_pair_image(pair, rep_path)


def on_right_arrow(pair):
    rel_path = pair.get("rel_path")
    if not rel_path:
        return
    src_data = pair.get("src_data", {})
    src_path = src_data.get("path")
    if not src_path or not os.path.isfile(src_path):
        src_path = resolve_image_path(rel_path)
    if not src_path or not os.path.isfile(src_path):
        write_to_log("Source image was not found on disk!")
        return
    stage_pair_image(pair, src_path)


def commit_pair_image(pair, copy_src):
    if not validate_pair_image_format(pair, copy_src):
        return
    out_dir = output_var.get()
    if not out_dir:
        write_to_log("You have to save first!")
        return
    rel_path = pair.get("rel_path")
    src_data = pair.get("src_data", {})
    dst_path = os.path.join(out_dir, rel_path)
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    if os.path.abspath(copy_src) != os.path.abspath(dst_path):
        shutil.copy2(copy_src, dst_path)
        evict_image_cache(dst_path)
    update_output_manifest_entry(rel_path, src_data.get("path"), dst_path)
    staged_changes.pop(rel_path, None)
    rep_data = get_rep_data(rel_path, src_data.get("path"))
    update_pair(pair, pair.get("img_h"), src_data=src_data, rep_data=rep_data, rel_path=rel_path)


def on_clear_pair(pair):
    rel_path = pair.get("rel_path")
    src_data = pair.get("src_data", {})
    if rel_path:
        staged_changes.pop(rel_path, None)
        out_dir = output_var.get()
        if out_dir and not is_source_dir(out_dir):
            out_path = os.path.join(out_dir, rel_path)
            if os.path.isfile(out_path):
                os.remove(out_path)
            entry = output_manifest.get(rel_path)
            was_committed = is_entry_committed(entry)
            if was_committed:
                output_manifest[rel_path] = {
                    "committed": False,
                    "status": "deleted",
                    "source_sha256": entry.get("source_sha256", ""),
                    "output_sha256": "",
                }
            else:
                output_manifest.pop(rel_path, None)
            save_output_manifest(out_dir)
            evict_image_cache(out_path)
    rep_data = get_rep_data(rel_path, src_data.get("path"))
    update_pair(pair, pair.get("img_h"), src_data=src_data, rep_data=rep_data, rel_path=rel_path)


def evict_image_cache(image_path):
    if not image_path:
        return
    abs_path = os.path.abspath(image_path)
    for key in [k for k in image_cache if k[0] == abs_path]:
        image_cache.pop(key, None)


def open_with_image_viewer(filepath):
    if not filepath or not os.path.isfile(filepath):
        write_to_log("Image file not found on disk!")
        return
    abs_path = os.path.abspath(filepath)
    try:
        subprocess.Popen(["xdg-open", abs_path])
        write_to_log(f'Opened "{os.path.basename(abs_path)}" with image viewer.')
    except Exception as e:
        write_to_log(f"Error opening image viewer: {e}")


def open_containing_folder(filepath):
    if not filepath:
        write_to_log("Image path not found!")
        return
    abs_path = os.path.abspath(filepath)
    folder = os.path.dirname(abs_path)
    if not os.path.isdir(folder):
        write_to_log("Containing folder not found on disk!")
        return
    try:
        subprocess.Popen(["xdg-open", folder])
        write_to_log(f'Opened containing folder "{folder}".')
    except Exception as e:
        write_to_log(f"Error opening containing folder: {e}")


def set_clipboard_image_path(path):
    global clipboard_image_path
    if not path or not os.path.isfile(path):
        return
    clipboard_image_path = os.path.abspath(path)
    try:
        root.clipboard_clear()
        root.clipboard_append(clipboard_image_path)
    except Exception:
        pass


def get_clipboard_image_path():
    if clipboard_image_path and os.path.isfile(clipboard_image_path):
        return clipboard_image_path
    try:
        cb_text = root.clipboard_get()
        if cb_text:
            text = cb_text.strip()
            if text.startswith("file://"):
                path = unquote(urlparse(text).path)
            else:
                line = text.splitlines()[0].strip()
                if line.startswith("file://"):
                    path = unquote(urlparse(line).path)
                else:
                    path = line
            if os.path.isfile(path) and get_image_format(path):
                return path
    except Exception:
        pass
    return None


def on_cut_image(pair, path):
    if not path or not os.path.isfile(path):
        return
    set_clipboard_image_path(path)
    on_clear_pair(pair)
    write_to_log(f'Cut "{os.path.basename(path)}".')


def on_copy_image(path):
    if not path or not os.path.isfile(path):
        return
    set_clipboard_image_path(path)
    write_to_log(f'Copied "{os.path.basename(path)}".')


def on_paste_image(pair):
    rel_path = pair.get("rel_path")
    if not rel_path:
        return
    paste_path = get_clipboard_image_path()
    if not paste_path or not os.path.isfile(paste_path):
        write_to_log("No valid image file found on clipboard!")
        return

    if not validate_pair_image_format(pair, paste_path):
        return
    stage_pair_image(pair, paste_path)
    write_to_log(f'Pasted "{os.path.basename(paste_path)}".')


def dismiss_context_menu():
    try:
        image_context_menu.unpost()
    except Exception:
        pass


def show_image_context_menu(event, is_source, pair):
    rel_path = pair.get("rel_path")
    src_data = pair.get("src_data", {})
    rep_data = pair.get("rep_data", {})

    if is_source:
        img_path = src_data.get("path")
        if not img_path and rel_path:
            img_path = resolve_image_path(rel_path)
    else:
        staged_path = staged_changes.get(rel_path)
        img_path = staged_path or rep_data.get("path")

    has_img = bool(img_path and os.path.isfile(img_path))
    clipboard_src = get_clipboard_image_path()
    can_paste = bool(not is_source and rel_path and clipboard_src and os.path.isfile(clipboard_src))

    image_context_menu.delete(0, END)
    image_context_menu.add_command(
        label="Open With Image Viewer",
        state="normal" if has_img else "disabled",
        command=lambda p=img_path: (dismiss_context_menu(), open_with_image_viewer(p))
    )
    image_context_menu.add_command(
        label="Open Containing Folder",
        state="normal" if has_img else "disabled",
        command=lambda p=img_path: (dismiss_context_menu(), open_containing_folder(p))
    )
    image_context_menu.add_separator()
    image_context_menu.add_command(
        label="Cut",
        state="normal" if (not is_source and has_img) else "disabled",
        command=lambda p=pair, pth=img_path: (dismiss_context_menu(), on_cut_image(p, pth))
    )
    image_context_menu.add_command(
        label="Copy",
        state="normal" if has_img else "disabled",
        command=lambda pth=img_path: (dismiss_context_menu(), on_copy_image(pth))
    )
    image_context_menu.add_separator()
    image_context_menu.add_command(
        label="Paste",
        state="normal" if can_paste else "disabled",
        command=lambda p=pair: (dismiss_context_menu(), on_paste_image(p))
    )

    image_context_menu.tk_popup(event.x_root, event.y_root)


def on_category_select(event=None):
    populate_materials(current_target_dir, category_var.get())


def new_session(event=None):
    output_var.set("")
    staged_changes.clear()
    output_manifest.clear()
    image_cache.clear()
    on_material_select()
    write_to_log("New session.")


def get_appdata_dir():
    candidates = []
    if os.environ.get("XDG_DATA_HOME"):
        candidates.append(os.path.join(os.environ["XDG_DATA_HOME"], "material-library-workbench"))
    candidates.append(os.path.expanduser("~/.local/share/material-library-workbench"))
    candidates.append(os.path.expanduser("~/.config/material-library-workbench"))

    for path in candidates:
        if os.path.isdir(path):
            return path

    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    target = os.path.join(base, "material-library-workbench")
    try:
        os.makedirs(target, exist_ok=True)
    except Exception:
        pass
    return target


def get_recent_files_path():
    return os.path.join(get_appdata_dir(), "recently_used.json")


def load_recent_files():
    path = get_recent_files_path()
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return [str(p) for p in data if isinstance(p, str)][:5]
    except Exception:
        pass
    return []


def save_recent_files(recent_list):
    path = get_recent_files_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(recent_list[:5], f, indent=2)
    except Exception:
        pass


def add_recent_file(file_path):
    if not file_path:
        return
    norm_path = os.path.abspath(file_path)
    recent_list = load_recent_files()
    recent_list = [p for p in recent_list if os.path.abspath(p) != norm_path]
    recent_list.insert(0, norm_path)
    save_recent_files(recent_list[:5])
    update_recent_menu()


def remove_recent_file(file_path):
    if not file_path:
        return
    norm_path = os.path.abspath(file_path)
    recent_list = load_recent_files()
    filtered = [p for p in recent_list if os.path.abspath(p) != norm_path]
    if len(filtered) != len(recent_list):
        save_recent_files(filtered)
        update_recent_menu()


def clear_recent_files():
    save_recent_files([])
    update_recent_menu()


def update_recent_menu():
    if recent_menu is None:
        return
    recent_menu.delete(0, END)
    recent_files = load_recent_files()
    if not recent_files:
        recent_menu.add_command(label="(Empty)", state="disabled")
    else:
        for i, file_path in enumerate(recent_files, start=1):
            recent_menu.add_command(
                label=f"{i} {file_path}",
                underline=0,
                command=lambda p=file_path: open_session(target_path=p),
            )
    recent_menu.add_separator()
    recent_menu.add_command(
        label="Clear",
        command=clear_recent_files,
        state="normal" if recent_files else "disabled",
    )


def open_session(title="Open", target_path=None):
    if target_path:
        manifest_path = os.path.abspath(target_path)
        if not os.path.isfile(manifest_path):
            write_to_log(f'File "{manifest_path}" was not found on disk!')
            remove_recent_file(manifest_path)
            return
    else:
        manifest_path = ask_manifest_dialog(title if isinstance(title, str) else "Open")
        if not manifest_path or not os.path.isfile(manifest_path):
            return

    target_out_dir = os.path.dirname(os.path.abspath(manifest_path))
    if is_source_dir(target_out_dir):
        write_to_log("You cannot select the source directory!")
        return

    output_var.set(target_out_dir)
    staged_changes.clear()
    load_output_manifest(manifest_path)
    add_recent_file(manifest_path)
    on_material_select()
    write_to_log(f'Loaded session from "{manifest_path}".')


def call_tk_command(cmd):
    try:
        root.tk.call(cmd)
    except Exception:
        pass


def show_help(event=None):
    call_tk_command("show_help")


def show_find(event=None):
    call_tk_command("show_find")


def find_next(event=None):
    call_tk_command("find_next")


def find_prev(event=None):
    call_tk_command("find_prev")


def perform_find(query_str, match_word_flag, in_images_flag, direction_str):
    query = str(query_str).strip()
    if not query:
        return

    match_word = str(match_word_flag).lower() in ("1", "true")
    in_images = str(in_images_flag).lower() in ("1", "true")
    try:
        direction = int(direction_str)
    except Exception:
        direction = 1

    cache_key = (query, match_word, in_images)
    prev_key = (search_state["query"], search_state["match_word"], search_state["in_images"])

    if cache_key != prev_key or not search_state["results"]:
        if match_word:
            pattern = re.compile(rf"\b{re.escape(query)}\b", re.IGNORECASE)
            is_match = lambda s: bool(pattern.search(s)) if s else False
        else:
            q_lower = query.lower()
            is_match = lambda s: q_lower in s.lower() if s else False

        cats = list(category["values"])
        if not cats:
            manifests_dir = get_manifests_dir(current_target_dir)
            if os.path.isdir(manifests_dir):
                cats = sorted([
                    os.path.splitext(f)[0]
                    for f in os.listdir(manifests_dir)
                    if f.endswith(".json") and f != "index.json"
                ])

        name_matches = []
        image_matches = []
        for cat in cats:
            cat_data = get_category_data(current_target_dir, cat)
            for mat_name, mat_info in cat_data.get("materials", {}).items():
                if is_match(mat_name):
                    name_matches.append((cat, mat_name))
                elif in_images:
                    imgs = mat_info.get("images", [])
                    prev_path = mat_info.get("preview", "")
                    if any(is_match(img) for img in imgs) or (prev_path and is_match(os.path.basename(prev_path))):
                        image_matches.append((cat, mat_name))

        results = name_matches + image_matches
        search_state["query"] = query
        search_state["match_word"] = match_word
        search_state["in_images"] = in_images
        search_state["results"] = results

        curr_cat = category_var.get()
        sel = material_list.curselection()
        curr_mat = material_list.get(sel[0]) if sel else None
        current_pair = (curr_cat, curr_mat)

        if current_pair in results:
            curr_pos = results.index(current_pair)
            search_state["index"] = (curr_pos + direction) % len(results)
        else:
            search_state["index"] = 0 if direction >= 0 else len(results) - 1
    else:
        results = search_state["results"]
        if results:
            search_state["index"] = (search_state["index"] + direction) % len(results)

    if not search_state["results"]:
        write_to_log(f'Phrase not found')
        return

    idx = search_state["index"]
    target_cat, target_mat = search_state["results"][idx]

    if category_var.get() != target_cat:
        category.set(target_cat)
        category_var.set(target_cat)
        populate_materials(current_target_dir, target_cat)

    all_mats = material_list.get(0, END)
    if target_mat in all_mats:
        mat_idx = all_mats.index(target_mat)
        material_list.selection_clear(0, END)
        material_list.selection_set(mat_idx)
        material_list.activate(mat_idx)
        material_list.see(mat_idx)
        on_material_select()

    write_to_log(f'{idx + 1} of {len(results)} matches')


MANIFEST_FILETYPES = [
    ("Changes Manifest", "changes.json"),
    ("JSON Files", "*.json"),
    ("All Files", "*.*"),
]
MANIFEST_ZENITY_FILTERS = [
    "--file-filter=Changes Manifest (changes.json) | changes.json",
    "--file-filter=JSON Files | *.json",
    "--file-filter=All Files | *",
]


def ask_manifest_dialog(title="Open"):
    initial_dir = output_var.get() or home_dir
    initial_file = os.path.join(initial_dir, "changes.json")
    path = run_zenity_file_dialog([
        f"--title={title}",
        f"--filename={initial_file}",
        *MANIFEST_ZENITY_FILTERS,
    ])
    if path is not None:
        return path
    return filedialog.askopenfilename(
        title=title,
        initialdir=initial_dir,
        filetypes=MANIFEST_FILETYPES,
    )


def ask_save_manifest_dialog(title="Save"):
    initial_dir = output_var.get() or home_dir
    initial_file = os.path.join(initial_dir, "changes.json")
    path = run_zenity_file_dialog([
        "--save",
        "--confirm-overwrite",
        f"--title={title}",
        f"--filename={initial_file}",
        *MANIFEST_ZENITY_FILTERS,
    ])
    if path is not None:
        return path
    return filedialog.asksaveasfilename(
        title=title,
        initialdir=initial_dir,
        initialfile="changes.json",
        defaultextension=".json",
        filetypes=MANIFEST_FILETYPES,
    )


def import_library(title="Import Library"):
    target_dir = ask_directory_dialog(title if isinstance(title, str) else "Import Library")
    if not target_dir or not os.path.isfile(os.path.join(target_dir, "radeon-prorender-material-library.blend")):
        return

    previews_script = os.path.join(base_dir, "import_previews.py")
    manifest_script = os.path.join(base_dir, "generate_manifest.py")
    if not os.path.isfile(manifest_script):
        return

    manifests_dir = get_manifests_dir(target_dir)

    blend_files = [
        f for f in os.listdir(target_dir)
        if f.endswith(".blend") and f != "radeon-prorender-material-library.blend"
    ]
    total_categories = len(blend_files)

    tasks = []
    if os.path.isfile(previews_script):
        tasks.append((
            "Importing previews",
            ["blender", "--factory-startup", "-b", "--python", previews_script, "--", target_dir],
            ("previews", "preview")
        ))
    tasks.append((
        "Generating manifests",
        ["blender", "--factory-startup", "-b", "--python", manifest_script, "--", target_dir, manifests_dir],
        ("materials", "material")
    ))

    def on_open_complete():
        category_cache.clear()
        image_cache.clear()
        staged_changes.clear()
        populate_categories(target_dir)

    run_blender_tasks(tasks, total_categories, on_open_complete)


def ask_directory_dialog(title="Open Directory"):
    initial_dir = os.path.dirname(output_var.get()) if output_var.get() else home_dir
    path = run_zenity_file_dialog([
        "--directory",
        f"--title={title}",
        f"--filename={os.path.join(initial_dir, '')}",
    ])
    if path is not None:
        return path
    return filedialog.askdirectory(title=title, initialdir=initial_dir)


def run_blender_tasks(tasks, total_steps, on_complete=None):
    if not tasks:
        return

    total_count = max(1, total_steps)
    progress["maximum"] = total_count
    progress["value"] = 0
    progress.grid()
    operation_var.set(f"{tasks[0][0]} (0/{total_steps})...")

    worker_queue = queue.Queue()

    def process_queue():
        try:
            while True:
                msg = worker_queue.get_nowait()
                if msg is None:
                    progress["value"] = progress["maximum"]
                    progress.grid_remove()
                    operation_var.set("")
                    if on_complete:
                        on_complete()
                    return
                action, payload = msg
                if action == "log":
                    append_log(payload)
                elif action == "phase":
                    progress["value"] = 0
                    operation_var.set(f"{payload} (0/{total_steps})...")
                elif action == "step":
                    phase_label, val, name = payload
                    progress["value"] = val
                    operation_var.set(f"{phase_label} ({val}/{total_steps}): {name}")
        except queue.Empty:
            pass
        root.after(50, process_queue)

    root.after(50, process_queue)

    def run_worker():
        try:
            env = dict(os.environ, PYTHONUNBUFFERED="1")
            for phase_label, cmd, suffixes in tasks:
                worker_queue.put(("phase", phase_label))
                proc = subprocess.Popen(
                    cmd,
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
                    if "Engine 'RPR' not available" in line:
                        continue
                    worker_queue.put(("log", line))
                    stripped = line.strip()
                    if ": " in stripped and stripped.endswith(suffixes):
                        completed += 1
                        cat_name = stripped.split(":", 1)[0].strip()
                        worker_queue.put(("step", (phase_label, completed, cat_name)))
                proc.stdout.close()
                proc.wait()
        except Exception as exc:
            worker_queue.put(("log", f"Error: {exc}\n"))
        finally:
            worker_queue.put(None)

    threading.Thread(target=run_worker, daemon=True).start()


def save_library(title="Save"):
    out_dir = output_var.get()
    if not out_dir:
        manifest_path = ask_save_manifest_dialog(title if isinstance(title, str) else "Save")
        if not manifest_path:
            return
        chosen_dir = (
            os.path.abspath(manifest_path)
            if os.path.isdir(manifest_path)
            else os.path.dirname(os.path.abspath(manifest_path))
        )
        if not perform_save(chosen_dir, create_subdir=True):
            return
        out_dir = output_var.get()
        if not out_dir:
            return

    for rel_path, staged_src in list(staged_changes.items()):
        if staged_src and os.path.isfile(staged_src):
            dst_path = os.path.join(out_dir, rel_path)
            os.makedirs(os.path.dirname(dst_path), exist_ok=True)
            if os.path.abspath(staged_src) != os.path.abspath(dst_path):
                shutil.copy2(staged_src, dst_path)
                evict_image_cache(dst_path)
            src_path = resolve_image_path(rel_path)
            update_output_manifest_entry(rel_path, src_path, dst_path)
    staged_changes.clear()

    changed_preview_cats = {
        rel_path.replace("\\", "/").split("/")[2]
        for rel_path, info in output_manifest.items()
        if isinstance(info, dict) and not info.get("committed")
        and rel_path.replace("\\", "/").startswith("rprmaterials/Previews/")
        and len(rel_path.replace("\\", "/").split("/")) >= 4
    }

    def finalize_commit():
        deleted_keys = [
            k for k, v in output_manifest.items()
            if isinstance(v, dict) and v.get("status") == "deleted"
        ]
        for k in deleted_keys:
            output_manifest.pop(k, None)
        for entry in output_manifest.values():
            if isinstance(entry, dict):
                entry["committed"] = True
        save_output_manifest(out_dir)
        on_material_select()
        manifest_path = os.path.join(out_dir, "changes.json")
        add_recent_file(manifest_path)
        write_to_log(f'Saved session to "{manifest_path}".')

    build_script = os.path.join(base_dir, "build_material_library.py")
    if changed_preview_cats and os.path.isfile(build_script):
        run_blender_tasks(
            [(
                "Updating previews",
                ["blender", "--factory-startup", "-b", "--python", build_script, "--", "--previews", out_dir],
                ("previews", "preview")
            )],
            len(changed_preview_cats),
            finalize_commit
        )
    else:
        finalize_commit()


def save_as_library(title="Save Directory"):
    out_dir = ask_directory_dialog(title if isinstance(title, str) else "Save Directory")
    if not out_dir:
        return
    if perform_save(out_dir, create_subdir=True):
        save_library()


def copy_library_assets(src_dir, dst_dir, overwrite=True):
    if not src_dir or not os.path.isdir(src_dir):
        return
    for filename in sorted(os.listdir(src_dir)):
        if filename.endswith(".blend") or filename == "blender_assets.cats.txt":
            src_file = os.path.join(src_dir, filename)
            dst_file = os.path.join(dst_dir, filename)
            if os.path.isfile(src_file) and (overwrite or not os.path.isfile(dst_file)):
                shutil.copy2(src_file, dst_file)


def perform_save(out_dir, create_subdir=True):
    if not out_dir:
        return False

    if create_subdir:
        target_out_dir = (
            out_dir
            if os.path.basename(os.path.normpath(out_dir)) == "uber-shader-material-library"
            else os.path.join(out_dir, "uber-shader-material-library")
        )
    else:
        target_out_dir = out_dir

    if is_source_dir(out_dir) or is_source_dir(target_out_dir):
        write_to_log("You cannot select the source directory!")
        return False

    scaffold_dirs = (
        "rprmaterials",
        os.path.join("rprmaterials", "Emissive_CoolLight"),
        os.path.join("rprmaterials", "Emissive_Fluorescent_Magenta"),
        os.path.join("rprmaterials", "Maps"),
        os.path.join("rprmaterials", "Previews"),
    )
    for rel_dir in scaffold_dirs:
        os.makedirs(os.path.join(target_out_dir, rel_dir), exist_ok=True)

    copy_library_assets(current_target_dir, target_out_dir, overwrite=False)

    old_out_dir = output_var.get()
    if old_out_dir and os.path.isdir(old_out_dir) and os.path.abspath(old_out_dir) != os.path.abspath(target_out_dir):
        old_manifest_file = os.path.join(old_out_dir, "changes.json")
        new_manifest_file = os.path.join(target_out_dir, "changes.json")
        if os.path.isfile(old_manifest_file) and not os.path.isfile(new_manifest_file):
            shutil.copy2(old_manifest_file, new_manifest_file)
        copy_library_assets(old_out_dir, target_out_dir, overwrite=True)
        old_rpr = os.path.join(old_out_dir, "rprmaterials")
        new_rpr = os.path.join(target_out_dir, "rprmaterials")
        if os.path.isdir(old_rpr):
            shutil.copytree(old_rpr, new_rpr, dirs_exist_ok=True)

    image_cache.clear()
    output_var.set(target_out_dir)
    return True


def load_output_manifest(target=None):
    output_manifest.clear()
    if target and os.path.isfile(target):
        path = target
        target_out_dir = os.path.dirname(os.path.abspath(target))
    else:
        target_out_dir = target or output_var.get()
        path = os.path.join(target_out_dir, "changes.json") if target_out_dir else None
    if not target_out_dir or not os.path.isdir(target_out_dir):
        return
    if path and os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    output_manifest.update(data)
        except Exception:
            pass
    else:
        save_output_manifest(target_out_dir)


def append_log(text):
    log_output.configure(state="normal")
    if log_output.index("end-1c") != "1.0" and log_output.get("end-2c") != "\n":
        log_output.insert(END, "\n")
    log_output.insert(END, text)
    log_output.see(END)
    log_output.configure(state="disabled")


def write_to_log(msg, info_msg=None):
    global info_clear_job
    append_log(f"{str(msg)}\n")

    if not is_debug_mode():
        if info_clear_job is not None:
            try:
                root.after_cancel(info_clear_job)
            except Exception:
                pass
        text = str(info_msg if info_msg is not None else msg)
        info_var.set(f"{text[:64]}..." if len(text) > 64 else text)
        info.configure(style="Info.TLabel")

        def clear_info():
            global info_clear_job
            info_clear_job = None
            if not is_debug_mode():
                info_var.set("")
                info.configure(style="TLabel")

        info_clear_job = root.after(5000, clear_info)


def toggle_log(event=None):
    if log.grid_info():
        log.grid_remove()
    else:
        log.grid()


def save_log():
    path = filedialog.asksaveasfilename(
        title="Save Log",
        initialdir=home_dir,
        defaultextension=".txt",
        filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")]
    )
    if path:
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(log_output.get("1.0", "end-1c"))
        except Exception:
            pass


def clear_log():
    log_output.configure(state="normal")
    log_output.delete("1.0", END)
    log_output.configure(state="disabled")


def is_debug_mode(app_root=None):
    target_root = app_root or globals().get("root")
    if target_root is None:
        return False
    try:
        return str(target_root.getvar("debug")) == "1"
    except Exception:
        return False


def load_debug_config(app_root, target_dir):
    if app_root is None or not isinstance(target_dir, str):
        return
    is_debug = is_debug_mode(app_root)

    if is_debug:
        if not log.grid_info():
            log.grid()
        info_var.set("Debug")
        info.configure(style="Debug.TLabel")

    if is_debug:
        source_tcl_script(app_root, target_dir, "debug.tcl")


root = Tk()
root.title("Material Library Workbench")
root.option_add('*tearOff', FALSE)
root.resizable(False, False)
root.columnconfigure(0, weight=1)
root.rowconfigure(0, weight=1)

root.createcommand("toggle_log", toggle_log)
root.createcommand("clear_log", clear_log)
root.createcommand("write_to_log", write_to_log)
root.createcommand("open_help_url", webbrowser.open)
root.createcommand("perform_find", perform_find)

load_tcl_config(root, base_dir)
load_style_config(root, base_dir)
load_help_config(root, base_dir)
load_find_config(root, base_dir)

category_var = StringVar()
images_in_material_var = StringVar(value="Images in material: 0")
info_var = StringVar()
materials_in_category_var = StringVar(value="Materials in category: 0")
operation_var = StringVar()
output_var = StringVar()

mainframe = ttk.Frame(root)
mainframe.grid(column=0, row=0, sticky=(N, W, E, S))
mainframe.columnconfigure(1, weight=1, uniform="preview_cols")
mainframe.columnconfigure(2, weight=1, uniform="preview_cols")

material = ttk.Labelframe(mainframe, text="Material")
material.grid(column=0, row=1, rowspan=2, sticky=(N, S, E, W))
material.rowconfigure(0, weight=1)
material.columnconfigure(0, weight=1)

tool_strip = ttk.Frame(mainframe)
tool_strip.grid(column=0, row=3, columnspan=4, sticky=(N, S, E, W))
tool_strip.columnconfigure(1, weight=1)
tool_strip.rowconfigure(0, weight=1)

log = ttk.Labelframe(mainframe, text=" Log ")
log.grid(column=0, row=4, columnspan=4, sticky=(N, S, E, W))
log.columnconfigure(0, weight=1)
log.rowconfigure(0, weight=1)
log.grid_remove()

log_tool_strip = ttk.Frame(log)
log_tool_strip.grid(column=0, row=1, columnspan=2, sticky=(W, E))

menubar = Menu(root)
file_menu = Menu(menubar)
search_menu = Menu(menubar)
help_menu = Menu(menubar)
image_context_menu = Menu(root, tearoff=0)
recent_menu = Menu(file_menu, tearoff=0)
menubar.add_cascade(menu=file_menu, label="File")
menubar.add_cascade(menu=search_menu, label="Search")
menubar.add_cascade(menu=help_menu, label="Help")
file_menu.add_command(label='New', accelerator='Ctrl+N', underline=0, command=new_session)
file_menu.add_command(label='Open...', accelerator='Ctrl+O', underline=0, command=open_session)
file_menu.add_command(label='Save', accelerator='Ctrl+S', underline=0, command=save_library)
file_menu.add_command(label='Save As...', accelerator='Ctrl+Shift+S', underline=5, command=save_as_library)
file_menu.add_separator()
file_menu.add_cascade(label='Most Recently Used', menu=recent_menu, underline=0)
file_menu.add_separator()
file_menu.add_command(label='Import Library', command=import_library)
search_menu.add_command(label='Find', accelerator='Ctrl+F', command=show_find)
search_menu.add_command(label='Find Next', accelerator='Ctrl+G', command=find_next)
search_menu.add_command(label='Find Previous', accelerator='Shift+Ctrl+G', command=find_prev)
help_menu.add_command(label='Manual', accelerator='F1', command=show_help)
root['menu'] = menubar
update_recent_menu()

category = ttk.Combobox(mainframe, textvariable=category_var)
category.state(["readonly"])
category.grid(column=0, row=0, sticky=(W, E))

materials_in_category = ttk.Label(mainframe, textvariable=materials_in_category_var, anchor="w", relief="sunken")
materials_in_category.grid(column=1, row=0, sticky=(W, E))
images_in_material = ttk.Label(mainframe, textvariable=images_in_material_var, anchor="w", relief="sunken")
images_in_material.grid(column=2, row=0, sticky=(W, E))

material_list = Listbox(material, exportselection=False)
material_list.grid(column=0, row=0, sticky=(N, S, E, W))

content_canvas = Canvas(mainframe, width=get_canvas_width(), height=2 * get_image_height(), yscrollincrement=32)
content_scroll = ttk.Scrollbar(mainframe, orient=VERTICAL, command=content_canvas.yview)
content_canvas.configure(yscrollcommand=content_scroll.set)
content_canvas.grid(column=1, row=1, rowspan=2, columnspan=2, sticky=(N, S, E, W))
content_scroll.grid(column=3, row=1, rowspan=2, sticky=(N, S))

version = ttk.Label(tool_strip, text=" Version 1.0.0 ", state="disabled")
version.grid(column=0, row=0, sticky=W)
info = ttk.Label(tool_strip, anchor="center", state="disabled", textvariable=info_var)
info.grid(column=1, row=0)
operation = ttk.Label(tool_strip, anchor="center", state="disabled", textvariable=operation_var)
operation.grid(column=2, row=0, sticky=E)
progress = ttk.Progressbar(tool_strip, orient=HORIZONTAL, length=200, mode='determinate')
progress.grid(column=3, row=0, sticky=W)
progress.grid_remove()
copyright_notice = ttk.Label(tool_strip, text=" Copyright © 2026 EvokeMadness ", state="disabled")
copyright_notice.grid(column=4, row=0, sticky=E)

log_output = Text(log, height=8, state="disabled")
log_output.grid(column=0, row=0, sticky=(N, S, E, W))
log_scroll = ttk.Scrollbar(log, orient=VERTICAL, command=log_output.yview)
log_scroll.grid(column=1, row=0, sticky=(N, S))
log_output['yscrollcommand'] = log_scroll.set

log_save = ttk.Button(log_tool_strip, text=" Save ", command=save_log)
log_save.grid(column=0, row=0, sticky=W)
log_clear = ttk.Button(log_tool_strip, text=" Clear ", command=clear_log)
log_clear.grid(column=1, row=0, sticky=W)

for child in (tool_strip, version, info, operation, copyright_notice):
    child.bind("<Button-1>", toggle_log)

root.bind("<Control-n>", new_session)
root.bind("<Control-N>", new_session)
root.bind("<Control-o>", open_session)
root.bind("<Control-O>", open_session)
root.bind("<Control-s>", save_library)
root.bind("<Control-S>", save_as_library)
root.bind("<Control-Shift-s>", save_as_library)
root.bind("<Control-Shift-S>", save_as_library)
root.bind("<Control-f>", show_find)
root.bind("<Control-F>", show_find)
root.bind("<Control-g>", find_next)
root.bind("<Control-G>", find_prev)
root.bind("<Control-Shift-g>", find_prev)
root.bind("<Control-Shift-G>", find_prev)
root.bind("<F1>", show_help)
category.bind("<<ComboboxSelected>>", on_category_select)
content_canvas.bind("<Enter>", bind_mousewheel)
content_canvas.bind("<Leave>", unbind_mousewheel)
material_list.bind("<<ListboxSelect>>", on_material_select)

populate_categories(base_dir)
if not category.get():
    update_canvas_display([], [])

load_debug_config(root, base_dir)

root.mainloop()