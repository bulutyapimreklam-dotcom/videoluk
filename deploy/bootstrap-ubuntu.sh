#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Bu betik root olarak çalıştırılmalı." >&2
  exit 1
fi

app_user="videoluk"
app_root="/opt/videoluk"
repo_url="${VIDEOLUK_REPO_URL:-https://github.com/bulutyapimreklam-dotcom/videoluk.git}"

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl git ufw fail2ban unattended-upgrades gnupg

install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
. /etc/os-release
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

if ! id "$app_user" >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash "$app_user"
fi
usermod -aG docker "$app_user"

if [ ! -d "$app_root/.git" ]; then
  git clone "$repo_url" "$app_root"
fi
chown -R "$app_user:$app_user" "$app_root"

ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

systemctl enable --now docker fail2ban
dpkg-reconfigure -f noninteractive unattended-upgrades

if ! swapon --show | grep -q .; then
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

cat > /etc/logrotate.d/videoluk-docker <<'EOF'
/var/lib/docker/containers/*/*.log {
  rotate 7
  daily
  compress
  size 50M
  missingok
  delaycompress
  copytruncate
}
EOF

echo
echo "Sunucu temeli hazır. Sonraki adımlar:"
echo "1. $app_root/.env.example dosyasını $app_root/.env olarak kopyalayın ve gerçek değerleri girin."
echo "2. DNS A kaydını bu sunucunun IPv4 adresine yönlendirin."
echo "3. sudo -u $app_user $app_root/deploy/manage.sh deploy komutunu çalıştırın."
