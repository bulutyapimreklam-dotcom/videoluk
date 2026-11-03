#!/bin/sh
set -eu

root_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
compose_file="$root_dir/deploy/compose.production.yaml"
env_file="$root_dir/.env"
backup_dir="${VIDEOLUK_BACKUP_DIR:-$root_dir/backups}"

command_name="${1:-help}"
case "$command_name" in
  validate)
    python3 "$root_dir/scripts/validate_env.py" "$env_file"
    docker compose --env-file "$env_file" -f "$compose_file" config >/dev/null
    ;;
  deploy)
    "$0" validate
    docker compose --env-file "$env_file" -f "$compose_file" up -d --build
    docker compose --env-file "$env_file" -f "$compose_file" ps
    ;;
  status)
    docker compose --env-file "$env_file" -f "$compose_file" ps
    docker compose --env-file "$env_file" -f "$compose_file" exec -T videoluk python -c "import json,urllib.request; print(json.dumps(json.load(urllib.request.urlopen('http://127.0.0.1:8787/api/health', timeout=5)), ensure_ascii=False, indent=2))"
    ;;
  logs)
    docker compose --env-file "$env_file" -f "$compose_file" logs --tail=200 -f videoluk caddy
    ;;
  backup)
    mkdir -p "$backup_dir"
    docker compose --env-file "$env_file" -f "$compose_file" run --rm --no-deps -v "$backup_dir:/backups" videoluk python scripts/backup_data.py --data /data --output /backups
    ;;
  help|*)
    echo "Kullanım: deploy/manage.sh {validate|deploy|status|logs|backup}"
    ;;
esac
