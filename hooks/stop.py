#!/usr/bin/env python3
"""
Frozen Gates: Stop hook
Checks LOC limits on modified files before session ends.
"""

import sys
import json
import os
import subprocess
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

DEFAULT_LOC_LIMIT = 500
DEFAULT_LOC_EXTENSIONS = [".ts", ".tsx", ".js", ".jsx", ".py", ".rs", ".go", ".vue"]


def load_config():
    """Load frozengates config."""
    config_path = os.environ.get("FROZENGATES_CONFIG", os.path.expanduser("~/.claude/frozengates.yaml"))

    if not os.path.exists(config_path):
        return None

    if not HAS_YAML:
        return None

    try:
        with open(config_path) as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def get_loc_config(config, repo_path):
    """Get LOC config for a specific repo, with defaults."""
    defaults = config.get("defaults", {}).get("loc", {})
    default_limit = defaults.get("limit", DEFAULT_LOC_LIMIT)
    default_extensions = defaults.get("extensions", DEFAULT_LOC_EXTENSIONS)

    # Check if file is in a configured repo with custom LOC settings
    if config and "repos" in config:
        for repo_name, repo_config in config["repos"].items():
            rpath = os.path.expanduser(repo_config.get("path", ""))
            if not rpath:
                continue

            rpath = os.path.abspath(rpath)
            if repo_path.startswith(rpath + "/") or repo_path == rpath:
                repo_loc = repo_config.get("loc", {})
                return {
                    "limit": repo_loc.get("limit", default_limit),
                    "extensions": repo_loc.get("extensions", default_extensions),
                    "exclude": repo_loc.get("exclude", []),
                    "repo_name": repo_name
                }

    return {
        "limit": default_limit,
        "extensions": default_extensions,
        "exclude": [],
        "repo_name": None
    }


def find_git_root(path):
    """Find git root for a path."""
    try:
        result = subprocess.run(
            ["git", "-C", path, "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def get_changed_files():
    """Get all changed files in current directory's git repo."""
    cwd = os.getcwd()
    git_root = find_git_root(cwd)
    if not git_root:
        return [], None

    try:
        all_files = []

        # Unstaged changes
        result = subprocess.run(
            ["git", "-C", git_root, "diff", "--name-only", "HEAD"],
            capture_output=True, text=True, timeout=5
        )
        if result.stdout.strip():
            all_files.extend(result.stdout.strip().split("\n"))

        # Staged changes
        result2 = subprocess.run(
            ["git", "-C", git_root, "diff", "--cached", "--name-only"],
            capture_output=True, text=True, timeout=5
        )
        if result2.stdout.strip():
            all_files.extend(result2.stdout.strip().split("\n"))

        # Untracked files
        result3 = subprocess.run(
            ["git", "-C", git_root, "ls-files", "--others", "--exclude-standard"],
            capture_output=True, text=True, timeout=5
        )
        if result3.stdout.strip():
            all_files.extend(result3.stdout.strip().split("\n"))

        # Convert to absolute paths
        abs_files = [os.path.join(git_root, f) for f in set(all_files)]
        return abs_files, git_root

    except Exception:
        return [], None


def count_loc(file_path):
    """Count non-empty lines in a file."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return sum(1 for line in f if line.strip())
    except Exception:
        return 0


def matches_pattern(filename, patterns):
    """Check if filename matches any glob pattern."""
    from fnmatch import fnmatch
    for pattern in patterns:
        if fnmatch(filename, pattern):
            return True
    return False


def main():
    config = load_config()
    changed_files, git_root = get_changed_files()

    if not changed_files:
        sys.exit(0)

    violations = []

    for file_path in changed_files:
        if not os.path.exists(file_path):
            continue

        ext = Path(file_path).suffix
        loc_config = get_loc_config(config, file_path)

        # Check extension
        if ext not in loc_config["extensions"]:
            continue

        # Check exclusions
        rel_path = os.path.relpath(file_path, git_root) if git_root else file_path
        if matches_pattern(rel_path, loc_config.get("exclude", [])):
            continue

        loc = count_loc(file_path)
        limit = loc_config["limit"]

        if loc > limit:
            repo_info = f" [{loc_config['repo_name']}]" if loc_config["repo_name"] else ""
            violations.append(f"{rel_path}: {loc} lines (limit: {limit}){repo_info}")

    if violations:
        print("LOC limit exceeded:", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
