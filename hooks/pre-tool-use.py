#!/usr/bin/env python3
"""
Frozen Gates: Pre-tool-use hook
Blocks Write/Edit operations on frozen files defined in frozengates.yaml
"""

import sys
import json
import os
from pathlib import Path
from fnmatch import fnmatch

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


def load_config():
    """Load frozengates config."""
    config_path = os.environ.get("FROZENGATES_CONFIG", os.path.expanduser("~/.claude/frozengates.yaml"))

    if not os.path.exists(config_path):
        return None

    if not HAS_YAML:
        # Fallback: try to parse simple YAML manually
        return None

    try:
        with open(config_path) as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def get_frozen_paths(config):
    """Extract all frozen file paths from config."""
    frozen = []

    if not config or "repos" not in config:
        return frozen

    for repo_name, repo_config in config["repos"].items():
        repo_path = os.path.expanduser(repo_config.get("path", ""))
        if not repo_path:
            continue

        if repo_config.get("frozen_all"):
            frozen.append({"path": repo_path, "pattern": "**/*", "repo": repo_name, "full": True})
        elif "frozen" in repo_config:
            for pattern in repo_config["frozen"]:
                frozen.append({"path": repo_path, "pattern": pattern, "repo": repo_name, "full": False})

    return frozen


def is_path_frozen(file_path, frozen_paths):
    """Check if a file path matches any frozen pattern."""
    file_path = os.path.abspath(os.path.expanduser(file_path))

    for frozen in frozen_paths:
        repo_path = os.path.abspath(frozen["path"])

        if frozen["full"]:
            # Entire directory is frozen
            if file_path.startswith(repo_path + "/") or file_path == repo_path:
                return frozen["repo"], "entire directory"
        else:
            # Specific file pattern
            target = os.path.join(repo_path, frozen["pattern"])
            if file_path == target or fnmatch(file_path, target):
                return frozen["repo"], frozen["pattern"]

    return None, None


def main():
    # Read hook input from stdin
    try:
        hook_input = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    tool_name = hook_input.get("tool_name", "")
    tool_input = hook_input.get("tool_input", {})

    # Only check Write and Edit tools
    if tool_name not in ("Write", "Edit"):
        sys.exit(0)

    file_path = tool_input.get("file_path", "")
    if not file_path:
        sys.exit(0)

    config = load_config()
    if not config:
        sys.exit(0)

    frozen_paths = get_frozen_paths(config)
    repo_name, pattern = is_path_frozen(file_path, frozen_paths)

    if repo_name:
        result = {
            "decision": "block",
            "reason": f"FROZEN: {file_path} is protected by frozen-gates [{repo_name}:{pattern}]. Human must unlock first."
        }
        print(json.dumps(result))
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
