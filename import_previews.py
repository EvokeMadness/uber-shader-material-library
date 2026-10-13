#!/usr/bin/env python3
import glob
import os
import shutil
import subprocess
import sys

try:
    import bpy
except ImportError:
    bpy = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCE_LIB_DIR = os.path.expanduser("~/Documents/Radeon ProRender/Material Library")
XML_DIR = os.path.join(SOURCE_LIB_DIR, "Xml")
IGNORED_FILES = {"radeon-prorender-material-library.blend"}

def categorize_previews(target_dir=None):
    print("Importing previews", flush=True)
    if not os.path.isdir(XML_DIR):
        print("Material library not found in Documents folder.", flush=True)
        return

    print(f"Found installed material library at '{SOURCE_LIB_DIR}'", flush=True)
    base_dir = os.path.abspath(target_dir) if target_dir else BASE_DIR
    previews_dir = os.path.join(base_dir, "rprmaterials", "Previews")

    # 1. Index all XML preview images
    xml_cache = {}
    for root, _, files in os.walk(XML_DIR):
        for f in files:
            if f.lower().endswith((".jpg", ".png", ".jpeg")):
                xml_cache[f.lower()] = os.path.join(root, f)

    # 2. Copy previews directly into category folders based on .blend files
    blend_files = sorted([
        f for f in glob.glob(os.path.join(base_dir, "*.blend"))
        if os.path.basename(f) not in IGNORED_FILES
    ])

    total_previews = 0
    for blend_file in blend_files:
        cat_name = os.path.splitext(os.path.basename(blend_file))[0]
        cat_dir = os.path.join(previews_dir, cat_name)
        os.makedirs(cat_dir, exist_ok=True)

        with bpy.data.libraries.load(blend_file) as (data_from, _):
            mat_names = sorted([m for m in data_from.materials if m and m not in ("Dots Stroke", "")])

        cat_count = 0
        for mat in mat_names:
            und = mat.replace(" ", "_").lower()
            base = mat.lower()
            matched_key = next(
                (k for k in (f"{und}.jpg", f"{base}.jpg", f"{und}.png", f"{base}.png") if k in xml_cache),
                None
            )

            if matched_key:
                src_path = xml_cache[matched_key]
                dst_path = os.path.join(cat_dir, os.path.basename(src_path))

                if not os.path.exists(dst_path) or os.path.getsize(src_path) != os.path.getsize(dst_path):
                    shutil.copy2(src_path, dst_path)
                cat_count += 1

        total_previews += cat_count
        print(f"{cat_name}: {cat_count} previews", flush=True)

    print(f"Total Previews: {total_previews}. Saved to '{previews_dir}'", flush=True)

if __name__ == "__main__":
    target = None
    if "--" in sys.argv:
        idx = sys.argv.index("--")
        if idx + 1 < len(sys.argv):
            target = sys.argv[idx + 1]
    elif len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        target = sys.argv[1]

    if bpy:
        categorize_previews(target)
    else:
        cmd = ["blender", "--factory-startup", "-b", "--python", __file__]
        if target:
            cmd.extend(["--", target])
        subprocess.run(cmd)
