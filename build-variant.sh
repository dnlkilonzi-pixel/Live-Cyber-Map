#!/usr/bin/env bash
# build-variant.sh – Build a themed variant of the Global Intelligence Dashboard.
#
# Usage:
#   ./build-variant.sh cyber           # web build for the cyber variant
#   ./build-variant.sh tech --desktop  # desktop (Tauri) build for the tech variant
#   ./build-variant.sh finance --desktop
#
# Variants: cyber | tech | finance

set -euo pipefail

VARIANT="${1:-cyber}"
DESKTOP="${2:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VARIANT_DIR="$SCRIPT_DIR/variants/$VARIANT"
FRONTEND_DIR="$SCRIPT_DIR/frontend"

if [[ ! -d "$VARIANT_DIR" ]]; then
  echo "❌ Unknown variant: $VARIANT"
  echo "   Available variants: cyber | tech | finance"
  exit 1
fi

echo "🔨 Building variant: $VARIANT"
echo "   Theme config: $VARIANT_DIR/theme.json"

# ── Export variant env vars ──────────────────────────────────────────────────
export NEXT_PUBLIC_VARIANT_ID="$VARIANT"
export NEXT_PUBLIC_VARIANT_THEME="$VARIANT"

# Read branding from theme.json (requires jq)
if command -v jq &>/dev/null; then
  APP_TITLE=$(jq -r '.branding.topBarText // "GLOBAL INTEL"' "$VARIANT_DIR/theme.json")
  SUBTITLE=$(jq -r '.branding.subtitle // ""' "$VARIANT_DIR/theme.json")
  export NEXT_PUBLIC_APP_TITLE="$APP_TITLE"
  export NEXT_PUBLIC_SUBTITLE="$SUBTITLE"
fi

# ── Install frontend dependencies ────────────────────────────────────────────
echo "📦 Installing frontend dependencies…"
cd "$FRONTEND_DIR"
npm ci --quiet

# ── Web build ────────────────────────────────────────────────────────────────
echo "🌐 Building Next.js for variant: $VARIANT…"
npm run build

OUT_DIR="$SCRIPT_DIR/dist/$VARIANT"
mkdir -p "$OUT_DIR"

if [[ -d "$FRONTEND_DIR/.next" ]]; then
  echo "✅ Next.js build complete → $FRONTEND_DIR/.next"
fi

# ── Desktop build (Tauri) ────────────────────────────────────────────────────
if [[ "$DESKTOP" == "--desktop" ]]; then
  echo "🖥️  Building Tauri desktop app for variant: $VARIANT…"

  if ! command -v cargo &>/dev/null; then
    echo "❌ Rust/Cargo not found. Install from https://rustup.rs"
    exit 1
  fi

  if ! command -v npm &>/dev/null; then
    echo "❌ Node/npm not found."
    exit 1
  fi

  # Install @tauri-apps/cli if not present
  cd "$SCRIPT_DIR"
  if ! npx --no-install @tauri-apps/cli info &>/dev/null 2>&1; then
    npm install --save-dev @tauri-apps/cli@1 --quiet
  fi

  # Build Tauri bundle
  npx @tauri-apps/cli build

  echo "✅ Desktop build complete"
  echo "   Bundles in: src-tauri/target/release/bundle/"
fi

echo ""
echo "✅ Variant '$VARIANT' build complete."
if [[ "$DESKTOP" != "--desktop" ]]; then
  echo "   To run locally: cd frontend && npm run start"
  echo "   To build desktop: ./build-variant.sh $VARIANT --desktop"
fi
