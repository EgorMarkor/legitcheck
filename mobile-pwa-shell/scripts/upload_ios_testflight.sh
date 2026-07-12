#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCHEME="${SCHEME:-App}"
CONFIGURATION="${CONFIGURATION:-Release}"
TEAM_ID="${TEAM_ID:-XLXV36C393}"
BUNDLE_ID="${BUNDLE_ID:-com.markor.legitcheck}"
MARKETING_VERSION="${MARKETING_VERSION:-4.0}"
BUILD_NUMBER="${BUILD_NUMBER:-4}"
BUILD_DIR="${BUILD_DIR:-$ROOT_DIR/build}"
ARCHIVE_PATH="${ARCHIVE_PATH:-$BUILD_DIR/App-store.xcarchive}"
EXPORT_PATH="${EXPORT_PATH:-$BUILD_DIR/AppStoreUpload}"
EXPORT_OPTIONS="$BUILD_DIR/ExportOptions-appstore.plist"

cd "$ROOT_DIR"
mkdir -p "$BUILD_DIR"

npm run sync:ios

PROJECT_FILE="$ROOT_DIR/ios/App/App.xcodeproj/project.pbxproj"
if [[ -f "$PROJECT_FILE" ]]; then
  MARKETING_VERSION="$MARKETING_VERSION" BUILD_NUMBER="$BUILD_NUMBER" /usr/bin/perl -0pi -e 's/CURRENT_PROJECT_VERSION = [^;]+;/CURRENT_PROJECT_VERSION = $ENV{"BUILD_NUMBER"};/g; s/MARKETING_VERSION = [^;]+;/MARKETING_VERSION = $ENV{"MARKETING_VERSION"};/g; s/TARGETED_DEVICE_FAMILY = [^;]+;/TARGETED_DEVICE_FAMILY = 1;/g;' "$PROJECT_FILE"
fi

AUTH_FLAGS=()
if [[ -n "${ASC_KEY_PATH:-}" || -n "${ASC_KEY_ID:-}" || -n "${ASC_ISSUER_ID:-}" ]]; then
  if [[ -z "${ASC_KEY_PATH:-}" || -z "${ASC_KEY_ID:-}" || -z "${ASC_ISSUER_ID:-}" ]]; then
    echo "Set ASC_KEY_PATH, ASC_KEY_ID, and ASC_ISSUER_ID together."
    exit 1
  fi
  AUTH_FLAGS=(
    -authenticationKeyPath "$ASC_KEY_PATH"
    -authenticationKeyID "$ASC_KEY_ID"
    -authenticationKeyIssuerID "$ASC_ISSUER_ID"
  )
fi

rm -rf "$ARCHIVE_PATH" "$EXPORT_PATH"

xcodebuild \
  -workspace ios/App/App.xcworkspace \
  -scheme "$SCHEME" \
  -configuration "$CONFIGURATION" \
  -destination 'generic/platform=iOS' \
  -archivePath "$ARCHIVE_PATH" \
  -allowProvisioningUpdates \
  "${AUTH_FLAGS[@]}" \
  DEVELOPMENT_TEAM="$TEAM_ID" \
  MARKETING_VERSION="$MARKETING_VERSION" \
  CURRENT_PROJECT_VERSION="$BUILD_NUMBER" \
  CODE_SIGN_STYLE=Automatic \
  clean archive

cat > "$EXPORT_OPTIONS" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>destination</key>
  <string>upload</string>
  <key>method</key>
  <string>app-store-connect</string>
  <key>signingStyle</key>
  <string>automatic</string>
  <key>teamID</key>
  <string>$TEAM_ID</string>
  <key>manageAppVersionAndBuildNumber</key>
  <false/>
  <key>uploadSymbols</key>
  <true/>
</dict>
</plist>
EOF

xcodebuild \
  -exportArchive \
  -archivePath "$ARCHIVE_PATH" \
  -exportPath "$EXPORT_PATH" \
  -exportOptionsPlist "$EXPORT_OPTIONS" \
  -allowProvisioningUpdates \
  "${AUTH_FLAGS[@]}"

echo "Upload submitted from archive: $ARCHIVE_PATH"
