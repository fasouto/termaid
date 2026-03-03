Output demo/termaid-demo.gif

Set Shell "bash"
Set FontSize 14
Set Width 800
Set Height 500
Set Padding 15
Set TypingSpeed 32ms
Set Theme { "name": "Catppuccin Mocha", "black": "#1e1e2e", "red": "#f38ba8", "green": "#a6e3a1", "yellow": "#f9e2af", "blue": "#89b4fa", "magenta": "#cba6f7", "cyan": "#94e2d5", "white": "#cdd6f4", "brightBlack": "#585b70", "brightRed": "#f38ba8", "brightGreen": "#a6e3a1", "brightYellow": "#f9e2af", "brightBlue": "#89b4fa", "brightMagenta": "#cba6f7", "brightCyan": "#94e2d5", "brightWhite": "#a6adc8", "background": "#1e1e2e", "foreground": "#cdd6f4", "selection": "#585b70", "cursor": "#f5e0dc" }

Env "PS1" "$ "
Env "VIRTUAL_ENV" ""

Hide
Type "cd demo"
Enter
Sleep 500ms
Ctrl+L
Show

# 1. Sequence diagram — API call flow
Type "termmaid sequence.mmd --theme phosphor"
Enter
Sleep 4s

# 2. Flowchart — branching decision tree with diamonds and labels
Ctrl+L
Type "termmaid flowchart.mmd --theme terra"
Enter
Sleep 4s

# 3. Git graph — branches, merges, commits
Ctrl+L
Type "termmaid gitgraph.mmd --theme amber"
Enter
Sleep 4s

# 4. One-liner hook — pipe-friendly with branching
Ctrl+L
Type "echo 'graph LR; A[Request] --> B{Valid?}; B -->|Yes| C[Process]; B -->|No| D[Error]' | termmaid --color"
Enter
Sleep 4s
