#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCHEME="${SCHEME:-App}"
CONFIGURATION="${CONFIGURATION:-Release}"
APP_BUNDLE_NAME="${APP_BUNDLE_NAME:-App.app}"
IPA_NAME="${IPA_NAME:-Checker-unsigned.ipa}"
MARKETING_VERSION="${MARKETING_VERSION:-4.0}"
BUILD_NUMBER="${BUILD_NUMBER:-4}"
PACKAGE_VERSION="${PACKAGE_VERSION:-4.0.0}"
BUILD_DIR="${BUILD_DIR:-$ROOT_DIR/build}"
ARCHIVE_PATH="${ARCHIVE_PATH:-$BUILD_DIR/App-unsigned.xcarchive}"
IPA_STAGING="$BUILD_DIR/ipa"
IPA_PATH="$BUILD_DIR/$IPA_NAME"

cd "$ROOT_DIR"

mkdir -p "$BUILD_DIR"

npm run sync:ios

PROJECT_FILE="$ROOT_DIR/ios/App/App.xcodeproj/project.pbxproj"
if [[ -f "$PROJECT_FILE" ]]; then
  MARKETING_VERSION="$MARKETING_VERSION" BUILD_NUMBER="$BUILD_NUMBER" /usr/bin/perl -0pi -e 's/CURRENT_PROJECT_VERSION = [^;]+;/CURRENT_PROJECT_VERSION = $ENV{"BUILD_NUMBER"};/g; s/MARKETING_VERSION = [^;]+;/MARKETING_VERSION = $ENV{"MARKETING_VERSION"};/g; s/TARGETED_DEVICE_FAMILY = [^;]+;/TARGETED_DEVICE_FAMILY = 1;/g;' "$PROJECT_FILE"
fi

set +e
xcodebuild -quiet \
  -workspace ios/App/App.xcworkspace \
  -scheme "$SCHEME" \
  -configuration "$CONFIGURATION" \
  -destination 'generic/platform=iOS' \
  -archivePath "$ARCHIVE_PATH" \
  clean archive \
  CODE_SIGNING_ALLOWED=NO \
  CODE_SIGNING_REQUIRED=NO \
  CODE_SIGN_IDENTITY=""
XCODEBUILD_STATUS=$?
set -e

if [[ "$XCODEBUILD_STATUS" -ne 0 ]]; then
  echo "xcodebuild failed; trying to repack the existing archive at $ARCHIVE_PATH"
fi

APP_PATH="$ARCHIVE_PATH/Products/Applications/$APP_BUNDLE_NAME"
if [[ ! -d "$APP_PATH" ]]; then
  echo "App bundle not found: $APP_PATH"
  exit "$XCODEBUILD_STATUS"
fi

/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $MARKETING_VERSION" "$APP_PATH/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleVersion $BUILD_NUMBER" "$APP_PATH/Info.plist"
/usr/libexec/PlistBuddy -c "Delete :UIDeviceFamily" "$APP_PATH/Info.plist" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Add :UIDeviceFamily array" "$APP_PATH/Info.plist"
/usr/libexec/PlistBuddy -c "Add :UIDeviceFamily:0 integer 1" "$APP_PATH/Info.plist"

if [[ -f "$APP_PATH/config.xml" ]]; then
  /usr/bin/sed -i '' -E "s/<widget version=\"[^\"]+\"/<widget version=\"$PACKAGE_VERSION\"/" "$APP_PATH/config.xml"
fi

/usr/libexec/PlistBuddy -c "Set :ApplicationProperties:CFBundleShortVersionString $MARKETING_VERSION" "$ARCHIVE_PATH/Info.plist" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Set :ApplicationProperties:CFBundleVersion $BUILD_NUMBER" "$ARCHIVE_PATH/Info.plist" 2>/dev/null || true

rm -rf "$IPA_STAGING" "$IPA_PATH"
mkdir -p "$IPA_STAGING/Payload"
cp -R "$APP_PATH" "$IPA_STAGING/Payload/"

(
  cd "$IPA_STAGING"
  /usr/bin/zip -qry "$IPA_PATH" Payload
)

echo "Unsigned IPA: $IPA_PATH"
