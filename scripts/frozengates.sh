#!/bin/bash
#
# frozengates - Filesystem locks for Claude Code
# Prevents AI from modifying protected files using macOS uchg flags
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Config path resolution:
# 1. -c <config> flag
# 2. $FROZENGATES_CONFIG environment variable
# 3. $CLAUDE_PROJECT_DIR/.claude/frozengates.yaml (project scope)
# 4. ~/.claude/frozengates.yaml (global fallback)
CONFIG_PATH=""

show_help() {
    echo -e "${BLUE}frozengates${NC} - Filesystem locks for Claude Code\n"
    echo "Usage: $0 [-c <config>] <command> [repo]"
    echo ""
    echo "Options:"
    echo "  -c <config>    Path to config file"
    echo ""
    echo "Commands:"
    echo "  lock [repo]    Lock files (all repos if no arg)"
    echo "  unlock [repo]  Unlock files (all repos if no arg)"
    echo "  status         Show lock status for all repos"
    echo ""
    echo "Config resolution:"
    echo "  1. -c <config> flag"
    echo "  2. \$FROZENGATES_CONFIG environment variable"
    echo "  3. \$CLAUDE_PROJECT_DIR/.claude/frozengates.yaml (project scope)"
    echo "  4. ~/.claude/frozengates.yaml (global fallback)"
    echo ""
    echo "Current config: $CONFIG_PATH"
}

# Parse options
while getopts "c:h" opt; do
    case $opt in
        c) CONFIG_PATH="$OPTARG" ;;
        h) show_help; exit 0 ;;
        *) show_help; exit 1 ;;
    esac
done
shift $((OPTIND - 1))

# Resolve config path if not set by flag
if [[ -z "$CONFIG_PATH" ]]; then
    if [[ -n "$FROZENGATES_CONFIG" ]]; then
        CONFIG_PATH="$FROZENGATES_CONFIG"
    elif [[ -n "$CLAUDE_PROJECT_DIR" && -f "$CLAUDE_PROJECT_DIR/.claude/frozengates.yaml" ]]; then
        CONFIG_PATH="$CLAUDE_PROJECT_DIR/.claude/frozengates.yaml"
    else
        CONFIG_PATH="$HOME/.claude/frozengates.yaml"
    fi
fi

# Check dependencies
if ! command -v yq &> /dev/null; then
    echo -e "${RED}Error: yq is required but not installed${NC}"
    echo "Install with: brew install yq"
    exit 1
fi

if [[ ! -f "$CONFIG_PATH" ]]; then
    echo -e "${RED}Error: Config not found at $CONFIG_PATH${NC}"
    exit 1
fi

# Expand tilde in paths
expand_path() {
    eval echo "$1"
}

# Check if path has uchg flag
is_locked() {
    local path="$1"
    if [[ -e "$path" ]]; then
        ls -lO "$path" 2>/dev/null | grep -q "uchg"
        return $?
    fi
    return 1
}

# Get all repo names from config
get_repos() {
    yq '.repos | keys[]' "$CONFIG_PATH"
}

# Get repo path
get_repo_path() {
    local repo="$1"
    yq ".repos.${repo}.path" "$CONFIG_PATH"
}

# Check if repo has frozen_all flag
has_frozen_all() {
    local repo="$1"
    local val=$(yq ".repos.${repo}.frozen_all // false" "$CONFIG_PATH")
    [[ "$val" == "true" ]]
}

# Get frozen files for a repo
get_frozen_files() {
    local repo="$1"
    yq ".repos.${repo}.frozen[]" "$CONFIG_PATH" 2>/dev/null || true
}

# Lock a single repo
lock_repo() {
    local repo="$1"
    local path=$(expand_path "$(get_repo_path "$repo")")

    echo -e "${BLUE}Locking ${repo}...${NC}"

    if [[ ! -d "$path" ]]; then
        echo -e "  ${YELLOW}Warning: Path does not exist: $path${NC}"
        return
    fi

    if has_frozen_all "$repo"; then
        echo -e "  Locking entire directory: $path"
        sudo chflags -R uchg "$path"
        echo -e "  ${GREEN}Locked (frozen_all)${NC}"
    else
        local files=$(get_frozen_files "$repo")
        if [[ -n "$files" ]]; then
            while IFS= read -r file; do
                local filepath="$path/$file"
                if [[ -e "$filepath" ]]; then
                    sudo chflags uchg "$filepath"
                    echo -e "  ${GREEN}Locked: $file${NC}"
                else
                    echo -e "  ${YELLOW}Not found: $file${NC}"
                fi
            done <<< "$files"
        else
            echo -e "  ${YELLOW}No frozen files configured${NC}"
        fi
    fi
}

# Unlock a single repo
unlock_repo() {
    local repo="$1"
    local path=$(expand_path "$(get_repo_path "$repo")")

    echo -e "${BLUE}Unlocking ${repo}...${NC}"

    if [[ ! -d "$path" ]]; then
        echo -e "  ${YELLOW}Warning: Path does not exist: $path${NC}"
        return
    fi

    if has_frozen_all "$repo"; then
        echo -e "  Unlocking entire directory: $path"
        sudo chflags -R nouchg "$path"
        echo -e "  ${GREEN}Unlocked (frozen_all)${NC}"
    else
        local files=$(get_frozen_files "$repo")
        if [[ -n "$files" ]]; then
            while IFS= read -r file; do
                local filepath="$path/$file"
                if [[ -e "$filepath" ]]; then
                    sudo chflags nouchg "$filepath"
                    echo -e "  ${GREEN}Unlocked: $file${NC}"
                else
                    echo -e "  ${YELLOW}Not found: $file${NC}"
                fi
            done <<< "$files"
        else
            echo -e "  ${YELLOW}No frozen files configured${NC}"
        fi
    fi
}

# Show status for all repos
show_status() {
    echo -e "${BLUE}=== Frozengates Status ===${NC}\n"
    echo -e "Config: $CONFIG_PATH\n"

    for repo in $(get_repos); do
        local path=$(expand_path "$(get_repo_path "$repo")")

        echo -e "${BLUE}$repo${NC} ($path)"

        if [[ ! -d "$path" ]]; then
            echo -e "  ${RED}Path does not exist${NC}\n"
            continue
        fi

        if has_frozen_all "$repo"; then
            # Check if any file in the directory is locked
            if ls -lO "$path" 2>/dev/null | grep -q "uchg"; then
                echo -e "  ${GREEN}LOCKED${NC} (frozen_all)\n"
            else
                echo -e "  ${YELLOW}UNLOCKED${NC} (frozen_all)\n"
            fi
        else
            local files=$(get_frozen_files "$repo")
            if [[ -n "$files" ]]; then
                while IFS= read -r file; do
                    local filepath="$path/$file"
                    if [[ -e "$filepath" ]]; then
                        if is_locked "$filepath"; then
                            echo -e "  ${GREEN}LOCKED${NC}   $file"
                        else
                            echo -e "  ${YELLOW}UNLOCKED${NC} $file"
                        fi
                    else
                        echo -e "  ${RED}MISSING${NC}  $file"
                    fi
                done <<< "$files"
                echo ""
            else
                echo -e "  ${YELLOW}No frozen files configured${NC}\n"
            fi
        fi
    done
}

# Main command handling
case "${1:-}" in
    lock)
        if [[ -n "${2:-}" ]]; then
            lock_repo "$2"
        else
            echo -e "${BLUE}Locking all repos...${NC}\n"
            for repo in $(get_repos); do
                lock_repo "$repo"
                echo ""
            done
        fi
        ;;
    unlock)
        if [[ -n "${2:-}" ]]; then
            unlock_repo "$2"
        else
            echo -e "${BLUE}Unlocking all repos...${NC}\n"
            for repo in $(get_repos); do
                unlock_repo "$repo"
                echo ""
            done
        fi
        ;;
    status)
        show_status
        ;;
    *)
        show_help
        ;;
esac
