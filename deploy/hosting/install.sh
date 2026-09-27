#!/bin/bash
# Install the hosting pack's units and config onto a provisioned host (run as
# root from /opt/sports-predictor). Idempotent. ENABLES NOTHING: timers are
# enabled one by one in hosting-h1.md step T11, after the migration receipts.
set -euo pipefail
cd "$(dirname "$0")"
install -d -m 0755 /etc/sports-predictor
install -d -o sp -g sp -m 0750 /var/log/sports-predictor /var/lib/sports-predictor
install -d -o sp -g sp -m 0700 /var/backups/sports-predictor
[ -e /etc/sports-predictor/host.env ] || install -o root -g sp -m 0640 etc/host.env.example /etc/sports-predictor/host.env
[ -e /etc/sports-predictor/fullseason.list ] || install -o root -g sp -m 0640 etc/fullseason.list.example /etc/sports-predictor/fullseason.list
install -m 0644 etc/52sp-unattended-upgrades /etc/apt/apt.conf.d/52sp-unattended-upgrades
install -m 0644 etc/logrotate-sports-predictor /etc/logrotate.d/sports-predictor
install -m 0644 systemd/*.service systemd/*.timer /etc/systemd/system/
systemctl daemon-reload
echo "✓ installed $(ls systemd | wc -l) unit files; NOTHING enabled."
systemctl list-unit-files 'sp-*' --no-pager
