#!/usr/bin/env bash
# Per-user installer for Text Capture (design D11).
#
#   scripts/install.sh                install for the current user (checks packages first)
#   scripts/install.sh --uninstall    stop the app; remove its shortcut, autostart entry and files
#   scripts/install.sh --check-deps   list missing apt packages and offer to install them
set -euo pipefail

APP_DESKTOP_ID=io.github.CreditStar0117.TextCapture
RUNTIME_PACKAGES=(python3-pyqt6 qt6-wayland tesseract-ocr tesseract-ocr-eng)
DEV_PACKAGES=(python3-pytest)

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
INSTALL_DIR="$DATA_HOME/text-capture"
BIN_DIR="$HOME/.local/bin"
LAUNCHER="$BIN_DIR/text-capture"
DESKTOP_FILE="$DATA_HOME/applications/$APP_DESKTOP_ID.desktop"
ICON_ROOT="$DATA_HOME/icons/hicolor"
PYTHON=/usr/bin/python3  # PyQt6 from apt belongs to the system Python

usage() {
    sed -n '2,/^set /p' "$0" | sed '$d; s/^# \{0,1\}//'
}

missing_packages() {
    local pkg
    for pkg in "$@"; do
        if [[ "$(dpkg-query -W -f='${db:Status-Abbrev}' "$pkg" 2>/dev/null)" != ii* ]]; then
            echo "$pkg"
        fi
    done
}

check_deps() {
    local packages=("$@") missing answer
    mapfile -t missing < <(missing_packages "${packages[@]}")
    if (( ${#missing[@]} == 0 )); then
        echo "All required packages are installed: ${packages[*]}"
        return 0
    fi
    echo "Missing packages: ${missing[*]}"
    if [[ ! -t 0 ]]; then
        echo "Install them with: sudo apt install ${missing[*]}"
        return 1
    fi
    read -r -p "Install them now with 'sudo apt install'? [y/N] " answer
    if [[ "$answer" =~ ^[Yy]$ ]]; then
        sudo apt install -y "${missing[@]}"
        mapfile -t missing < <(missing_packages "${packages[@]}")
        if (( ${#missing[@]} == 0 )); then
            echo "All required packages are installed: ${packages[*]}"
            return 0
        fi
        echo "Still missing: ${missing[*]}"
    fi
    return 1
}

refresh_caches() {
    command -v update-desktop-database >/dev/null && update-desktop-database -q "$(dirname "$DESKTOP_FILE")" || true
    command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t -f "$ICON_ROOT" 2>/dev/null || true
}

install_app() {
    check_deps "${RUNTIME_PACKAGES[@]}" || { echo "Install the missing packages, then run this script again."; exit 1; }

    if [[ -x "$LAUNCHER" ]]; then
        "$LAUNCHER" --quit >/dev/null 2>&1 || true  # the new code takes over at the next start
    fi

    mkdir -p "$INSTALL_DIR" "$BIN_DIR" "$(dirname "$DESKTOP_FILE")"
    rm -rf "$INSTALL_DIR/text_capture"
    cp -r "$SRC_DIR/text_capture" "$INSTALL_DIR/"
    find "$INSTALL_DIR" -name __pycache__ -type d -prune -exec rm -rf {} +

    cat > "$LAUNCHER" <<EOF
#!/bin/sh
# Text Capture launcher, written by scripts/install.sh
export TEXT_CAPTURE_LAUNCHER=$(printf '%q' "$LAUNCHER")
export PYTHONPATH=$(printf '%q' "$INSTALL_DIR")\${PYTHONPATH:+:\$PYTHONPATH}
exec $PYTHON -m text_capture "\$@"
EOF
    chmod 755 "$LAUNCHER"

    QT_QPA_PLATFORM=offscreen PYTHONPATH="$INSTALL_DIR" "$PYTHON" -m text_capture.icons "$ICON_ROOT" >/dev/null

    local exec_line
    exec_line="$(QT_QPA_PLATFORM=offscreen PYTHONPATH="$INSTALL_DIR" "$PYTHON" -c \
        'import sys; from text_capture.settings import desktop_exec; print(desktop_exec([sys.argv[1]]))' "$LAUNCHER")"
    cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=Text Capture
GenericName=Screen OCR
Comment=Copy text from anywhere on the screen
Exec=$exec_line
Icon=$APP_DESKTOP_ID
Terminal=false
Categories=Utility;
Keywords=OCR;text;screenshot;capture;clipboard;
StartupNotify=false
X-GNOME-UsesNotifications=true
EOF
    refresh_caches

    echo "Installed Text Capture:"
    echo "  app:       $INSTALL_DIR/text_capture"
    echo "  command:   $LAUNCHER"
    echo "  app grid:  $DESKTOP_FILE"
    echo "Start it from the app grid (\"Text Capture\") or run: $LAUNCHER"
    case ":$PATH:" in
        *":$BIN_DIR:"*) ;;
        *) echo "Note: $BIN_DIR is not on your PATH yet; log out and back in to use the bare 'text-capture' command." ;;
    esac
}

uninstall_app() {
    if [[ -x "$LAUNCHER" ]]; then
        "$LAUNCHER" --uninstall || true
    elif [[ -d "$INSTALL_DIR/text_capture" ]]; then
        PYTHONPATH="$INSTALL_DIR" "$PYTHON" -m text_capture --uninstall || true
    fi
    rm -rf "$INSTALL_DIR"
    rm -f "$LAUNCHER" "$DESKTOP_FILE"
    rm -f "$ICON_ROOT"/*/apps/"$APP_DESKTOP_ID".png
    refresh_caches
    echo "Uninstalled Text Capture. Settings are kept in ${XDG_CONFIG_HOME:-$HOME/.config}/text-capture (delete that folder to remove them)."
}

case "${1:-}" in
    "") install_app ;;
    --uninstall) uninstall_app ;;
    --check-deps) check_deps "${RUNTIME_PACKAGES[@]}" "${DEV_PACKAGES[@]}" ;;
    -h|--help) usage ;;
    *) usage; exit 2 ;;
esac
