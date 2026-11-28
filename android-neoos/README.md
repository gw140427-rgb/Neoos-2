# NeoOS Android Native Control Center

This is a native Android application written in Kotlin and Jetpack Compose. It is no longer an app launcher for Termux, a VM app, or Heybon.

## Current native features

- Native dashboard and connection settings.
- HTTPS connection to a configured NeoOS API endpoint.
- Health check using `GET /health`.
- VPS inventory using `GET /api/instances`.
- Optional Bearer token entered at runtime. The token is not persisted.
- Server address is stored locally in app preferences.

## API requirements

The configured server must be reachable from the phone over HTTPS and implement:
- `GET /health`
- `GET /api/instances`

The documented AWS backend currently binds to loopback on its host and requires a separately configured HTTPS reverse proxy or secure SSM tunnel. This Android app does not bypass that network restriction and does not contain AWS credentials.

## Android behavior and limits

- The app can be selected as the Android Home app, but it cannot replace Samsung firmware, the bootloader, or Android itself.
- Android requires the user to approve installation of an APK.
- No existing NeoOS, VM, Debian, or phone data is deleted or modified by this app.

## Build

The GitHub Actions workflow builds a debug APK with JDK 17 and Gradle 8.9. The APK is published as the `neoos-android-debug-apk` workflow artifact after a successful build.
