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
SOURCE_LIB_DIR = os.path.expanduser("~/Documents/Radeon ProRender/Material Library")
XML_DIR = os.path.join(SOURCE_LIB_DIR, "Xml")
SOURCE_MAPS_DIR = os.path.join(SOURCE_LIB_DIR, "Maps")
LOCAL_MAPS_DIR = os.path.join(BASE_DIR, "rprmaterials", "Maps")
PREVIEWS_DIR = os.path.join(BASE_DIR, "rprmaterials", "Previews")
IGNORED_FILES = {"radeon-prorender-material-library.blend"}

DEFAULT_COLOR = (0.8, 0.8, 0.8)
NODE_POS = (-400, 300)

def parse_floats(val_str):
    try:
        return [float(x.strip()) for x in val_str.split(",")]
    except Exception:
        return None

def find_image_from_connection(tree, conn_name):
    if not conn_name:
        return None
    nodes = {n.get("name"): n for n in tree.findall(".//node") if n.get("name")}
    curr, visited = conn_name, set()
    while curr in nodes and curr not in visited:
        visited.add(curr)
        n = nodes[curr]
        if n.get("type") == "INPUT_TEXTURE":
            for p in n.findall("param"):
                if p.get("name") == "path" and p.get("value"):
                    return os.path.basename(p.get("value").replace("\\", "/"))
        curr = next((
            p.get("value") for p in n.findall("param")
            if p.get("type") == "connection" and p.get("name") not in ("uv", "normal", "bumpscale")
        ), None)
    return None

def extract_material_properties(xml_file, cat_name):
    tree = ET.parse(xml_file)
    mat_name = os.path.splitext(os.path.basename(xml_file))[0]

    # Emissive shaders (closure BLEND with EMISSIVE child nodes)
    if em_nodes := tree.findall(".//node[@type='EMISSIVE']"):
        colors = [
            parse_floats(p.get("value", ""))
            for en in em_nodes
            if (p := en.find("./param[@name='color']")) is not None
        ]
        c = next((v for v in colors if v and not (v[0] == v[1] == v[2])), next((v for v in colors if v), DEFAULT_COLOR))
        return (*c[:3], 1.0), 0.0, 0.2, None

    uber = tree.find(".//node[@type='UBER']")
    uber_params = uber.findall("param") if uber is not None else []
    params = {p.get("name"): p.get("value") for p in uber_params if p.get("name") and p.get("value")}

    refl_mode = params.get("reflection.mode", "1")
    diff_raw = parse_floats(params.get("diffuse.color", ""))
    refl_raw = parse_floats(params.get("reflection.color", ""))
    refr_raw = parse_floats(params.get("refraction.color", ""))
    refr_weight = parse_floats(params.get("refraction.weight", ""))
    refl_rough = parse_floats(params.get("reflection.roughness", ""))
    refr_rough = parse_floats(params.get("refraction.roughness", ""))

    is_pure_metal = cat_name in ("metals", "extendedmetals", "preciousmetals") or mat_name in ("Roofing_CorrugatedIron", "Mirror", "Generic")

    # Viewport Alpha
    is_refractive = not is_pure_metal and bool(refr_weight and refr_weight[0] > 0.05)
    alpha = max(0.1, 1.0 - refr_weight[0] * 0.75) if is_refractive else 1.0

    # Viewport Color
    if is_refractive and refr_raw and len(refr_raw) >= 3:
        color = (*refr_raw[:3], alpha)
    else:
        primary, fallback = (refl_raw, diff_raw) if refl_mode == "2" else (diff_raw, refl_raw)
        c = primary or fallback or DEFAULT_COLOR
        color = (*c[:3], 1.0 if refl_mode == "2" else alpha)

    # Viewport Roughness
    r = (refr_rough if is_refractive else None) or refl_rough
    roughness = r[0] if r else 0.4

    # Viewport Metallic
    if is_pure_metal:
        metallic = 1.0
    elif cat_name == "metallic_paint" or (cat_name == "carpaints" and any(k in mat_name.lower() for k in ("metallic", "pearl", "candy", "flakes"))):
        metallic = 0.8
    else:
        metallic = 0.0

    # Diffuse Image Texture
    diff_conn = next((
        p.get("value") for p in uber_params
        if p.get("type") == "connection" and p.get("name") in ("diffuse.color", "reflection.color", "refraction.color")
    ), None)
    diff_img = find_image_from_connection(tree, diff_conn)

    return color, metallic, roughness, diff_img

def load_or_get_image(img_name):
    if not img_name:
        return None
    if img := bpy.data.images.get(img_name):
        return img
    for maps_dir in (LOCAL_MAPS_DIR, SOURCE_MAPS_DIR):
        if os.path.isfile(p := os.path.join(maps_dir, img_name)):
            return bpy.data.images.load(p, check_existing=True)
    return None

def setup_viewport_texture(mat, img_name):
    if not img_name or not (img := load_or_get_image(img_name)):
        return False
    mat.use_nodes = True
    node = mat.node_tree.nodes.get("Viewport Texture") or mat.node_tree.nodes.new(type="ShaderNodeTexImage")
    node.name = "Viewport Texture"
    node.label = "Viewport Texture"
    node.location = NODE_POS
    node.image = img
    mat.node_tree.nodes.active = node
    return True

def reset_viewport_shading():
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                space = area.spaces.active
                space.shading.type = "SOLID"
                space.shading.color_type = "TEXTURE"

def build_material_library():
    if not os.path.isdir(XML_DIR):
        print("Material library not found in Documents folder.")
        return

    xml_cache = {}
    for root, _, files in os.walk(XML_DIR):
        for f in files:
            if f.lower().endswith(".xml"):
                xml_cache[os.path.splitext(f)[0].lower()] = os.path.join(root, f)

    blend_files = sorted([
        f for f in glob.glob(os.path.join(BASE_DIR, "*.blend"))
        if os.path.basename(f) not in IGNORED_FILES
    ])

    mat_count = 0
    textured_count = 0
    preview_count = 0

    for blend_file in blend_files:
        cat_name = os.path.splitext(os.path.basename(blend_file))[0]
        bpy.ops.wm.open_mainfile(filepath=blend_file)

        # 1. Purge scene objects, meshes, and texts
        for coll in (bpy.data.objects, bpy.data.meshes, bpy.data.texts):
            for item in list(coll):
                coll.remove(item)

        # 2. Index category preview thumbnails
        cat_previews_dir = os.path.join(PREVIEWS_DIR, cat_name)
        preview_cache = (
            {f.lower(): f for f in os.listdir(cat_previews_dir) if f.lower().endswith(".jpg")}
            if os.path.isdir(cat_previews_dir)
            else {}
        )

        # 3. Update materials
        for mat in bpy.data.materials:
            if not mat or mat.name in ("Dots Stroke", ""):
                continue

            und = mat.name.replace(" ", "_").lower()
            base = mat.name.lower()

            # Load custom preview thumbnail
            if preview_cache and (prev_file := preview_cache.get(f"{und}.jpg") or preview_cache.get(f"{base}.jpg")):
                try:
                    with bpy.context.temp_override(id=mat):
                        bpy.ops.ed.lib_id_load_custom_preview(filepath=os.path.join(cat_previews_dir, prev_file))
                        preview_count += 1
                except Exception:
                    pass

            # Update viewport display & texture
            if matched_xml := (xml_cache.get(und) or xml_cache.get(base)):
                color, metallic, roughness, diff_img = extract_material_properties(matched_xml, cat_name)
                mat.diffuse_color = color
                mat.metallic = metallic
                mat.roughness = roughness
                mat_count += 1
                if setup_viewport_texture(mat, diff_img):
                    textured_count += 1

        # 4. Viewport display, relative paths, orphan purge, and compression
        reset_viewport_shading()
        bpy.ops.file.make_paths_relative()
        bpy.ops.outliner.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)
        bpy.ops.wm.save_mainfile(compress=True)

        try:
            os.remove(blend_file + "1")
        except OSError:
            pass

    print(f"Materials updated: {mat_count} ({textured_count} textured). Previews assigned: {preview_count}.")

if __name__ == "__main__":
    if bpy:
        build_material_library()
    else:
        subprocess.run(["blender", "--factory-startup", "-b", "--python", __file__])
