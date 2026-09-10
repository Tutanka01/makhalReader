#!/bin/sh
# Entrypoint for the API container.
#
# The container starts as root only to ensure the mounted /data volume is
# writable by the unprivileged app user (volumes created by older, root-running
# images are root-owned). It then immediately drops privileges with setpriv
# (from util-linux, already present in the slim base image).
set -e

APP_USER="app"

if [ "$(id -u)" = "0" ]; then
    if [ -d /data ]; then
        chown -R "$APP_USER:$APP_USER" /data
    fi
    exec setpriv --reuid="$APP_USER" --regid="$APP_USER" --init-groups -- "$@"
fi

exec "$@"
