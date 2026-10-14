This is the Reachy dashboard 1.2.1 video client with a narrow fix: an unavailable
Orbbec torso endpoint must not disable the independent head WebRTC view. The Head
view remains selectable, and the Torso tab recovers when its endpoint returns.

Validation: `node check-video-management.cjs`.

On reachy, the file is installed at
`/pollen/docker/reachy2-dashboard/video-management.js` and mounted by that
directory's compose file onto the dashboard's original static JS path. The
original compose file was saved as `compose.yaml.before-camera-fix-20261013`.
