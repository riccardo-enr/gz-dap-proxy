"""Gazebo Sim pause/unpause via the gz CLI."""

import asyncio
import logging

log = logging.getLogger(__name__)


async def _gz_service(world: str, pause: bool, timeout_ms: int) -> None:
    action = "pause" if pause else "unpause"
    cmd = [
        "gz", "service",
        "-s", f"/world/{world}/control",
        "--reqtype", "gz.msgs.WorldControl",
        "--reptype", "gz.msgs.Boolean",
        "--timeout", str(timeout_ms),
        "--req", f"pause: {str(pause).lower()}",
    ]
    log.info("Gazebo %s: %s", action, " ".join(cmd))
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        log.warning(
            "gz service %s failed (rc=%d): %s",
            action, proc.returncode, stderr.decode().strip(),
        )
    else:
        log.debug("gz service %s ok: %s", action, stdout.decode().strip())


async def pause_simulation(world: str, timeout_ms: int = 1000) -> None:
    await _gz_service(world, pause=True, timeout_ms=timeout_ms)


async def unpause_simulation(world: str, timeout_ms: int = 1000) -> None:
    await _gz_service(world, pause=False, timeout_ms=timeout_ms)
