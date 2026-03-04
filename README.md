# gz-dap-proxy

A DAP (Debug Adapter Protocol) proxy that automatically pauses and unpauses [Gazebo Sim](https://gazebosim.org/) when you hit breakpoints while debugging ROS 2 nodes.

## Problem

When debugging ROS 2 nodes, hitting a breakpoint doesn't stop the Gazebo simulation — the robot keeps moving while you inspect variables. This makes debugging real-time systems nearly impossible.

## Solution

`gz-dap-proxy` sits between your editor (Zed, Neovim, Helix, etc.) and the actual debug adapter (codelldb/debugpy). It intercepts DAP messages to:

- **Pause** Gazebo when a breakpoint is hit (`stopped` event)
- **Unpause** Gazebo when you resume execution (`continue`, `next`, `stepIn`, `stepOut`)

```
Editor (DAP client)
    │  stdin/stdout
    ▼
gz-dap-proxy
    │  stdin/stdout
    ▼
codelldb / debugpy (DAP server)

    gz-dap-proxy also calls:
    → gz service  pause:true   (on stopped)
    → gz service  pause:false  (on continue/step)
```

## Installation

```bash
pip install gz-dap-proxy
```

Or install from source:

```bash
git clone https://github.com/<user>/gz-dap-proxy.git
cd gz-dap-proxy
pip install -e .
```

## Usage

Wrap your debug adapter command with `gz-dap-proxy`:

```bash
# With codelldb (C/C++)
gz-dap-proxy --world my_world -- codelldb

# With debugpy (Python)
gz-dap-proxy --world my_world -- python -m debugpy --listen 0
```

### Options

```
gz-dap-proxy [OPTIONS] -- <ADAPTER_COMMAND> [ADAPTER_ARGS...]

Options:
  --world <NAME>    Gazebo world name (default: $GZ_WORLD_NAME or "default")
  --timeout <MS>    gz service timeout in ms (default: 1000)
  --verbose, -v     Log DAP messages to stderr
```

### Environment variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GZ_WORLD_NAME` | Gazebo world name | `default` |

### Zed configuration

In `.zed/debug.json`:

```json
{
  "label": "Debug ROS 2 Node (with Gazebo pause)",
  "adapter": "CodeLLDB",
  "request": "launch",
  "program": "${workspaceFolder}/install/my_pkg/lib/my_pkg/my_node",
  "command": "gz-dap-proxy",
  "args": ["--world", "my_world", "--", "codelldb", "--port", "${port}"]
}
```

### Neovim (nvim-dap)

```lua
dap.adapters.codelldb_gz = {
  type = "executable",
  command = "gz-dap-proxy",
  args = { "--world", "my_world", "--", "codelldb" },
}
```

## Requirements

- Python >= 3.10
- `gz` CLI (Gazebo Sim) installed and on `$PATH`
- A running Gazebo simulation

## License

MIT
