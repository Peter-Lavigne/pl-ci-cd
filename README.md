# Verploy

[![PyPI version](https://img.shields.io/pypi/v/verploy)](https://pypi.org/project/verploy/)
[![Python versions](https://img.shields.io/pypi/pyversions/verploy)](https://pypi.org/project/verploy/)
[![License](https://img.shields.io/pypi/l/verploy)](./LICENSE)
[![Coverage](https://img.shields.io/badge/coverage-100%25-brightgreen)](https://github.com/Peter-Lavigne/verploy)
<!-- Coverage is enforced by pytest --cov-fail-under=100 -->

Verploy is an opinionated Claude Code orchestration tool aiming to maximize developer productivity. Verploy treats manual verification, such as code review, as the primary bottleneck of development.

## Quickstart

"Claude, set up https://github.com/Peter-Lavigne/verploy for my project, and explain how to use it."

## Features

Verploy allows defining deploy-gating and fine-grained manual checks on a per-project basis. Manual checks are more effective when developers commit more working memory to them, so Verploy aims to minimize the number of agents running in parallel by making the CI/CD process as fast as possible.

To that end, additional features include:
- Everything is local-first to minimize latency compared to remote agents and CI/CD systems
- Multi-agent support, so the developer is never waiting for an agent to finish
- A fast-forward-only workflow prevents silent merge conflicts
- Worktree support enables agents to work independently
- Works with Docker to sandbox agent execution and isolate deployment credentials

## Installation and setup

### Installation

Verploy is available as [`verploy`](https://pypi.org/project/verploy/) on PyPI.

Because Verploy uses other tools you have installed, it's recommended to install it per-project instead of globally:

```bash
uv add --dev verploy
```

### Stop hook

Verploy expects changes to be committed and worktrees to be rebased onto main before it runs. Add `verploy-hook` as a Claude Code [Stop hook](https://docs.anthropic.com/en/docs/claude-code/hooks) to enforce this automatically.

`.claude/settings.json`:
```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "uv run verploy-hook",
            "timeout": 600
          }
        ]
      }
    ]
  }
}
```

The hook checks that there are no uncommitted changes, the branch is rebased onto main (in worktrees), and runs the verify script if one exists.

### Scripts

Add a `.verploy/` directory to your project with any of these executable scripts:

- `verify` (optional) -- runs automated quality checks on Stop (e.g. linting, type checking, tests)
- `manual` -- runs manual checks (e.g. human review, expensive tests)
- `deploy` -- runs after pushing (e.g. publishing to PyPI)

### Example `.verploy/` scripts

`.verploy/verify`:
```bash
#!/bin/bash
set -euo pipefail

uv run ruff format .
uv run ruff check --fix .
uv run pyright
uv run pytest --cov --cov-fail-under=100
```

`.verploy/deploy`:
```bash
#!/bin/bash
set -euo pipefail

uv build --no-sources
uv publish
```

`.verploy/manual`:
```sh
#!/bin/sh
read -p "Review the code. Is it acceptable? (y/n) " answer
[ "$answer" = "y" ]
```

## Usage

```bash
uv run verploy
```

## License

Licensed under the Apache License 2.0. See [LICENSE](./LICENSE).
