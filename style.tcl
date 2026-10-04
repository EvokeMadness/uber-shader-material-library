ttk::style configure Strip.TFrame -background grey
ttk::style configure Strip.TLabel -background grey -foreground white

catch {font create DebugFont {*}[font actual TkDefaultFont] -weight bold}
ttk::style configure Debug.TLabel -foreground red -font DebugFont
ttk::style map Debug.TLabel -foreground {disabled red}
