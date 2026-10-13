proc build_log {parent} {
    global log_frame log_output log_scroll log_tool_strip

    set log_frame [ttk::labelframe $parent.log_frame -text " Log "]
    grid $log_frame -column 0 -row 4 -columnspan 4 -sticky nsew
    grid columnconfigure $log_frame 0 -weight 1
    grid rowconfigure $log_frame 0 -weight 1
    grid remove $log_frame

    set log_output [text $log_frame.output -height 8 -state disabled]
    grid $log_output -column 0 -row 0 -sticky nsew

    set log_scroll [ttk::scrollbar $log_frame.scroll -orient vertical -command [list $log_output yview]]
    grid $log_scroll -column 1 -row 0 -sticky ns
    $log_output configure -yscrollcommand [list $log_scroll set]

    set log_tool_strip [ttk::frame $log_frame.tool_strip]
    grid $log_tool_strip -column 0 -row 1 -columnspan 2 -sticky we

    ttk::button $log_tool_strip.save -text " Save " -command save_log
    grid $log_tool_strip.save -column 0 -row 0 -sticky w

    ttk::button $log_tool_strip.clear -text " Clear " -command clear_log
    grid $log_tool_strip.clear -column 1 -row 0 -sticky w
}

proc toggle_log {} {
    global log_frame
    if {[info exists log_frame] && [winfo exists $log_frame]} {
        if {[llength [grid info $log_frame]] > 0} {
            grid remove $log_frame
        } else {
            grid $log_frame -column 0 -row 4 -columnspan 4 -sticky nsew
        }
    }
}

proc show_log {} {
    global log_frame
    if {[info exists log_frame] && [winfo exists $log_frame]} {
        grid $log_frame -column 0 -row 4 -columnspan 4 -sticky nsew
    }
}

proc clear_log {} {
    global log_output
    if {[info exists log_output] && [winfo exists $log_output]} {
        $log_output configure -state normal
        $log_output delete 1.0 end
        $log_output configure -state disabled
    }
}

proc append_log {msg} {
    global log_output
    if {[info exists log_output] && [winfo exists $log_output]} {
        $log_output configure -state normal
        if {[$log_output index "end-1c"] ne "1.0" && [$log_output get "end-2c"] ne "\n"} {
            $log_output insert end "\n"
        }
        $log_output insert end $msg
        $log_output see end
        $log_output configure -state disabled
    }
}

proc get_log_text {} {
    global log_output
    if {[info exists log_output] && [winfo exists $log_output]} {
        return [$log_output get 1.0 "end-1c"]
    }
    return ""
}

