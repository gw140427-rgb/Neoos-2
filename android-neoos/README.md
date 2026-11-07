# NeoOS Android Launcher

An Android home-screen launcher for the NeoOS mobile environment.

## What it does

- Presents a full-screen NeoOS home screen.
- Offers launch cards for NeoOS VM, Termux, and Heybon.
- Stores each target application's Android package name locally.
- Declares itself as an Android HOME app so the system can start it as the home screen after boot.

## Important Android behavior

A normal Android app cannot replace Samsung's bootloader or start before Android. It also cannot reliably force another app's activity to the foreground from a background boot receiver on modern Android versions.

For automatic startup, install this app and select **NeoOS** as the device's default Home app. Android will then show NeoOS when it starts the Home screen after boot. The user can switch back to One UI Home in Android's Home app settings.

The immersive UI hides the status and navigation bars, but Android may reveal system bars with an edge swipe. This is not a replacement for device-owner lock-task/kiosk management.

## Build

Open the `android-neoos` directory in Android Studio, allow Gradle sync, then build the app:

```bash
./gradlew assembleDebug
```

The project currently does not include a Gradle wrapper. Android Studio can generate/use its configured Gradle installation, or a wrapper can be added from an installed Gradle distribution.

## Configure app targets

Open **환경 설정** in NeoOS and enter the Android package names for the VM app and Heybon app. Termux defaults to `com.termux`.

The launcher does not guess package IDs or install other apps. A launch card reports an error if its configured target is not installed or does not expose a launcher activity.
