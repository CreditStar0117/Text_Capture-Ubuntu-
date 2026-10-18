#!/usr/bin/env bash
# Per-user installer for Text Capture (design D11).
#
#   scripts/install.sh --check-deps   list missing apt packages and offer to install them
set -euo pipefail

APT_PACKAGES=(python3-pyqt6 qt6-wayland tesseract-ocr tesseract-ocr-eng python3-pytest)

usage() {
    sed -n '2,/^set /p' "$0" | sed '$d; s/^# \{0,1\}//'
}

missing_packages() {
    local pkg
    for pkg in "${APT_PACKAGES[@]}"; do
        if [[ "$(dpkg-query -W -f='${db:Status-Abbrev}' "$pkg" 2>/dev/null)" != ii* ]]; then
            echo "$pkg"
        fi
    done
}

check_deps() {
    local missing
    mapfile -t missing < <(missing_packages)
    if (( ${#missing[@]} == 0 )); then
        echo "All required packages are installed: ${APT_PACKAGES[*]}"
        return 0
    fi
    echo "Missing packages: ${missing[*]}"
    if [[ ! -t 0 ]]; then
        echo "Install them with: sudo apt install ${missing[*]}"
        return 1
    fi
    local answer
    read -r -p "Install them now with 'sudo apt install'? [y/N] " answer
    if [[ "$answer" =~ ^[Yy]$ ]]; then
        sudo apt install -y "${missing[@]}"
        mapfile -t missing < <(missing_packages)
        if (( ${#missing[@]} == 0 )); then
            echo "All required packages are installed: ${APT_PACKAGES[*]}"
            return 0
        fi
        echo "Still missing: ${missing[*]}"
    fi
    return 1
}

case "${1:-}" in
    --check-deps) check_deps ;;
    -h|--help) usage ;;
    *) usage; exit 2 ;;
esac
