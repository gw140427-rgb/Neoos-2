# NeoCut Web MVP

NeoCut is an independent, free-first video editor prototype in the NeoOS-2 repository.

## Run
Open `index.html` in a modern browser, or serve this folder with any static web host. No build step, account, API key, or server-side upload is required.

## Implemented in this prototype
- Installable PWA shell for supported mobile/desktop browsers, plus cached app files for reopening offline after the first successful load (media editing/export still requires browser support and local files)
- Local video import and preview
- Start/end range preview and experimental range export
- Caption overlay with text, size, and color
- Experimental browser export to WebM with caption overlay
- Optional background music selection and volume control, mixed into supported WebM exports
- Save/load project settings as JSON (media files are not embedded)

## Known limitations
- This is an early MVP, not a complete CapCut replacement.
- Browser MediaRecorder, canvas, and Web Audio support vary. Large videos can be slow or fail.
- Export is WebM, not MP4. Audio mixing and export need real-device testing.
- The editor currently handles one video at a time; it has no multi-clip timeline, transitions, filters, waveform, or AI subtitles.
- Project JSON saves editing settings only; the user must reselect the original video and music after opening a project.
- PWA installation is not the same as a native Android APK or a Windows/Linux installer; those packages are not built yet.

## Roadmap
1. Test PWA installation and export on Android and desktop browsers; fix browser-specific issues.
2. Add a real multi-clip timeline, transitions, and more precise editing.
3. Add reliable media export and project asset relinking.
4. Package the shared editor as native Android and desktop apps after the web workflow stabilizes.
