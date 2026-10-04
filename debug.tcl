# debug.tcl

if {[info exists debug_images] && $debug_images == 1} {
    proc debug_images {{num_previews 1} {num_images 5}} {
        set_preview_image_counts $num_previews $num_images
    }

    debug_images 1 5
}
