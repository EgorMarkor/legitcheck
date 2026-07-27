# Push notifications

`npm run sync:ios` installs the Capacitor Push Notifications plugin and applies
the APNs entitlement plus AppDelegate registration callbacks.

Before an App Store/TestFlight build:

1. Enable **Push Notifications** for the App ID `com.markor.legitcheck` in the
   Apple Developer portal and regenerate the signing profile if needed.
2. Configure the production backend with `APNS_KEY_ID`, `APNS_TEAM_ID`,
   `APNS_AUTH_KEY_PATH`, and `APNS_BUNDLE_ID`.
3. Put the APNs `.p8` key outside the repository at `APNS_AUTH_KEY_PATH`.
4. Run `npm run upload:ios:testflight` with the existing App Store Connect
   signing credentials. The upload script archives with
   `APS_ENVIRONMENT=production`.

The web app requests notification permission on native startup, registers the
APNs device token against the signed-in Checker account, and opens the relevant
verdict when a notification is tapped.
