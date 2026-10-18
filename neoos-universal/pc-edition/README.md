# NeoOS PC Edition — first bootable ISO build

This directory defines the first reproducible build attempt for a minimal Debian 13 (trixie) amd64 live system under the NeoOS PC Edition name. The image is assembled by GitHub Actions; no PC or local build tools are required on the phone.

## Build it

1. Open the repository's **Actions** tab.
2. Select **Build NeoOS PC Edition ISO**.
3. Press **Run workflow** on `main`.
4. Wait for the workflow to finish successfully.
5. Open the completed run and download the `neoos-pc-edition-amd64-iso` artifact. It includes the ISO and its SHA-256 checksum.

A push to `main` that changes this directory or the build workflow also triggers a build.

## Scope of this first build

- Target architecture: x86-64 / amd64 PCs and compatible emulators.
- Base: Debian 13 (trixie) packages from the official Debian archive.
- Image type: hybrid live ISO, intended to boot into a minimal live system.
- Packages: basic shell, systemd, live-boot, networking tools, sudo and text utilities.
- Build output is a GitHub Actions artifact retained for 14 days; it is not yet a permanent public download/release.

## Honest status

The workflow is now defined, but the ISO is **not considered built until a workflow run succeeds**. Even a successful build does not prove that it boots on every physical PC. Next validation should boot the ISO in QEMU, then test target hardware. No disk installer or automatic repartitioning is included, so it cannot silently overwrite an existing operating system.

This is not yet the full NeoOS desktop, a universal boot manager, or a VM engine. Those are separate stages. This starter image is a concrete first step toward a real PC OS instead of a mock download page.

## Data and safety

The build runs in a disposable GitHub Actions runner and does not touch the user's phone, existing local data, Docker volumes, or any other repository. Only a downloadable build artifact is produced. The live system uses Debian packages and does not bundle proprietary Windows installation media.
