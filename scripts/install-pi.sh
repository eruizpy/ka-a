#!/usr/bin/env bash
# Install application services; this script never enables real pumps or starts services.
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Run this installer with sudo on the target Raspberry Pi." >&2
  exit 1
fi
if [[ ! -f /proc/device-tree/model ]] || ! grep -q 'Raspberry Pi 4' /proc/device-tree/model; then
  echo "This installation profile supports Raspberry Pi 4 only." >&2
  exit 1
fi
python3 -c 'import sys; assert sys.version_info >= (3, 11), "Python 3.11+ required"'
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

apt-get update
apt-get install -y python3-venv python3-dev python3-lgpio python3-smbus i2c-tools rsync
id kaa >/dev/null 2>&1 || useradd --system --home-dir /var/lib/kaa --shell /usr/sbin/nologin kaa
usermod -aG gpio,i2c kaa
install -d -o root -g root -m 0755 /opt/kaa
install -d -o root -g kaa -m 0750 /etc/kaa
install -d -o kaa -g kaa -m 0700 /var/lib/kaa
rsync -a --chmod=D755,F644 --exclude=.git --exclude=.venv --exclude=data \
  --exclude=artifacts --exclude=certs --exclude=config.local.yaml --exclude=.env \
  --exclude=.pytest_cache --exclude=.ruff_cache --exclude=__pycache__ \
  "${project_dir}/" /opt/kaa/
python3 -m venv --system-site-packages /opt/kaa/.venv
/opt/kaa/.venv/bin/python -m pip install --upgrade pip
/opt/kaa/.venv/bin/python -m pip install -c /opt/kaa/constraints.txt '/opt/kaa[hardware,aws]'

if [[ ! -f /etc/kaa/config.yaml ]]; then
  /opt/kaa/.venv/bin/python -c 'import yaml; from pathlib import Path; p=Path("/opt/kaa/config.example.yaml"); c=yaml.safe_load(p.read_text()); c["data_dir"]="/var/lib/kaa"; Path("/etc/kaa/config.yaml").write_text(yaml.safe_dump(c,sort_keys=False))'
  chown root:kaa /etc/kaa/config.yaml
  chmod 0640 /etc/kaa/config.yaml
fi
if [[ ! -f /etc/kaa/environment ]]; then
  printf '%s\n' 'KAA_ENABLE_HARDWARE=NO' > /etc/kaa/environment
  chown root:kaa /etc/kaa/environment
  chmod 0640 /etc/kaa/environment
fi
install -m 0644 /opt/kaa/deploy/kaa-web.service /etc/systemd/system/kaa-web.service
install -m 0644 /opt/kaa/deploy/kaa-controller.service /etc/systemd/system/kaa-controller.service
systemctl daemon-reload
echo "Installed in SIMULATION mode. Services were not started."
echo "Read /opt/kaa/docs/RASPBERRY_PI.md, then create your administrator password:"
echo "sudo -u kaa /opt/kaa/.venv/bin/kaa --config /etc/kaa/config.yaml setup"
