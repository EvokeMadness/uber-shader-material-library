set find_search_text ""
set find_match_word 0
set find_in_images 0

proc close_find {} {
    if {[winfo exists .find_window]} {
        destroy .find_window
    }
}

proc find_next {} {
    global find_search_text find_match_word find_in_images
    if {[winfo exists .find_window.search_entry]} {
        set find_search_text [.find_window.search_entry get]
    }
    if {[info exists find_search_text] && $find_search_text ne ""} {
        set mw [expr {[info exists find_match_word] ? $find_match_word : 0}]
        set img [expr {[info exists find_in_images] ? $find_in_images : 0}]
        perform_find $find_search_text $mw $img 1
    } else {
        show_find
    }
}

proc find_prev {} {
    global find_search_text find_match_word find_in_images
    if {[winfo exists .find_window.search_entry]} {
        set find_search_text [.find_window.search_entry get]
    }
    if {[info exists find_search_text] && $find_search_text ne ""} {
        set mw [expr {[info exists find_match_word] ? $find_match_word : 0}]
        set img [expr {[info exists find_in_images] ? $find_in_images : 0}]
        perform_find $find_search_text $mw $img -1
    } else {
        show_find
    }
}

proc show_find {} {
    if {[winfo exists .find_window]} {
        wm deiconify .find_window
        raise .find_window
        focus -force .find_window.search_entry
        .find_window.search_entry selection range 0 end
        return
    }

    toplevel .find_window
    wm title .find_window "Find"
    wm resizable .find_window 0 0

    label .find_window.search_lbl -text "Search:"
    entry .find_window.search_entry -textvariable find_search_text
    checkbutton .find_window.chk_word -text "Match whole word" -variable find_match_word
    checkbutton .find_window.chk_images -text "Search in material images" -variable find_in_images
    button .find_window.btn_close -text "Close" -command close_find
    button .find_window.btn_prev -text "Previous" -command find_prev
    button .find_window.btn_next -text "Next" -command find_next -default active

    grid .find_window.search_lbl -row 0 -column 0 -sticky w
    grid .find_window.search_entry -row 0 -column 1 -columnspan 2 -sticky ew
    grid .find_window.chk_word -row 1 -column 0 -columnspan 3 -sticky w
    grid .find_window.chk_images -row 2 -column 0 -columnspan 3 -sticky w
    grid .find_window.btn_close -row 3 -column 0 -sticky ew
    grid .find_window.btn_prev -row 3 -column 1 -sticky ew
    grid .find_window.btn_next -row 3 -column 2 -sticky ew

    grid columnconfigure .find_window 0 -weight 1
    grid columnconfigure .find_window 1 -weight 1
    grid columnconfigure .find_window 2 -weight 1

    bind .find_window <Return> find_next
    bind .find_window <KP_Enter> find_next
    bind .find_window <Escape> close_find
    bind .find_window <Control-g> find_next
    bind .find_window <Control-G> find_prev
    bind .find_window <Control-Shift-g> find_prev
    bind .find_window <Control-Shift-G> find_prev

    bind .find_window.search_entry <Return> {find_next; break}
    bind .find_window.search_entry <KP_Enter> {find_next; break}
    bind .find_window.search_entry <Control-g> {find_next; break}
    bind .find_window.search_entry <Control-G> {find_prev; break}
    bind .find_window.search_entry <Control-Shift-g> {find_prev; break}
    bind .find_window.search_entry <Control-Shift-G> {find_prev; break}

    bind .find_window.btn_next <Return> {find_next; break}
    bind .find_window.btn_next <KP_Enter> {find_next; break}
    bind .find_window.btn_prev <Return> {find_prev; break}
    bind .find_window.btn_prev <KP_Enter> {find_prev; break}
    bind .find_window.btn_close <Return> {close_find; break}
    bind .find_window.btn_close <KP_Enter> {close_find; break}

    focus -force .find_window.search_entry
}

