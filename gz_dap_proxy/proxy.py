"""Async DAP proxy that intercepts messages to control Gazebo Sim."""

import argparse
import asyncio
import json
import logging
import os
import sys

from .gazebo import pause_simulation, unpause_simulation

log = logging.getLogger(__name__)

# DAP requests that resume execution
RESUME_COMMANDS = {"continue", "next", "stepIn", "stepOut", "stepBack"}


async def read_dap_message(reader: asyncio.StreamReader) -> dict | None:
    """Read one DAP message (Content-Length framing) from *reader*."""
    headers: dict[str, str] = {}
    while True:
        line = await reader.readline()
        if not line:
            return None  # EOF
        decoded = line.decode("ascii").strip()
        if decoded == "":
            break  # end of headers
        if ":" in decoded:
            key, value = decoded.split(":", 1)
            headers[key.strip()] = value.strip()

    length = int(headers.get("Content-Length", 0))
    if length == 0:
        return None

    body = await reader.readexactly(length)
    return json.loads(body)


def write_dap_message(writer: asyncio.StreamWriter, msg: dict) -> None:
    """Serialize and write one DAP message to *writer*."""
    body = json.dumps(msg, separators=(",", ":")).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    writer.write(header + body)


async def relay(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    hook: "asyncio.coroutines" = None,
    label: str = "",
    verbose: bool = False,
) -> None:
    """Forward DAP messages from *reader* to *writer*, calling *hook* on each."""
    try:
        while True:
            msg = await read_dap_message(reader)
            if msg is None:
                log.debug("relay %s: EOF", label)
                break
            if verbose:
                log.info("relay %s: %s", label, json.dumps(msg))
            if hook:
                await hook(msg)
            write_dap_message(writer, msg)
            await writer.drain()
    except (asyncio.IncompleteReadError, ConnectionError):
        log.debug("relay %s: connection closed", label)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="gz-dap-proxy",
        description="DAP proxy that pauses Gazebo Sim on breakpoints",
    )
    parser.add_argument(
        "--world",
        default=os.environ.get("GZ_WORLD_NAME", "default"),
        help="Gazebo world name (default: $GZ_WORLD_NAME or 'default')",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=1000,
        metavar="MS",
        help="gz service timeout in ms (default: 1000)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Log DAP messages to stderr",
    )
    parser.add_argument(
        "adapter_cmd",
        nargs=argparse.REMAINDER,
        metavar="-- ADAPTER_COMMAND [ARGS...]",
        help="Debug adapter command (after '--')",
    )
    args = parser.parse_args(argv)

    # Strip leading '--' from adapter_cmd
    cmd = args.adapter_cmd
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        parser.error("No adapter command provided. Usage: gz-dap-proxy [OPTIONS] -- <ADAPTER> [ARGS...]")
    args.adapter_cmd = cmd
    return args


async def run(args: argparse.Namespace) -> int:
    world = args.world
    timeout_ms = args.timeout
    verbose = args.verbose

    log.info("Starting adapter: %s", args.adapter_cmd)
    log.info("Gazebo world: %s (timeout: %dms)", world, timeout_ms)

    proc = await asyncio.create_subprocess_exec(
        *args.adapter_cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=sys.stderr,
    )

    # stdin/stdout of *this* process (the proxy)
    client_reader = asyncio.StreamReader()
    await asyncio.get_event_loop().connect_read_pipe(
        lambda: asyncio.StreamReaderProtocol(client_reader), sys.stdin.buffer
    )

    class StdoutWriter:
        """Minimal asyncio.StreamWriter-like wrapper around stdout."""
        def write(self, data: bytes) -> None:
            sys.stdout.buffer.write(data)
        async def drain(self) -> None:
            sys.stdout.buffer.flush()

    client_writer = StdoutWriter()

    async def on_adapter_message(msg: dict) -> None:
        """Intercept adapter → client messages."""
        if msg.get("type") == "event" and msg.get("event") == "stopped":
            log.info("Breakpoint hit — pausing Gazebo")
            await pause_simulation(world, timeout_ms)

    async def on_client_message(msg: dict) -> None:
        """Intercept client → adapter messages."""
        if msg.get("type") == "request" and msg.get("command") in RESUME_COMMANDS:
            log.info("Resume (%s) — unpausing Gazebo", msg["command"])
            await unpause_simulation(world, timeout_ms)

    # Run both relay loops concurrently
    adapter_to_client = relay(
        proc.stdout, client_writer,
        hook=on_adapter_message, label="adapter→client", verbose=verbose,
    )
    client_to_adapter = relay(
        client_reader, proc.stdin,
        hook=on_client_message, label="client→adapter", verbose=verbose,
    )

    done, pending = await asyncio.wait(
        [asyncio.ensure_future(adapter_to_client),
         asyncio.ensure_future(client_to_adapter)],
        return_when=asyncio.FIRST_COMPLETED,
    )

    # One side closed — clean up
    for task in pending:
        task.cancel()

    if proc.returncode is None:
        proc.terminate()
        await proc.wait()

    return proc.returncode or 0


def main() -> None:
    args = parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        stream=sys.stderr,
        level=level,
        format="[gz-dap-proxy] %(levelname)s %(message)s",
    )

    rc = asyncio.run(run(args))
    sys.exit(rc)


if __name__ == "__main__":
    main()
