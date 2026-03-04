Output demo/termaid-demo.gif

Set Shell "bash"
Set FontSize 14
Set Width 830
Set Height 500
Set Padding 15
Set Margin 15
Set MarginFill "#FFFFFF"
Set BorderRadius 10
Set WindowBar Colorful
Set TypingSpeed 32ms
Set Theme { "name": "Catppuccin Mocha", "black": "#1e1e2e", "red": "#f38ba8", "green": "#a6e3a1", "yellow": "#f9e2af", "blue": "#89b4fa", "magenta": "#cba6f7", "cyan": "#94e2d5", "white": "#cdd6f4", "brightBlack": "#585b70", "brightRed": "#f38ba8", "brightGreen": "#a6e3a1", "brightYellow": "#f9e2af", "brightBlue": "#89b4fa", "brightMagenta": "#cba6f7", "brightCyan": "#94e2d5", "brightWhite": "#a6adc8", "background": "#1e1e2e", "foreground": "#cdd6f4", "selection": "#585b70", "cursor": "#f5e0dc" }

Env "PS1" "$ "
Env "VIRTUAL_ENV" ""

Hide
Type "source .venv/bin/activate"
Enter
Sleep 500ms
Type "cd demo"
Enter
Sleep 500ms
Type "export PS1='$ '"
Enter
Sleep 500ms
Ctrl+L
Show

# 1. Sequence diagram — API call flow
Type "termaid sequence.mmd --theme phosphor"
Enter
Sleep 4s

# 2. Flowchart — branching decision tree with diamonds and labels
Type "termaid flowchart.mmd --theme terra"
Enter
Sleep 4s

# 3. Git graph — branches, merges, commits
Type "termaid gitgraph.mmd --theme amber"
Enter
Sleep 4s

# 4. One-liner hook — pipe-friendly with branching
Ctrl+L
Set TypingSpeed 0
Type "# Pipe-friendly: works with echo, cat, curl..."
Enter
Set TypingSpeed 32ms
Sleep 1s
Type "echo 'graph LR; A[Request] --> B{Valid?}; B -->|Yes| C[Process]; B -->|No| D[Error]' | termaid --theme default"
Enter
Sleep 3s

# 5. TUI mode — interactive viewer
Ctrl+L
Set TypingSpeed 0
Type "# Interactive TUI mode"
Enter
Set TypingSpeed 32ms
Sleep 1s
Type "termaid erdiagram.mmd --tui"
Enter
Sleep 4s
Type "q"
Sleep 1s
