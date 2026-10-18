# NeoCut Web MVP

NeoCut is an independent, free-first video editor prototype in the NeoOS-2 repository.

## Run
Open `index.html` in a modern browser, or serve this folder with any static web host. No build step, account, API key, or server-side upload is required.

## Implemented in this prototype
- Installable PWA shell for supported mobile/desktop browsers, plus cached app files for reopening offline after the first successful load (media editing/export still requires browser support and local files)
- Import multiple local video clips, select a clip, reorder clips, and remove clips
- Per-clip start/end trimming and preview
- Sequential multi-clip WebM export with caption overlay (experimental)
- Caption overlay with text, size, and color
- Experimental browser export to WebM with caption overlay
- Optional background music selection and volume control, mixed into supported WebM exports
- Save/load project settings as JSON (media files are not embedded)

## Known limitations
- This is an early MVP, not a complete CapCut replacement.
- Browser MediaRecorder, canvas, and Web Audio support vary. Large videos can be slow or fail.
- Export is WebM, not MP4. Audio mixing and export need real-device testing.
- The multi-clip timeline and sequential export are an early prototype and need real-device testing; transitions, filters, waveform, and AI subtitles are not implemented.
- Project JSON saves clip names/order and trim settings but does not embed media or automatically relink files.
- Native packaging scaffolds and a GitHub Actions workflow now exist for an Android debug APK and Windows/Linux desktop installers. They are not considered built until the workflow completes successfully; no signed release APK is provided.

## Roadmap
1. Test PWA installation and export on Android and desktop browsers; fix browser-specific issues.
2. Test and harden multi-clip export on Android and desktop browsers.
3. Add transitions, filters, and project asset relinking.
4. Validate the Android and desktop CI builds, then test installers on real devices.
