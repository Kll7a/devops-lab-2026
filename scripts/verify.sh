#!/usr/bin/env bash
# Проверка, что стенд собран так, как мы задумали.
# Возвращает 0, если всё хорошо, иначе — число провалившихся проверок.
set -euo pipefail

RED=$'\e[31m'; GREEN=$'\e[32m'; YELLOW=$'\e[33m'; RESET=$'\e[0m'
FAILED=0

check() {
  local name="$1"; shift
  if "$@" >/dev/null 2>&1; then
    printf '  %s✓%s %s\n' "$GREEN" "$RESET" "$name"
  else
    printf '  %s✗%s %s\n' "$RED" "$RESET" "$name"
    FAILED=$((FAILED + 1))
  fi
}

section() { printf '\n%s== %s ==%s\n' "$YELLOW" "$1" "$RESET"; }

section "Инструменты"
for bin in podman buildah skopeo git jq helm kubectl k3s uv; do
  check "$bin установлен" command -v "$bin"
done

section "Ядро и ОС"
check "swap выключен"        bash -c '[[ $(free -m | awk "/Swap/ {print \$2}") -eq 0 ]]'
check "ip_forward включён"   bash -c '[[ $(sysctl -n net.ipv4.ip_forward) == 1 ]]'
check "SELinux в enforcing"  bash -c '[[ $(getenforce) == "Enforcing" ]]'
check "firewalld активен"    systemctl is-active --quiet firewalld

section "Контейнеры"
check "podman запускает контейнер" podman run --rm docker.io/library/alpine:3 true

section "Kubernetes"
check "служба k3s активна"   systemctl is-active --quiet k3s
check "API отвечает"         kubectl version
check "нода Ready"           bash -c 'kubectl get nodes --no-headers | grep -qw Ready'
check "системные поды живы"  bash -c '! kubectl get pods -n kube-system --no-headers | grep -Eq "Error|CrashLoop"'

printf '\n'
if (( FAILED == 0 )); then
  printf '%sВсе проверки пройдены.%s\n' "$GREEN" "$RESET"
else
  printf '%sПровалено проверок: %d%s\n' "$RED" "$FAILED" "$RESET"
fi
exit "$FAILED"
