#!/usr/bin/env bash
set -e

echo -e "\033[36mInstalling Jev Decision Layer...\033[0m"

# Install Python requirements
if command -v pip3 &>/dev/null; then
    pip3 install -r "$(dirname "$0")/requirements.txt" --quiet
elif command -v pip &>/dev/null; then
    pip install -r "$(dirname "$0")/requirements.txt" --quiet
fi

# Make scripts executable
chmod +x "$(dirname "$0")/jev.sh"

# Create initial jev_keys.json from template if not present
KEYS_FILE="$(dirname "$0")/jev_keys.json"
if [ ! -f "$KEYS_FILE" ]; then
    cp "$(dirname "$0")/jev_keys.example.json" "$KEYS_FILE"
    echo -e "\033[33mInitialized jev_keys.json from template.\033[0m"
fi

echo -e "\033[32mInstallation complete! Try running: ./jev.sh --help\033[0m"
