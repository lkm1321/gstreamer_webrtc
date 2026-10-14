# Plan: Enable the head ToF camera in pollen-vision + gstreamer_webrtc

## Context (read first)

Reachy 2's head is a single Luxonis OAK-FFC-4P DepthAI device carrying 2× IMX296 RGB
(sockets `CAM_B`/`CAM_C`) and a Luxonis OAK-FFC ToF 33D module between the eyes on a third
FFC port (`CAM_A` or `CAM_D` — confirmed in Phase 0). Today nothing in the stack touches the
ToF: `pollen-vision` (pinned `2.0.1` by `gstreamer_webrtc/setup.cfg`) builds a depthai
pipeline with only two `ColorCamera` → `ImageManip` → H264+MJPEG encoders, and
`gstreamer_webrtc` only consumes the `left`/`right` H264 (WebRTC) and MJPEG (ROS) queues.

Architecture decision (already made, do not revisit): the ToF is added to the same on-device
pipeline (a DepthAI device is exclusive to one process), drained via its own XLink queue, and
published **directly to ROS** as `sensor_msgs/Image` `16UC1`. It does NOT enter the
GStreamer/WebRTC pipeline. The WebRTC teleop path must remain byte-for-byte untouched.

Reference sources (clone fresh if needed):
- pollen-vision at tag `2.0.1`: `git clone --branch 2.0.1 https://github.com/pollen-robotics/pollen-vision.git`
- gstreamer_webrtc: `/Users/156421/src/reachy/hardware/gstreamer_webrtc/` (branch `develop`)

Work happens on forks of `pollen-robotics/pollen-vision` (branch off tag `2.0.1`) and
`pollen-robotics/gstreamer_webrtc` (branch off `develop`).

Key runtime facts the plan depends on:
- Config JSON is loaded from the **pollen-vision package** (`config_files_vision/CONFIG_IMX296.json`
  via `importlib.resources` in `utils.get_config_file_path`) — NOT from `gstreamer_webrtc/config/`.
  The copies in `gstreamer_webrtc/config/` are unshipped mirrors; update both, but the packaged
  one is the one that matters.
- `depthai==2.27.0.0` is pinned; `dai.node.ToF` is supported at this version (stable decoding
  since 2.26). Do not bump depthai.
- `DepthaiWrapper._prepare()` (wrapper.py) filters `getConnectedCameraFeatures()` by
  `socket_to_name` keys and assumes the survivors are the identical stereo pair
  (`connected_cameras_features[0].width`). `flash()` also iterates `socket_to_name`.
  **Therefore: do NOT add the ToF socket to `socket_to_name`.** Use a new, separate config key.
- `TeleopWrapper.get_data_h264()` iterates `self.queues` assuming every entry is an H264
  bitstream queue, and `gstreamer_webrtc/src/gstreamer/main.py:compute_camera_latency()`
  indexes `latency["left"]`. **Therefore: the ToF queue must live in its own dict**, mirroring
  the existing `_queues_mjpeg` pattern, never in `self.queues`.

---

## Phase 0 — Hardware discovery (on the robot; MOSTLY DONE)

Already confirmed by probing the robot (2026-07-14):
- The ToF module enumerates on the teleop-head device with `sensorName == "S5K33D"`
  (Samsung 33D ToF — the expected sensor on the OAK-FFC ToF 33D module).
- Its `CameraFeatures.name` (socket alias) is empty, while the IMX296 entries report
  `left`/`right`. This is expected — the alias comes from the board-config/EEPROM socket
  naming and Pollen only aliased the stereo sockets. Nothing in the stack reads `name`;
  do not add logic that depends on it.

Remaining Phase-0 steps (small probe script, e.g. fork `scripts/probe_tof.py`):
1. Record the ToF's **board socket** (`cam.socket`, expect `CAM_A` or `CAM_D`) — this is the
   value for the `"tof_socket"` config key.
2. Confirm `dai.CameraSensorType.TOF` is in its `supportedTypes`.
3. Check whether device EEPROM has intrinsics for that socket:
   `device.readCalibration().getCameraIntrinsics(<tof socket>, cam.width, cam.height)` —
   print the K matrix or the exception. Pollen's `flash()` only writes the left/right
   sockets, so ToF intrinsics are plausibly absent/zero; the result decides which branch of
   `get_tof_camera_info()` (§1.1) is exercised. Note this only affects the published ROS
   `CameraInfo` — the ToF node's internal depth calibration (FPPN/wiggle) lives on the
   module's own EEPROM and is applied on-device regardless.

Deliverable: the socket string for `"tof_socket"`, and whether EEPROM intrinsics exist.

---

## Phase 1 — pollen-vision fork (branch from tag `2.0.1`)

All paths relative to `pollen_vision/pollen_vision/camera_wrappers/depthai/` unless noted.

### 1.1 `cam_config.py`
- In `CamConfig.__init__`, read an optional key: `self.tof_socket = config.get("tof_socket")`
  (string like `"CAM_A"`, or `None`). Add an optional ctor param `tof_fps: int = 30` and store it.
  ToF stays entirely out of `socket_to_name` / `name_to_socket`.
- Add `get_tof_camera_info(self) -> Tuple[...]` returning `(height, width, distortion_model,
  D, K)` for the ToF socket via `self.calib.getCameraIntrinsics(socket_stringToCam[self.tof_socket],
  w, h)` and `getDistortionCoefficients(...)`. Do NOT reuse `to_ROS_msg()` — it is
  stereo-rectification-specific (uses `P_left/P_right` and stereo rotation). Depth resolution
  `(w, h)` comes from the sensor feature reported in Phase 0 (expect 640×480).
  **Fallback (per Phase 0 step 3):** if EEPROM intrinsics for the ToF socket are absent or
  zero, log a clear warning and synthesize K from the module datasheet FoV
  (H 90°, V 65°: `fx = (w/2)/tan(45°)`, `fy = (h/2)/tan(32.5°)`, `cx = w/2`, `cy = h/2`),
  `distortion_model = "plumb_bob"`, `D = [0]*5`. Approximate intrinsics are acceptable for a
  first integration; flashing real ToF intrinsics into the EEPROM is out of scope.
- Update `to_string()` to mention ToF presence (nice-to-have).

### 1.2 `teleop.py` (`TeleopWrapper`)
All ToF additions are conditional on `self.cam_config.tof_socket is not None` so every other
Reachy (and other configs like CONFIG_SR) keeps working unchanged.

- `_create_pipeline()` / new `_create_tof_nodes(pipeline)`:
  - `self.tof_cam = pipeline.create(dai.node.Camera)`;
    `setBoardSocket(socket_stringToCam[cfg.tof_socket])`; `setFps(cfg.tof_fps)`.
  - `self.tof = pipeline.create(dai.node.ToF)`; configure `initialConfig`
    (enable optical-error correction, wiggle/FPPN correction, median filter — follow the
    depthai 2.27 ToF example, https://docs.luxonis.com/software/depthai/examples/tof_depth/).
  - `self.xout_tof = pipeline.createXLinkOut()`; stream name `"tof_depth"`.
- `_link_pipeline()`: `self.tof_cam.raw.link(self.tof.input)`;
  `self.tof.depth.link(self.xout_tof.input)`.
- `_create_queues()`: create `self._queue_tof = self._device.getOutputQueue("tof_depth",
  maxSize=1, blocking=False)` — stored separately, NOT merged into the returned `queues_h264`.
- New public method mirroring `get_data_mjpeg()`:
  ```
  get_data_tof() -> Tuple[npt.NDArray[np.uint16], float, timedelta]
  ```
  Uses `pkt = self._queue_tof.get()` (blocking; runs in its own host thread) and
  `pkt.getFrame()` (2-D uint16, depth in millimetres), latency computed as elsewhere
  (`dai.Clock.now() - pkt.getTimestamp()`).

### 1.3 Packaged config
- `pollen_vision/config_files_vision/CONFIG_IMX296.json`: add `"tof_socket": "<from Phase 0>"`.
  Leave `socket_to_name` untouched. Leave the other CONFIG_*.json files untouched.

### 1.4 Guard rails
- If pipeline start throws after adding ToF nodes (RVC2 resource exhaustion — 4 video encoders
  + ToF decode share SHAVEs), catch and re-raise with a clear message suggesting lowering
  `tof_fps`; do not silently drop the stereo path.

### 1.5 Example + release
- Add `pollen_vision/examples/tof_example.py` (or `scripts/`): open `TeleopWrapper` with
  `CONFIG_IMX296`, loop `get_data_tof()`, colorize (`cv2.applyColorMap` on normalized depth)
  and `cv2.imshow`. This is the standalone acceptance test for Phase 1.
- Match repo lint conventions (repo ships black/isort/flake8/mypy configs — run whatever
  `.github/workflows/` runs).
- Tag the fork: `2.0.1-tof.1`.

---

## Phase 2 — gstreamer_webrtc fork (branch from `develop`)

### 2.1 `setup.cfg`
- Repin: `pollen-vision@git+https://github.com/<fork-owner>/pollen-vision.git@2.0.1-tof.1`.
- Bump `version = 1.3.0` → `1.4.0`.

### 2.2 `src/gstreamer/ros_publisher.py`
- Add `ROSDepthPublisher(Node)` (node name `teleop_camera_publisher_depth`):
  - Publishes `sensor_msgs/Image` on `teleop_camera/depth/image_raw`, QoS depth 1:
    `encoding="16UC1"`, `step = width * 2`, `header.frame_id = "tof_camera_optical"`,
    data = raw uint16 mm frame bytes; stamp = `now() - latency` (same pattern as
    `ROSPublisher.publish_img`).
  - Publishes `CameraInfo` on `teleop_camera/depth/camera_info` at 1 Hz from
    `cam_config.get_tof_camera_info()` (same asyncio-coroutine pattern as the existing
    `_publish_camera_info`).
- Do not modify the existing `ROSPublisher`.

### 2.3 `src/gstreamer/main.py`
- Add `--tof` flag (default off). Validate: `--tof` requires `--ros` and `--stream != "audio"`;
  error out otherwise (depth has no WebRTC consumer by design).
- Thread the flag through to the wrapper only if needed (ToF nodes activate off the config's
  `tof_socket`; `--tof` gates only the *publishing*. Simplest correct behavior: when
  `tof_socket` is present in the config the device pipeline always includes ToF nodes, and
  `--tof --ros` decides whether the host drains/publishes them. The `maxSize=1, blocking=False`
  device-side queue makes an undrained stream harmless).
- Add `thread_tof_fun(teleop_wrapper, asyncio_loop, stop_event)`: its own `Thread(daemon=True)`
  started next to `thread_ros`, looping `get_data_tof()` (blocking at ToF fps) →
  `depth_publisher.publish_depth(...)`. Do NOT fold it into `thread_ros_fun`'s loop — that loop
  is paced by the MJPEG queues at camera fps and the rates must stay decoupled. rclpy
  init/executor handling: `rclpy.init()` is currently called inside `thread_ros_fun`; create the
  depth node there too and add it to the same `MultiThreadedExecutor`, then start the tof pull
  thread from within `thread_ros_fun` after node creation (keeps single rclpy init).
- Touch nothing in `configure_pipeline`, `compute_camera_latency`, or the H264 push loop.

### 2.4 Config mirror + docs
- `config/CONFIG_IMX296.json`: mirror the `"tof_socket"` addition (kept in sync for humans;
  note in README that the runtime copy ships inside pollen-vision).
- README: new section — enabling ToF (`--tof --ros`), topic names, units (mm), known limits.

### 2.5 Lint
- Must pass exactly what `.github/workflows/lint.yml` runs: `black --check .` (line length 128),
  `isort . -c`, `flake8 . --config setup.cfg` (max-complexity 10 — watch `main_loop`),
  `mypy .` (strict mode is on; annotate everything, `Optional` handled explicitly).

---

## Phase 3 — Verification (on the robot)

1. **Phase-1 standalone**: run `tof_example.py` → live colorized depth window; point at a wall
   at a measured distance, confirm mm values within spec (<1% error, 0.2–5 m range).
2. **Regression, ToF disabled**: run `streaming_service --config CONFIG_IMX296` (no `--tof`)
   with a headset or `scripts/` consumer connected → stereo stream works as before; compare
   `Reachy2Teleoperation.log` / `scripts/buffer_lateness.py` latency stats against a
   pre-change baseline run. Must be unchanged within noise.
3. **Full stack**: `streaming_service --config CONFIG_IMX296 --ros --tof` +
   active WebRTC consumer simultaneously:
   - `ros2 topic hz /teleop_camera/depth/image_raw` ≈ tof_fps (30).
   - `ros2 topic hz` on both mjpeg-backed image topics unchanged.
   - rviz2: depth image renders, CameraInfo present.
   - Stereo H264 still 60 fps, no XLink drops in logs, watch host CPU.
4. **USB2 edge case**: repeat step 3 with `--force-usb2`. Raw depth (~18 MB/s) + streams may
   saturate USB2 — if it degrades, document `--tof` as USB3-only rather than fixing.
5. Run the two repos' lint suites; commit; tag `2.0.1-tof.1` (pollen-vision) and `v1.4.0-tof.1`
   (gstreamer_webrtc).

---

## Known risks / decision points for the executing agent

- **ToF hardware confirmed present** (`sensorName == "S5K33D"`); only its board socket and
  EEPROM-intrinsics status still need recording (Phase 0). Everything is parameterized on the
  `"tof_socket"` config key, so only the JSON needs the discovered value. If any runtime
  sanity check on the ToF is wanted, match `sensorName == "S5K33D"` or
  `CameraSensorType.TOF in supportedTypes` — never `CameraFeatures.name`, which is an
  EEPROM socket alias and is empty for this socket on this robot.
- **RVC2 compute budget**: 2× H264(60fps) + 2× MJPEG(60fps) encoders + ToF decode may exceed
  SHAVE/encoder resources. If `startPipeline` fails or fps collapses: first lower `tof_fps`
  to 15; if still failing, make MJPEG encoders conditional on `--ros` (they're unused
  otherwise) to free resources — that's an acceptable scope extension.
- **depthai 2.27 ToF API details** (node config field names changed between 2.24/2.26/2.27):
  consult the version-matching Luxonis example rather than latest docs.
- **Do not** add the ToF to `socket_to_name`, `self.queues`, `get_data_h264()`, or anything
  the WebRTC path or `compute_camera_latency()` touches.
- **Units/encoding contract**: depth is uint16 millimetres, `16UC1`, no scaling — consumers
  (e.g. depth_image_proc) expect exactly this.
- Out of scope: streaming depth to the VR headset, torso Orbbec camera, overlay Docker image
  (handled separately), upstream PRs (do last, after robot validation).
