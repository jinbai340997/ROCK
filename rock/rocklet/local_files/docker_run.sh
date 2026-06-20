#!/bin/bash
set -o errexit

port=$1

# Log directory: use /tmp if the user is not root, in case of permission issues
if [ "$(whoami)" != "root" ]; then
    LOG_DIR="/tmp/data/logs"
else
    LOG_DIR="/data/logs"
fi

is_musl() {
    if ldd --version 2>&1 | grep -q musl; then
        echo "true"
    elif [ -e /lib/ld-musl-x86_64.so.1 ] || [ -e /lib/ld-musl-aarch64.so.1 ] && [ ! -f /usr/glibc-compat/lib/libc.so.6 ]; then
        echo "true"
    else
        echo "false"
    fi
}

is_nix() {
    if [ -d /nix/store ]; then
        echo "true"
    else
        echo "false"
    fi
}

# Kata DinD: set up loop device and mount disk image for Docker storage
setup_kata_dind() {
    local docker_root="/var/lib/docker"
    if [ -f /etc/docker/daemon.json ]; then
        local custom_root
        custom_root=$(grep -o '"data-root"[[:space:]]*:[[:space:]]*"[^"]*"' /etc/docker/daemon.json | sed 's/.*"data-root"[[:space:]]*:[[:space:]]*"\([^"]*\)"/\1/')
        if [ -n "$custom_root" ]; then
            docker_root="$custom_root"
        fi
    fi
    mkdir -p "$docker_root"
    for i in $(seq 0 7); do
        mknod -m 660 /dev/loop$i b 7 $i 2>/dev/null || true
    done
    mount -o loop /docker-disk.img "$docker_root"
    mount -o remount,rw /sys/fs/cgroup
    mount -o remount,rw /proc/sys

    # Inject insecure-registries for DinD mirror proxy.
    # ROCK_DIND_INSECURE_REGISTRIES is a comma-separated list of ACR domains
    # injected by the admin _apply_dind_mirror_hosts() when the proxy is enabled.
    if [ -n "${ROCK_DIND_INSECURE_REGISTRIES:-}" ]; then
        local DAEMON_JSON="/etc/docker/daemon.json"
        # Build a JSON array from the CSV: "a,b" → ["a","b"]
        local INSECURE_JSON
        INSECURE_JSON=$(echo "$ROCK_DIND_INSECURE_REGISTRIES" | \
            tr ',' '\n' | sed 's/^/"/;s/$/"/' | paste -sd',' - | sed 's/^/[/;s/$/]/')

        if [ -f "$DAEMON_JSON" ]; then
            if command -v jq &>/dev/null; then
                jq --argjson new "$INSECURE_JSON" \
                    '.["insecure-registries"] = ((.["insecure-registries"] // []) + $new | unique)' \
                    "$DAEMON_JSON" > /tmp/daemon.merged.json && mv /tmp/daemon.merged.json "$DAEMON_JSON"
            elif command -v python3 &>/dev/null; then
                python3 -c "
import json
with open('$DAEMON_JSON') as f: d = json.load(f)
d.setdefault('insecure-registries', []).extend(json.loads('$INSECURE_JSON'))
d['insecure-registries'] = list(set(d['insecure-registries']))
with open('$DAEMON_JSON', 'w') as f: json.dump(d, f, indent=2)
"
            elif command -v python &>/dev/null; then
                python -c "
import json
with open('$DAEMON_JSON') as f: d = json.load(f)
d.setdefault('insecure-registries', []).extend(json.loads('$INSECURE_JSON'))
d['insecure-registries'] = list(set(d['insecure-registries']))
with open('$DAEMON_JSON', 'w') as f: json.dump(d, f, indent=2)
"
            else
                echo "WARNING: no jq or python available, creating new daemon.json"
                echo "{\"insecure-registries\": $INSECURE_JSON}" > "$DAEMON_JSON"
            fi
        else
            mkdir -p /etc/docker
            echo "{\"insecure-registries\": $INSECURE_JSON}" > "$DAEMON_JSON"
        fi
        echo "DinD insecure-registries injected: $ROCK_DIND_INSECURE_REGISTRIES"
    fi
}

# Run rocklet
if [ "$(is_nix)" = "true" ]; then
    # NixOS
    ln -sf $(ls -d /nix/store/*glibc*/lib 2>/dev/null | head -1) /lib
    ln -sf $(ls -d /nix/store/*glibc*/lib64 2>/dev/null | head -1) /lib64
    mkdir -p /bin
    ln -sf $(ls -d /nix/store/*bash*/bin/bash 2>/dev/null | head -1) /bin/bash
    ln -sf $(ls -d /nix/store/*util-linux*/bin/mount 2>/dev/null | head -1) /bin/mount
    export PATH="/bin:${PATH}"
    GCC_LIB=$(ls -d /nix/store/*gcc*lib/lib 2>/dev/null | head -1)
    ZLIB_LIB=$(ls -d /nix/store/*zlib*/lib 2>/dev/null | head -1)
    NIX_LIBS=""
    [ -n "$GCC_LIB" ] && NIX_LIBS="${GCC_LIB}:"
    [ -n "$ZLIB_LIB" ] && NIX_LIBS="${NIX_LIBS}${ZLIB_LIB}:"
    [ -n "$NIX_LIBS" ] && export LD_LIBRARY_PATH="${NIX_LIBS}${LD_LIBRARY_PATH}"
fi

if [ "${ROCK_KATA_RUNTIME}" = "true" ]; then
    echo "Kata runtime detected, setting up DinD disk..."
    setup_kata_dind
fi

if [ "$(is_musl)" = "true" ]; then
    # musl-based distributions
    if [ ! -d /tmp/local_files/alpine_glibc ]; then
        echo "Alpine Linux system is not supported yet"
        exit 1
    fi

    sed -i "s|https://.*alpinelinux.org|https://mirrors.aliyun.com|g" /etc/apk/repositories
    apk add bash
    apk add --allow-untrusted --force-overwrite /tmp/local_files/alpine_glibc/*.apk
    mkdir -p /lib64
    ln -sf /usr/glibc-compat/lib/ld-linux-x86-64.so.2 /lib64/ld-linux-x86-64.so.2
    ln -sf /usr/glibc-compat/lib/ld-linux-x86-64.so.2 /lib/ld-linux-x86-64.so.2
    mkdir -p "${LOG_DIR}"
    /tmp/miniforge/bin/rocklet --port ${port} >> "${LOG_DIR}/rocklet_uvicorn.log" 2>&1
else
    # glibc-based distributions
    mkdir -p "${LOG_DIR}"
    /tmp/miniforge/bin/rocklet --port ${port} >> "${LOG_DIR}/rocklet_uvicorn.log" 2>&1
fi