#!/bin/sh
# Installation du Content Engine (macOS / Linux). Relançable sans risque.
# Usage : ouvre un Terminal dans ce dossier puis :  ./setup.sh
set -e
cd "$(dirname "$0")"

say() { printf '\n\033[1m%s\033[0m\n' "$1"; }
ok() { printf '  \033[32mOK\033[0m  %s\n' "$1"; }
warn() { printf '  \033[33m--\033[0m  %s\n' "$1"; }

say "1/5  Environnement Python (.venv)"
if command -v uv >/dev/null 2>&1; then
  [ -x .venv/bin/python ] || uv venv --python 3.12 .venv
  uv pip install --python .venv/bin/python -e ".[dev]"
else
  PY=""
  for c in python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then PY="$c"; break; fi
  done
  if [ -z "$PY" ]; then
    echo "Python 3.10+ introuvable. Installe uv (recommandé) puis relance :"
    echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
  fi
  [ -x .venv/bin/python ] || "$PY" -m venv .venv
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -e ".[dev]"
fi
ok "dépendances installées"

say "2/5  Fichier de clés (.env)"
if [ -f .env ]; then ok ".env existe déjà (non modifié)"; else cp .env.example .env && chmod 600 .env && ok ".env créé depuis .env.example"; fi

say "3/5  Outils externes"
chmod +x bin/engine
if command -v ffmpeg >/dev/null 2>&1; then ok "ffmpeg"; else warn "ffmpeg absent (analyse vidéo + Hook Lab) → macOS : brew install ffmpeg"; fi
if command -v claude >/dev/null 2>&1 || [ -x "$HOME/.local/bin/claude" ]; then ok "Claude Code (claude)";
else warn "Claude Code absent → installe-le (voir GUIDE.md § 2), puis lance « claude » une fois pour te connecter"; fi
if [ -d "/Applications/Google Chrome.app" ] || command -v google-chrome >/dev/null 2>&1; then ok "Google Chrome (comptes scout)";
else warn "Google Chrome absent → comptes scout via Chromium : .venv/bin/python -m playwright install chromium"; fi

say "4/5  Tests"
.venv/bin/python -m pytest -q tests || warn "un test a échoué : l'installation continue, signale-le"

say "5/5  Diagnostic"
./bin/engine doctor || true

say "Installation terminée."
echo "Étape suivante : configure ton identité (GUIDE.md § 3), puis lance le dashboard :  ./bin/engine ui"
