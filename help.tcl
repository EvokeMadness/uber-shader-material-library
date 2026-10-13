if {[llength [info commands open_help_url]] == 0} {
    proc open_help_url {url} {
        catch {exec xdg-open $url &}
    }
}

proc insert_help_inline {w line extra_tags} {
    set idx 0
    set len [string length $line]
    set link_count 0

    while {$idx < $len} {
        if {[regexp -indices -start $idx {(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\))} $line match]} {
            set mstart [lindex $match 0]
            set mend [lindex $match 1]
            if {$mstart > $idx} {
                set plain [string range $line $idx [expr {$mstart - 1}]]
                $w insert end $plain $extra_tags
            }
            set token [string range $line $mstart $mend]
            if {[string match {\*\* *\*\*} $token] || [string match {\*\*?*\*\*} $token]} {
                set inner [string range $token 2 end-2]
                $w insert end $inner [concat $extra_tags bold]
            } elseif {[string match {`*`} $token]} {
                set inner [string range $token 1 end-1]
                $w insert end $inner [concat $extra_tags inline_code]
            } elseif {[string match {\[*\]\(*\)} $token]} {
                if {[regexp {\[([^\]]+)\]\(([^)]+)\)} $token -> link_text link_url]} {
                    set tag_name "link_[incr link_count]_[clock clicks]"
                    $w tag configure $tag_name -foreground #3794ff -underline 1
                    $w tag bind $tag_name <Enter> [list $w configure -cursor hand2]
                    $w tag bind $tag_name <Leave> [list $w configure -cursor ""]
                    $w tag bind $tag_name <Button-1> [list open_help_url $link_url]
                    $w insert end $link_text [concat $extra_tags $tag_name]
                }
            }
            set idx [expr {$mend + 1}]
        } else {
            set rest [string range $line $idx end]
            $w insert end $rest $extra_tags
            break
        }
    }
    $w insert end "\n" $extra_tags
}

proc show_help {} {
    if {[winfo exists .help_window]} {
        wm deiconify .help_window
        raise .help_window
        return
    }

    toplevel .help_window
    wm title .help_window "Material Library Workbench Manual"
    wm geometry .help_window 640x500
    wm minsize .help_window 400 300

    ttk::frame .help_window.f
    pack .help_window.f -fill both -expand 1

    text .help_window.f.text -wrap word -yscrollcommand [list .help_window.f.scroll set] -padx 14 -pady 14 -borderwidth 0 -highlightthickness 0
    ttk::scrollbar .help_window.f.scroll -orient vertical -command [list .help_window.f.text yview]

    pack .help_window.f.scroll -side right -fill y
    pack .help_window.f.text -side left -fill both -expand 1

    catch {font create HelpH1 {*}[font actual TkDefaultFont] -size 15 -weight bold}
    catch {font create HelpH2 {*}[font actual TkDefaultFont] -size 13 -weight bold}
    catch {font create HelpH3 {*}[font actual TkDefaultFont] -size 11 -weight bold}
    catch {font create HelpBold {*}[font actual TkDefaultFont] -weight bold}
    catch {font create HelpCode -family Courier -size 10}

    .help_window.f.text tag configure h1 -font HelpH1 -spacing1 10 -spacing3 6
    .help_window.f.text tag configure h2 -font HelpH2 -spacing1 8 -spacing3 4
    .help_window.f.text tag configure h3 -font HelpH3 -spacing1 6 -spacing3 2
    .help_window.f.text tag configure bold -font HelpBold
    .help_window.f.text tag configure inline_code -font HelpCode -background #e0e0e0
    .help_window.f.text tag configure code_block -font HelpCode -background #f4f4f4 -lmargin1 16 -lmargin2 16
    .help_window.f.text tag configure bullet -lmargin1 16 -lmargin2 32
    .help_window.f.text tag configure quote -lmargin1 16 -lmargin2 16 -foreground #666666

    set help_file [file join [file dirname [info script]] "HELP.md"]
    if {![file exists $help_file]} {
        set help_file "HELP.md"
    }

    if {[file exists $help_file]} {
        set fp [open $help_file r]
        set in_code 0
        while {[gets $fp line] >= 0} {
            if {[string match "```*" $line]} {
                set in_code [expr {!$in_code}]
                continue
            }
            if {$in_code} {
                .help_window.f.text insert end "$line\n" code_block
            } elseif {[regexp {^#\s+(.*)$} $line -> htext]} {
                insert_help_inline .help_window.f.text $htext h1
            } elseif {[regexp {^##\s+(.*)$} $line -> htext]} {
                insert_help_inline .help_window.f.text $htext h2
            } elseif {[regexp {^###\s+(.*)$} $line -> htext]} {
                insert_help_inline .help_window.f.text $htext h3
            } elseif {[regexp {^\s*[-*]\s+(.*)$} $line -> btext]} {
                .help_window.f.text insert end "• " bullet
                insert_help_inline .help_window.f.text $btext bullet
            } elseif {[regexp {^\s*(\d+\.)\s+(.*)$} $line -> num btext]} {
                .help_window.f.text insert end "$num " bullet
                insert_help_inline .help_window.f.text $btext bullet
            } elseif {[regexp {^>\s+(.*)$} $line -> qtext]} {
                insert_help_inline .help_window.f.text $qtext quote
            } else {
                insert_help_inline .help_window.f.text $line ""
            }
        }
        close $fp
    } else {
        .help_window.f.text insert end "HELP.md not found."
    }

    .help_window.f.text configure -state disabled
}

