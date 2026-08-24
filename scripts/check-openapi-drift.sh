#!/usr/bin/env bash
# Проверяет, что app/openapi.json совпадает со схемой, которую генерирует код.
set -euo pipefail

cd "$(dirname "$0")/.."
python - <<'PY' > /tmp/openapi-generated.json
import json, sys
sys.path.insert(0, "app")
from src.main import app
json.dump(app.openapi(), sys.stdout, indent=2, sort_keys=True)
PY

if ! diff -u app/openapi.json /tmp/openapi-generated.json; then
  echo
  echo "ОШИБКА: app/openapi.json устарел."
  echo "Выполните 'make spec' и закоммитьте результат."
  exit 1
fi
echo "OpenAPI-схема актуальна."
