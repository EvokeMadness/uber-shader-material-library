#!/usr/bin/env python3
import glob
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict

try:
    import bpy
except ImportError:
    bpy = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_MAPS_DIR = os.path.join(BASE_DIR, "rprmaterials", "Maps")
SOURCE_MAPS_DIR = os.path.expanduser("~/Documents/Radeon ProRender/Material Library/Maps")
SOURCE_XML_DIR = os.path.join(os.path.dirname(SOURCE_MAPS_DIR), "Xml")
MANIFESTS_DIR = os.path.join(BASE_DIR, "manifests")
IGNORED_FILES = {"radeon-prorender-material-library.blend"}

def get_image_resolution(img_name, cache, local_maps_dir=LOCAL_MAPS_DIR):
    if img_name in cache:
        return cache[img_name]
    local_map = os.path.join(local_maps_dir, img_name)
    source_map = os.path.join(SOURCE_MAPS_DIR, img_name)
    path = local_map if os.path.isfile(local_map) else source_map
    res = "Unknown"
    if os.path.isfile(path):
        try:
            img = bpy.data.images.load(path, check_existing=True)
            res = f"{img.size[0]} × {img.size[1]} pixels"
            bpy.data.images.remove(img)
        except Exception:
            pass
    cache[img_name] = res
    return res

def get_material_images(mat_name, xml_folders, cat_imgs):
    und = mat_name.replace(" ", "_").lower()
    base = mat_name.lower()
    folder = xml_folders.get(und) or xml_folders.get(base)
    if not folder:
        return []
    xml_files = glob.glob(os.path.join(folder, "*.xml"))
    if not xml_files:
        return []
    try:
        tree = ET.parse(xml_files[0])
        imgs = [
            os.path.basename(p.attrib["value"].replace("\\", "/"))
            for node in tree.findall(".//node[@type='INPUT_TEXTURE']")
            for p in [node.find("param[@name='path']")]
            if p is not None and "value" in p.attrib and os.path.basename(p.attrib["value"].replace("\\", "/")) in cat_imgs
        ]
        return sorted(set(imgs))
    except Exception:
        return []

def generate_manifest(target_dir=None):
    print("Generating manifests", flush=True)
    base_dir = os.path.abspath(target_dir) if target_dir else BASE_DIR
    local_maps_dir = os.path.join(base_dir, "rprmaterials", "Maps")
    manifests_dir = os.path.join(base_dir, "manifests")

    blend_files = sorted([
        f for f in glob.glob(os.path.join(base_dir, "*.blend"))
        if os.path.basename(f) not in IGNORED_FILES
    ])

    if not blend_files:
        return

    os.makedirs(manifests_dir, exist_ok=True)

    xml_folders = {
        f.replace(" ", "_").lower(): os.path.join(SOURCE_XML_DIR, f)
        for f in os.listdir(SOURCE_XML_DIR)
    } if os.path.isdir(SOURCE_XML_DIR) else {}

    mat_count = 0
    res_cache = {}
    categories_index = {}

    for blend_file in blend_files:
        blend_filename = os.path.basename(blend_file)
        cat_name = os.path.splitext(blend_filename)[0]

        with bpy.data.libraries.load(blend_file) as (data_from, _):
            raw_mats = sorted([m for m in data_from.materials if m and m not in ("Dots Stroke", "")])
            raw_imgs = sorted([os.path.basename(i) for i in data_from.images if i and i not in ("Render Result", "Viewer Node")])

        mat_count += len(raw_mats)
        print(f"{cat_name}: {len(raw_mats)} materials", flush=True)

        cat_imgs_set = set(raw_imgs)
        cat_materials = {}
        img_to_mats = defaultdict(list)

        # 1. Materials
        for mat in raw_mats:
            mat_imgs = get_material_images(mat, xml_folders, cat_imgs_set)
            cat_materials[mat] = {
                "preview": f"rprmaterials/Previews/{cat_name}/{mat.replace(' ', '_')}.jpg",
                "images": mat_imgs
            }
            for img_name in mat_imgs:
                img_to_mats[img_name].append(mat)

        # 2. Images
        cat_images = {}
        for img_name in raw_imgs:
            cat_images[img_name] = {
                "resolution": get_image_resolution(img_name, res_cache, local_maps_dir),
                "relative_path": f"rprmaterials/Maps/{img_name}",
                "source_path": os.path.join(SOURCE_MAPS_DIR, img_name),
                "materials": sorted(img_to_mats.get(img_name, []))
            }

        # 3. Category manifest
        cat_manifest = {
            "category": cat_name,
            "blend_file": blend_filename,
            "materials": cat_materials,
            "images": cat_images
        }

        cat_file = os.path.join(manifests_dir, f"{cat_name}.json")
        with open(cat_file, "w", encoding="utf-8") as f:
            json.dump(cat_manifest, f, indent=2)

        categories_index[cat_name] = {
            "blend_file": blend_filename,
            "materials_count": len(raw_mats),
            "images_count": len(raw_imgs)
        }

    # 4. Library index manifest
    index_data = {
        "library": "Uber Shader Material Library",
        "total_materials": mat_count,
        "total_categories": len(blend_files),
        "categories": categories_index
    }

    index_file = os.path.join(manifests_dir, "index.json")
    with open(index_file, "w", encoding="utf-8") as f:
        json.dump(index_data, f, indent=2)

    print(f"Total Materials: {mat_count}. Saved {len(blend_files)} category manifests to '{manifests_dir}'", flush=True)

if __name__ == "__main__":
    target = None
    if "--" in sys.argv:
        idx = sys.argv.index("--")
        if idx + 1 < len(sys.argv):
            target = sys.argv[idx + 1]
    elif len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        target = sys.argv[1]

    if bpy:
        generate_manifest(target)
    else:
        cmd = ["blender", "--factory-startup", "-b", "--python", __file__]
        if target:
            cmd.extend(["--", target])
        subprocess.run(cmd)
