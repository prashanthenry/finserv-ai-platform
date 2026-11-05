#!/usr/bin/env bash
# No GitHub token or AWS access key is stored in user data.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl git jq unzip docker.io python3 python3-venv
systemctl enable --now docker

if ! snap list amazon-ssm-agent >/dev/null 2>&1; then
  snap install amazon-ssm-agent --classic
fi
snap start amazon-ssm-agent
snap install aws-cli --classic
ln -sf /snap/bin/aws /usr/local/bin/aws
ln -sf /usr/bin/python3 /usr/local/bin/python

id gha-runner >/dev/null 2>&1 || useradd --create-home --shell /bin/bash gha-runner
usermod -aG docker gha-runner
install -d -o gha-runner -g gha-runner /opt/actions-runner
install -d -o gha-runner -g gha-runner /opt/actions-runner/_work/_tool

runner_version=2.338.2
runner_sha256=baebf204307bac6193480852732f0aba2ae97b6c5597c244f4d5558390147c40
package="/tmp/actions-runner-linux-x64-${runner_version}.tar.gz"
curl --fail --location --retry 5 \
  "https://github.com/actions/runner/releases/download/v${runner_version}/actions-runner-linux-x64-${runner_version}.tar.gz" \
  --output "$package"
printf '%s  %s\n' "$runner_sha256" "$package" | sha256sum --check -
tar -xzf "$package" -C /opt/actions-runner
/opt/actions-runner/bin/installdependencies.sh
printf '%s\n' 'RUNNER_TOOL_CACHE=/opt/actions-runner/_work/_tool' > /opt/actions-runner/.env
chown -R gha-runner:gha-runner /opt/actions-runner
rm -f "$package"
touch /var/lib/github-runner-ready
echo "Runner software ready. Register from a Session Manager administrator session."
