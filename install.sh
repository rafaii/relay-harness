#!/bin/bash
# Relay Framework Installation Script
# =====================================
#
# This script sets up the Relay Framework for use from any directory.
#
# Installation options:
#   1. Add to PATH (symlink to ~/bin or /usr/local/bin)
#   2. Set up alias in shell profile
#   3. Use directly from framework directory

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RELAY_SCRIPT="$SCRIPT_DIR/relay"

echo "╔════════════════════════════════════════════════════════════╗"
echo "║          Relay Framework Installation                      ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo

# Check if relay script exists
if [ ! -f "$RELAY_SCRIPT" ]; then
    echo "❌ Error: relay script not found at $RELAY_SCRIPT"
    exit 1
fi

# Make relay executable
chmod +x "$RELAY_SCRIPT"

echo "Framework location: $SCRIPT_DIR"
echo

# Detect user's actual shell (not the shell running this script)
# Check $SHELL environment variable which contains the user's login shell
USER_SHELL=$(basename "$SHELL")

if [[ "$USER_SHELL" == "zsh" ]]; then
    SHELL_PROFILE="$HOME/.zshrc"
    SHELL_NAME="zsh"
elif [[ "$USER_SHELL" == "bash" ]]; then
    SHELL_PROFILE="$HOME/.bashrc"
    [ -f "$HOME/.bash_profile" ] && SHELL_PROFILE="$HOME/.bash_profile"
    SHELL_NAME="bash"
else
    # Fallback: try to detect from existing config files
    if [ -f "$HOME/.zshrc" ]; then
        SHELL_PROFILE="$HOME/.zshrc"
        SHELL_NAME="zsh"
    elif [ -f "$HOME/.bash_profile" ]; then
        SHELL_PROFILE="$HOME/.bash_profile"
        SHELL_NAME="bash"
    elif [ -f "$HOME/.bashrc" ]; then
        SHELL_PROFILE="$HOME/.bashrc"
        SHELL_NAME="bash"
    else
        SHELL_PROFILE="$HOME/.profile"
        SHELL_NAME="sh"
    fi
fi

echo "Installation Options:"
echo "────────────────────────────────────────────────────────────"
echo
echo "  1. Symlink to ~/bin (recommended)"
echo "     Creates: ~/bin/relay -> $RELAY_SCRIPT"
echo
echo "  2. Add alias to shell profile ($SHELL_NAME)"
echo "     Adds to: $SHELL_PROFILE"
echo
echo "  3. Symlink to /usr/local/bin (system-wide, requires sudo)"
echo "     Creates: /usr/local/bin/relay -> $RELAY_SCRIPT"
echo
echo "  4. Skip installation (use ./relay from this directory)"
echo
read -p "Choose option [1-4]: " choice

case $choice in
    1)
        # Option 1: Symlink to ~/bin
        BIN_DIR="$HOME/bin"
        mkdir -p "$BIN_DIR"

        if [ -L "$BIN_DIR/relay" ] || [ -f "$BIN_DIR/relay" ]; then
            echo
            read -p "⚠️  relay already exists in $BIN_DIR. Overwrite? [y/N]: " overwrite
            if [ "$overwrite" != "y" ] && [ "$overwrite" != "Y" ]; then
                echo "Installation cancelled."
                exit 0
            fi
            rm -f "$BIN_DIR/relay"
        fi

        ln -s "$RELAY_SCRIPT" "$BIN_DIR/relay"
        echo
        echo "✅ Symlink created: $BIN_DIR/relay -> $RELAY_SCRIPT"
        echo

        # Check if ~/bin is in PATH
        if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
            echo "⚠️  $BIN_DIR is not in your PATH"
            echo
            echo "Add this to your $SHELL_PROFILE:"
            echo "    export PATH=\"\$HOME/bin:\$PATH\""
            echo
            read -p "Add to $SHELL_PROFILE now? [y/N]: " add_path
            if [ "$add_path" = "y" ] || [ "$add_path" = "Y" ]; then
                echo "" >> "$SHELL_PROFILE"
                echo "# Relay Framework" >> "$SHELL_PROFILE"
                echo "export PATH=\"\$HOME/bin:\$PATH\"" >> "$SHELL_PROFILE"
                echo "✅ PATH updated in $SHELL_PROFILE"
                echo "   Run: source $SHELL_PROFILE"
            fi
        else
            echo "✅ $BIN_DIR is already in your PATH"
        fi
        ;;

    2)
        # Option 2: Add alias to shell profile
        ALIAS_LINE="alias relay='$RELAY_SCRIPT'"

        if grep -q "alias relay=" "$SHELL_PROFILE" 2>/dev/null; then
            echo
            echo "⚠️  'relay' alias already exists in $SHELL_PROFILE"
            read -p "Overwrite? [y/N]: " overwrite
            if [ "$overwrite" = "y" ] || [ "$overwrite" = "Y" ]; then
                # Remove old alias
                sed -i.bak '/alias relay=/d' "$SHELL_PROFILE"
            else
                echo "Installation cancelled."
                exit 0
            fi
        fi

        echo "" >> "$SHELL_PROFILE"
        echo "# Relay Framework" >> "$SHELL_PROFILE"
        echo "$ALIAS_LINE" >> "$SHELL_PROFILE"
        echo
        echo "✅ Alias added to $SHELL_PROFILE"
        echo "   Run: source $SHELL_PROFILE"
        echo "   Or open a new terminal"
        ;;

    3)
        # Option 3: System-wide symlink
        SYSTEM_BIN="/usr/local/bin"

        if [ -L "$SYSTEM_BIN/relay" ] || [ -f "$SYSTEM_BIN/relay" ]; then
            echo
            read -p "⚠️  relay already exists in $SYSTEM_BIN. Overwrite? [y/N]: " overwrite
            if [ "$overwrite" != "y" ] && [ "$overwrite" != "Y" ]; then
                echo "Installation cancelled."
                exit 0
            fi
            sudo rm -f "$SYSTEM_BIN/relay"
        fi

        sudo ln -s "$RELAY_SCRIPT" "$SYSTEM_BIN/relay"
        echo
        echo "✅ System-wide symlink created: $SYSTEM_BIN/relay -> $RELAY_SCRIPT"
        ;;

    4)
        # Option 4: Skip
        echo
        echo "Installation skipped."
        echo
        echo "To use Relay Framework, run:"
        echo "    cd $SCRIPT_DIR"
        echo "    ./relay start"
        echo
        exit 0
        ;;

    *)
        echo "Invalid option. Installation cancelled."
        exit 1
        ;;
esac

echo
echo "╔════════════════════════════════════════════════════════════╗"
echo "║          Installation Complete!                            ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo
echo "Next steps:"
echo "───────────────────────────────────────────────────────────"
echo "  1. Open a new terminal or run: source $SHELL_PROFILE"
echo "  2. Navigate to your project directory"
echo "  3. Run: relay start"
echo
echo "Usage:"
echo "  relay start              # Start or resume project"
echo "  relay ui                 # Launch Web UI"
echo "  relay status             # Show project progress"
echo "  relay --help             # Show all commands"
echo
echo "Documentation: $SCRIPT_DIR/README.md"
echo
