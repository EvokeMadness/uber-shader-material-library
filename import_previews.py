#!/usr/bin/env python3
import glob
import os
import shutil
import subprocess

try:
    import bpy
except ImportError:
    bpy = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCE_LIB_DIR = os.path.expanduser("~/Documents/Radeon ProRender/Material Library")
XML_DIR = os.path.join(SOURCE_LIB_DIR, "Xml")
PREVIEWS_DIR = os.path.join(BASE_DIR, "rprmaterials", "Previews")
IGNORED_FILES = {"radeon-prorender-material-library.blend"}

def categorize_previews():
    if not os.path.isdir(XML_DIR):
        print("Material library not found in Documents folder.")
        return

    print(f"Found installed material library at '{SOURCE_LIB_DIR}'")

    # 1. Index all XML preview images
    xml_cache = {}
    for root, _, files in os.walk(XML_DIR):
        for f in files:
            if f.lower().endswith((".jpg", ".png", ".jpeg")):
                xml_cache[f.lower()] = os.path.join(root, f)

    # 2. Copy previews directly into category folders based on .blend files
    blend_files = sorted([
        f for f in glob.glob(os.path.join(BASE_DIR, "*.blend"))
        if os.path.basename(f) not in IGNORED_FILES
    ])

    for blend_file in blend_files:
        cat_name = os.path.splitext(os.path.basename(blend_file))[0]
        cat_dir = os.path.join(PREVIEWS_DIR, cat_name)
        os.makedirs(cat_dir, exist_ok=True)

        with bpy.data.libraries.load(blend_file) as (data_from, _):
            mat_names = data_from.materials

        for mat in mat_names:
            if not mat or mat in ("Dots Stroke", ""):
                continue

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

if __name__ == "__main__":
    if bpy:
        categorize_previews()
    else:
        subprocess.run(["blender", "--factory-startup", "-b", "--python", __file__])
