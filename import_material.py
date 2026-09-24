import bpy
import re
from functools import partial

bpy.app.handlers.depsgraph_update_post[:] = [
    h for h in bpy.app.handlers.depsgraph_update_post if getattr(h, "__name__", None) != "on_slot_add"
]

DUPLICATE_NAME_PATTERN = re.compile(r"^(.*?)\.\d{3}$")
pending = set()

def merge_image_base_names():
    for img in sorted(bpy.data.images, key=lambda x: x.name):
        match = DUPLICATE_NAME_PATTERN.match(img.name)
        if not match:
            continue
        base_name = match.group(1)
        if base_name in bpy.data.images:
            base_img = bpy.data.images[base_name]
            if base_img != img:
                img.user_remap(base_img)
                bpy.data.images.remove(img)
        else:
            img.name = base_name

def cleanup(obj_name):
    obj = bpy.data.objects.get(obj_name)
    if obj:
        for slot in obj.material_slots:
            if slot.material and not slot.material.asset_data:
                slot.material.asset_mark()
        if hasattr(obj.data, "materials"):
            obj.data.materials.clear()

    merge_image_base_names()

    pending.discard(obj_name)

def on_slot_add(scene, depsgraph):
    obj = bpy.context.active_object
    if not obj or not hasattr(obj, "material_slots") or not any(slot.material for slot in obj.material_slots):
        return

    if obj.name not in pending:
        pending.add(obj.name)
        bpy.app.timers.register(partial(cleanup, obj.name), first_interval=1.0)

bpy.app.handlers.depsgraph_update_post.append(on_slot_add)
