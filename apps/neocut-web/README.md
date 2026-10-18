# NeoCut Web MVP

NeoCut is an independent, free-first video editor prototype in the NeoOS-2 repository.

## Run
Open `index.html` in a modern browser, or serve this folder with any static web host. No build step, account, API key, or server-side upload is required.

## Implemented
- Local video import and preview
- Start/end range preview
- Caption overlay with text, size, and color
- Experimental browser export to WebM with caption overlay

## Current limitations
- This is an early MVP, not a complete CapCut replacement.
- Export depends on browser MediaRecorder/canvas support and may fail for some codecs or large videos.
- Exported video is WebM, not MP4; source audio is not mixed into the canvas recording yet.
- The trim range is used for preview/export but there is no multi-clip timeline, transitions, filters, project persistence, or AI subtitle generation yet.
- Android APK, Windows installer, and Linux desktop packages are not built by this web-only folder yet.

## Roadmap
1. Add automated checks and safer export lifecycle handling.
2. Implement clip timeline, audio capture/mixing, and project save/load.
3. Package the shared editor for desktop and Android after the web workflow stabilizes.
4. Preserve existing NeoOS functionality; keep NeoCut isolated under `apps/neocut-web/`.
