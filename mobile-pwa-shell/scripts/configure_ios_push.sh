#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DELEGATE="$ROOT_DIR/ios/App/App/AppDelegate.swift"
PROJECT_FILE="$ROOT_DIR/ios/App/App.xcodeproj/project.pbxproj"
ENTITLEMENTS_TARGET="$ROOT_DIR/ios/App/App/App.entitlements"
ENTITLEMENTS_TEMPLATE="$ROOT_DIR/native/apple/App.entitlements"
METHODS_TEMPLATE="$ROOT_DIR/native/apple/AppDelegatePushMethods.swift.inc"

for required_file in "$APP_DELEGATE" "$PROJECT_FILE" "$ENTITLEMENTS_TEMPLATE" "$METHODS_TEMPLATE"; do
  if [[ ! -f "$required_file" ]]; then
    echo "Missing required iOS file: $required_file" >&2
    exit 1
  fi
done

cp "$ENTITLEMENTS_TEMPLATE" "$ENTITLEMENTS_TARGET"

if ! grep -q "CHECKER_PUSH_NOTIFICATIONS" "$APP_DELEGATE"; then
  METHODS_CONTENT="$(<"$METHODS_TEMPLATE")" /usr/bin/perl -0pi -e \
    's/\n}\s*$/\n$ENV{"METHODS_CONTENT"}\n}\n/' \
    "$APP_DELEGATE"
fi

if ! grep -q "CODE_SIGN_ENTITLEMENTS = App/App.entitlements;" "$PROJECT_FILE"; then
  /usr/bin/perl -0pi -e \
    's/(CURRENT_PROJECT_VERSION = [^;]+;)/$1\n\t\t\t\tCODE_SIGN_ENTITLEMENTS = App\/App.entitlements;\n\t\t\t\tAPS_ENVIRONMENT = development;/g' \
    "$PROJECT_FILE"
fi

echo "Configured iOS Push Notifications capability."
