#!/usr/bin/env bash
# Runs on EC2 as root from inside the unpacked build (started through SSM).
# Usage: deploy.sh <build-name>
set -euo pipefail

name=$1
src=$(cd "$(dirname "$0")" && pwd)
root=/opt/ticketq
release="$root/releases/$name"

command -v python3.12 > /dev/null || { echo "python3.12 is missing" >&2; exit 1; }

id ticketq &> /dev/null || useradd --system --no-create-home --shell /sbin/nologin ticketq
install -d "$root/releases"
install -d -o ticketq -g ticketq -m 750 /var/lib/ticketq

previous=$(readlink -f "$root/current" || true)
[[ -d $previous ]] || previous=""

# Re-deploying the running build must not delete it first.
if [[ $previous != "$release" ]]; then
  rm -rf "$release"
  cp -r "$src/app" "$release"
  python3.12 -m venv "$release/venv"
  "$release/venv/bin/pip" install --quiet --no-index --find-links "$src/wheels" -r "$release/requirements-aws.txt"
  ln -s /var/lib/ticketq/booking.db "$release/booking.db" # data survives deployments
  chmod -R a+rX "$release"

  install -m 644 "$src/ticketq.service" /etc/systemd/system/ticketq.service
  systemctl daemon-reload
  systemctl enable --quiet ticketq
  ln -sfn "$release" "$root/current"
fi
systemctl restart ticketq || true # the health check below decides

expected=$(cat "$release/BUILD")
for _ in {1..20}; do
  if curl -fs --max-time 3 http://127.0.0.1/health | grep -qF "$expected"; then
    echo "Deployed $name"
    touch "$release"
    # Keep the three newest releases.
    # shellcheck disable=SC2012 # build names are validated, no odd characters
    ls -1dt "$root"/releases/*/ | tail -n +4 | xargs -r rm -rf
    exit 0
  fi
  sleep 2
done

echo "Health check failed for $name" >&2
journalctl -u ticketq -n 30 --no-pager >&2 || true
if [[ -n $previous && $previous != "$release" ]]; then
  echo "Rolling back to $(basename "$previous")" >&2
  ln -sfn "$previous" "$root/current"
  systemctl restart ticketq
fi
exit 1
