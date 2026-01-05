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
except ImportError:
    print("frozen-gates: PyYAML required - install via your package manager", file=sys.stderr)
    sys.exit(1)

DEFAULT_LOC_LIMIT = 500
DEFAULT_LOC_EXTENSIONS = [".ts", ".tsx", ".js", ".jsx", ".py", ".rs", ".go", ".vue"]


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


def extract_modified_from_transcript(transcript_path):
    """Extract Write/Edit file paths from a single transcript."""
    modified = set()
    if not transcript_path or not os.path.exists(transcript_path):
        return modified

    try:
        with open(transcript_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    # Tool calls are nested in message.content[]
                    message = entry.get("message", {})
                    content = message.get("content", [])
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "tool_use":
                            tool_name = item.get("name", "")
                            if tool_name in ("Write", "Edit"):
                                file_path = item.get("input", {}).get("file_path")
                                if file_path:
                                    modified.add(os.path.abspath(os.path.expanduser(file_path)))
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass

    return modified


def get_session_modified_files(transcript_path):
    """Extract modified files from session transcript AND all subagent transcripts."""
    modified = set()

    if not transcript_path or not os.path.exists(transcript_path):
        return list(modified)

    # Extract session ID from main transcript filename
    session_id = os.path.basename(transcript_path).replace('.jsonl', '')
    transcript_dir = os.path.dirname(transcript_path)

    # Get files from main transcript
    modified.update(extract_modified_from_transcript(transcript_path))

    # Find and process all agent-*.jsonl transcripts that belong to this session
    for agent_transcript in Path(transcript_dir).glob('agent-*.jsonl'):
        try:
            with open(agent_transcript, "r", encoding="utf-8") as f:
                first_line = f.readline().strip()
                if first_line:
                    entry = json.loads(first_line)
                    # Only process agent transcripts that belong to this session
                    if entry.get('sessionId') == session_id:
                        modified.update(extract_modified_from_transcript(str(agent_transcript)))
        except Exception:
            continue

    return list(modified)


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


def load_config():
    """Load config from session's project dir or user scope.

    Resolution order:
    1. $CLAUDE_PROJECT_DIR/.claude/frozengates.yaml (session scope)
    2. ~/.claude/frozengates.yaml (user scope)
    """
    # Check session's project dir
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if project_dir:
        project_config = os.path.join(project_dir, ".claude", "frozengates.yaml")
        if os.path.exists(project_config):
            with open(project_config) as f:
                return yaml.safe_load(f)

    # Fall back to user scope
    user_config = os.path.expanduser("~/.claude/frozengates.yaml")
    if os.path.exists(user_config):
        with open(user_config) as f:
            return yaml.safe_load(f)

    return None


def main():
    # Read hook input from stdin
    try:
        hook_input = json.load(sys.stdin)
    except Exception:
        hook_input = {}

    transcript_path = hook_input.get("transcript_path")
    if transcript_path:
        transcript_path = os.path.expanduser(transcript_path)

    config = load_config()
    if not config:
        # No config = no LOC enforcement
        sys.exit(0)

    modified_files = get_session_modified_files(transcript_path)

    if not modified_files:
        sys.exit(0)

    violations = []

    for file_path in modified_files:
        if not os.path.exists(file_path):
            continue

        # Get git root for this file (for relative path display)
        file_dir = os.path.dirname(file_path)
        git_root = find_git_root(file_dir)

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
