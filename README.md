# frozen-gates

**AI agents should be citizens of a system, not autonomous actors.**

When you give an AI agent write access to your codebase, you're trusting it to make high-level decisions within your architecture. But agents drift. They "fix" things that aren't broken. They refactor code they don't fully understand. They modify configuration files because they think they know better.

Silent drift is the killer. You ask for a bug fix, and somewhere in the process the agent also:
- Rewrote your package.json dependencies
- "Improved" your SDK internals
- Refactored a working abstraction into something clever
- Added 600 lines to a file that was intentionally small

**frozen-gates removes the agent's ability to drift.** It enforces hard boundaries at the filesystem level - boundaries the agent cannot negotiate, bypass, or "helpfully" work around.

## Philosophy

Agents should operate at a higher level of abstraction:
- Make architectural decisions → yes
- Implement features within existing patterns → yes
- Modify foundational code → **no, ask a human**
- Change project configuration → **no, ask a human**
- Let files grow unbounded → **no, enforce limits**

The agent becomes a citizen operating within your system's constraints, not an autonomous actor rewriting the rules.

## Features

- **Filesystem locks** - OS-level immutability (agent literally cannot write)
- **LOC limits** - Prevent files from growing beyond maintainable size
- **Human-only unlock** - Sudo requirement ensures only humans change boundaries

## Security Model

| Action | Who | Why |
|--------|-----|-----|
| Lock | Human only | You define the boundaries |
| Unlock | Human only | Agent can NEVER unlock |
| Status | Claude + Human | Read-only awareness |

## Install

```bash
/plugin install frozen-gates --source github --repo sceat/frozen-gates-claude-plugin
```

## Requirements

- macOS (uses `chflags uchg`)
- `yq`: `brew install yq`
- `pyyaml`: `pip install pyyaml`

## Setup

### 1. Define your boundaries

```bash
mkdir -p ~/.claude
cat > ~/.claude/frozengates.yaml << 'EOF'
version: 1

defaults:
  loc:
    limit: 500
    extensions: [.ts, .tsx, .js, .jsx, .py, .rs]

repos:
  # SDK code is foundational - agent should never touch it
  my-sdk:
    path: ~/dev/my-sdk
    frozen_all: true

  # Config files define the system - agent works within them
  my-app:
    path: ~/dev/my-app
    frozen:
      - package.json
      - package-lock.json
      - tsconfig.json
    loc:
      limit: 400
EOF
```

### 2. Add terminal controls

```bash
cat >> ~/.zshrc << 'EOF'

# Frozen gates - human-only lock/unlock
alias claude-lock='~/dev/sceat/frozen-gates-claude-plugin/scripts/frozengates.sh lock'
alias claude-unlock='~/dev/sceat/frozen-gates-claude-plugin/scripts/frozengates.sh unlock'
alias claude-status='~/dev/sceat/frozen-gates-claude-plugin/scripts/frozengates.sh status'
EOF
source ~/.zshrc
```

### 3. Activate boundaries

```bash
claude-lock  # Requires sudo - this is intentional
```

## Usage

**Human (terminal):**
```bash
claude-lock      # Activate all boundaries
claude-unlock    # Release boundaries (when YOU decide)
claude-status    # View current state
```

**Agent (plugin):**
```bash
/frozen-gates:status  # Agent can see boundaries, not change them
```

## How It Works

1. **chflags uchg** - macOS immutable flag at filesystem level
2. **Pre-tool-use hook** - Blocks Write/Edit before execution
3. **Stop hook** - Enforces LOC limits on session end
4. **Sudo requirement** - Physical barrier requiring human terminal access

Even if the hook fails, the OS-level lock prevents modification. Belt and suspenders.

## Config Reference

```yaml
version: 1

defaults:
  loc:
    limit: 500                                    # Default max lines
    extensions: [.ts, .tsx, .js, .jsx, .py, .rs]  # Files to check

repos:
  # Entire SDK is off-limits
  my-sdk:
    path: ~/dev/my-sdk
    frozen_all: true

  # Specific files frozen + custom LOC
  my-app:
    path: ~/dev/my-app
    frozen:
      - package.json
      - tsconfig.json
    loc:
      limit: 400
      exclude: ["*.test.ts"]

  # LOC only (no frozen files)
  my-scripts:
    path: ~/dev/my-scripts
    loc:
      limit: 200
```

## License

MIT
