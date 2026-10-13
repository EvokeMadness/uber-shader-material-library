ttk::style configure Strip.TFrame -background grey
ttk::style configure Strip.TLabel -background grey -foreground white

ttk::style configure Info.TLabel -background #4a6984 -foreground white
ttk::style map Info.TLabel -background {disabled #4a6984} -foreground {disabled white}

catch {font create DebugFont {*}[font actual TkDefaultFont] -weight bold}
ttk::style configure Debug.TLabel -foreground red -font DebugFont
ttk::style map Debug.TLabel -foreground {disabled red}

ttk::style configure Deleted.TLabelframe -background #c74e39
ttk::style configure Deleted.TLabelframe.Label -background #c74e39 -foreground white

ttk::style configure Modified.TLabelframe -background #d18616
ttk::style configure Modified.TLabelframe.Label -background #d18616 -foreground white

ttk::style configure Added.TLabelframe -background #388a34
ttk::style configure Added.TLabelframe.Label -background #388a34 -foreground white

