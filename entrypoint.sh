#!/usr/bin/env bash
set -euo pipefail

RUN_PIPELINE="${RUN_PIPELINE:-0}"
DATA_DIR="${DATA_DIR:-/data}"
PORT="${STREAMLIT_SERVER_PORT:-8501}"

echo "[entrypoint] RUN_PIPELINE=${RUN_PIPELINE}  DATA_DIR=${DATA_DIR}  PORT=${PORT}"

# garantir diretório de dados
mkdir -p "${DATA_DIR}"

# deixar src no PYTHONPATH para o app
export PYTHONPATH="/app/src:${PYTHONPATH:-}"

# debug rápido do ambiente
python - <<'PY'
import sys, os
print("[debug] py:", sys.version.split()[0])
print("[debug] sys.path:", sys.path)
for p in ["/app", "/app/src", "/app/scripts", "/app/src/case_indicium"]:
    if os.path.isdir(p):
        print("[debug] dir:", p, "=>", sorted(os.listdir(p))[:20])
PY

run_step() {
  local step="$1"   # bronze | silver | gold
  echo "[entrypoint] procurando step '${step}'…"

  # 1) tentar módulo (só funciona se /app/scripts for pacote com __init__.py)
  local mod="scripts.run_${step}"
  echo "[entrypoint] tentando módulo: ${mod}"
  if python - <<PY
import importlib, sys
try:
    importlib.import_module("${mod}")
    print("OK-MODULE")
except Exception as e:
    print("ERR-MODULE", e.__class__.__name__)
    raise SystemExit(1)
PY
  then
    echo "[entrypoint] executando: python -m ${mod}"
    python -m "${mod}"
    return 0
  fi

  # 2) tentar como arquivo solto na raiz do projeto
  local file="/app/scripts/run_${step}.py"
  if [ -f "${file}" ]; then
    echo "[entrypoint] executando arquivo: ${file}"
    python "${file}"
    return 0
  fi

  echo "[entrypoint] ERRO: não encontrei o step '${step}' (módulo nem arquivo)."
  return 1
}

if [ "${RUN_PIPELINE}" = "1" ]; then
  echo "[entrypoint] Executando pipeline ETL (bronze -> silver -> gold)…"
  set -x
  run_step bronze
  run_step silver
  run_step gold
  set +x

  echo "[entrypoint] Pipeline concluído. Listando ${DATA_DIR}:"
  ls -lah "${DATA_DIR}" || true

  # Se este container é o 'etl', pode finalizar
  if [ "${ETL_EXIT_AFTER:=1}" = "1" ]; then
    echo "[entrypoint] ETL concluído. Saindo."
    exit 0
  fi
fi

echo "[entrypoint] Iniciando Streamlit na porta ${PORT}…"
exec streamlit run src/case_indicium/webapp/app.py --server.port="${PORT}" --server.address=0.0.0.0
