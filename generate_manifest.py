#!/usr/bin/env python3
import glob
import os
import subprocess
import xml.etree.ElementTree as ET

try:
    import bpy
except ImportError:
    bpy = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_MAPS_DIR = os.path.join(BASE_DIR, "rprmaterials", "Maps")
SOURCE_MAPS_DIR = os.path.expanduser("~/Documents/Radeon ProRender/Material Library/Maps")
MANIFEST_PATH = os.path.join(BASE_DIR, "material_manifest.xml")
IGNORED_FILES = {"radeon-prorender-material-library.blend"}

def get_image_resolution(filepath):
    if not filepath or not os.path.isfile(filepath):
        return "Unknown"
    try:
        img = bpy.data.images.load(filepath, check_existing=True)
        res = f"{img.size[0]}x{img.size[1]}"
        bpy.data.images.remove(img)
        return res
    except Exception:
        return "Unknown"

def generate_manifest():
    blend_files = sorted([
        f for f in glob.glob(os.path.join(BASE_DIR, "*.blend"))
        if os.path.basename(f) not in IGNORED_FILES
    ])

    if not blend_files:
        return

    root = ET.Element("library_manifest")
    root.set("library", "Uber Shader Material Library")
    mat_count = 0

    for blend_file in blend_files:
        blend_filename = os.path.basename(blend_file)
        cat_name = os.path.splitext(blend_filename)[0]

        cat_elem = ET.SubElement(root, "category")
        cat_elem.set("name", cat_name)
        cat_elem.set("blend_file", blend_filename)

        with bpy.data.libraries.load(blend_file) as (data_from, _):
            raw_mats = [m for m in data_from.materials if m and m not in ("Dots Stroke", "")]
            raw_imgs = [i for i in data_from.images if i and i not in ("Render Result", "Viewer Node")]

        mat_count += len(raw_mats)
        print(f"{cat_name}: {len(raw_mats)} materials")

        # 1. Materials
        mats_elem = ET.SubElement(cat_elem, "materials")
        mats_elem.set("count", str(len(raw_mats)))
        for mat in sorted(raw_mats):
            mat_elem = ET.SubElement(mats_elem, "material")
            mat_elem.set("name", mat)
            mat_elem.set("preview", f"rprmaterials/Previews/{cat_name}/{mat.replace(' ', '_')}.jpg")

        # 2. Images
        imgs_elem = ET.SubElement(cat_elem, "images")
        imgs_elem.set("count", str(len(raw_imgs)))
        for img in sorted(raw_imgs):
            img_name = os.path.basename(img)
            local_map = os.path.join(LOCAL_MAPS_DIR, img_name)
            source_map = os.path.join(SOURCE_MAPS_DIR, img_name)
            img_path = local_map if os.path.isfile(local_map) else source_map

            img_elem = ET.SubElement(imgs_elem, "image")
            img_elem.set("name", img_name)
            img_elem.set("resolution", get_image_resolution(img_path))
            ET.SubElement(img_elem, "relative_path").text = f"//rprmaterials/Maps/{img_name}"
            ET.SubElement(img_elem, "source_path").text = source_map

    # 3. Write manifest
    ET.indent(root, space="  ")
    ET.ElementTree(root).write(MANIFEST_PATH, encoding="utf-8", xml_declaration=True)
    print(f"Total Materials: {mat_count}. Saved manifest to '{MANIFEST_PATH}'")

if __name__ == "__main__":
    if bpy:
        generate_manifest()
    else:
        subprocess.run(["blender", "--factory-startup", "-b", "--python", __file__])
