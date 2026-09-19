#!/bin/sh
# ClippyMe container entrypoint.
#
# The image runs as root ONLY long enough to normalize ownership of the
# writable, bind-mountable dirs, then drops to the unprivileged appuser.
#
# A host bind mount (./data:/app/data) or a prior `-u root` invocation can leave
# data/ owned by a UID the non-root appuser (999) cannot traverse — that is the
# cause of the `Permission denied: data/config.json` and `data/cache` failures.
# Re-chowning on every boot makes the container self-healing regardless of how
# the host directory got locked.
#
# The privilege drop happens ONLY for the default `uvicorn` server command, so
# `docker compose run --rm -u root backend sh -lc "..."` (the documented
# integration-test path) still gets a real root shell.
set -e

if [ "$(id -u)" = "0" ] && [ "${1:-}" = "uvicorn" ]; then
    # ROCm devices keep the host's numeric group IDs inside the container.
    # Add appuser to those exact groups at boot instead of assuming Ubuntu's
    # video/render GIDs match the host. CPU/NVIDIA containers simply skip this.
    for gpu_device in /dev/kfd /dev/dri/renderD128; do
        if [ -e "$gpu_device" ]; then
            gpu_gid="$(stat -c '%g' "$gpu_device")"
            gpu_group="$(getent group "$gpu_gid" | cut -d: -f1)"
            if [ -z "$gpu_group" ]; then
                gpu_group="clippyme-gpu-$gpu_gid"
                groupadd -g "$gpu_gid" "$gpu_group"
            fi
            usermod -aG "$gpu_group" appuser
        fi
    done

    for d in /app/data /app/output /app/uploads /app/.cache /app/.config /app/data/cache; do
        mkdir -p "$d"
    done
    # data/ is small (config, cookies, cache, fonts, bin) — safe to recurse.
    chown -R appuser:appuser /app/data /app/.cache /app/.config 2>/dev/null || true
    chmod 777 /app/.cache /app/.config 2>/dev/null || true
    # output/ and uploads/ can be large; their contents are already
    # appuser-created, so only the top-level dir needs fixing.
    chown appuser:appuser /app/output /app/uploads 2>/dev/null || true

    export HF_HOME=/app/data/cache/huggingface
    export MPLCONFIGDIR=/app/data/cache/matplotlib
    export TORCH_HOME=/app/data/cache/torch

    exec gosu appuser "$@"
fi

exec "$@"
