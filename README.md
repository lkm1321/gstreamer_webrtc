# Gstreamer WebRTC

[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black) ![linter](https://github.com/pollen-robotics/gstreamer_webrtc/actions/workflows/lint.yml/badge.svg)

This python code streams video from a Luxonis Camera, and audio from a microphone. It can also consume and play back an audio stream from a remote peer. This piece of software is based on the [gstreamer webrtc plugin](https://gitlab.freedesktop.org/gstreamer/gst-plugins-rs/-/tree/main/net/webrtc).

## Installation

The dependencies are listed in the ```setup.cfg``` file and will be installed if you install this package locally with:
```
pip install -e .[dev]
```
use *[dev]* for optional development tools.


## Usage

The installation provides the executable `streaming_service`. Use the `--help` option for more infos about the configuration.

### Examples

Stream audio only

```console
streaming_service  --config config/CONFIG_OAK.json producer --name robot --verbose --stream audio
```

Stream video only

```console
streaming_service  --config config/CONFIG_OAK.json producer --name robot --verbose --stream video
```       

Steam audio and video, and playback sound from remote peer
```console
streaming_service --config config/CONFIG_OAK.json producer --name robot --verbose --stream audiovideo --remote-producer-name UnityClient
```

Simple consumer for debugging purposes
```console
python src/gstreamer/simple_consumer.py consumer --remote-producer-peer-id <peer_id>
```
THe peer_id can be get in the log of the signalling server

### Head depth (Reachy 2)

Depth is opt-in. Select `--depth-mode stereo` to compute depth from the two RGB
cameras, or `--depth-mode tof` (`--tof` also works) for the head ToF sensor.
Both require `--ros` and a video stream. With `--depth-mode off` (the default),
no depth nodes run, regardless of the config's legacy `"tof"` key.

```console
streaming_service producer --config CONFIG_IMX296 --name robot --stream audiovideo --ros --depth-mode stereo --depth-fps 15
```

- `teleop_camera/depth/image_raw`: `sensor_msgs/Image`, `16UC1`, millimeters; zero means invalid depth.
- `teleop_camera/depth/camera_info`: published with each depth image, with the same timestamp.
- Stereo: 640×480, 15 fps by default (use `--depth-fps`, at most `--fps`), aligned to
  `left_camera_optical`. Uses independent, unrectified grayscale camera outputs,
  left/right consistency checking, subpixel disparity, speckle rejection and a 0.2–10 m range.
- ToF: sensor socket is auto-detected; decoding settings remain in `tof_config`.
  The rate is bounded by `--depth-fps` and capped at 10 fps to preserve RGB on RVC2.
  `tof_filtering.enabled` adds a 5×5 median filter and temporal smoothing within 100 mm
  in the depth reader thread. The former DepthAI host-filter presets are no longer used:
  that graph stalled the RGB encoders on RVC2. Missing ToF intrinsics still use an
  approximate datasheet-based fallback with a warning.

Depth has its own queue and reader thread and is published only to ROS. H264 and
MJPEG RGB streams continue independently. Stereo needs texture and overlapping views;
blank surfaces, glass and occlusions can produce invalid pixels. USB3 is recommended.
Runtime camera configs ship in pollen-vision's `config_files_vision/`; `config/` here is a mirror.

For deployment, `docker/Dockerfile.depth` builds both local checkouts over the robot's
existing ToF image. Run its build command from their common `cameras` directory, then
set the camera service image to the result and append `--depth-mode stereo --depth-fps 15`.
The signalling server and gRPC bridge can retain their existing images.

## Debugging

[Enable tracer](https://gstreamer.freedesktop.org/documentation//rstracers/buffer-lateness.html?gi-language=c)

### Tracing tool

[Tool by gstreamer](https://gitlab.freedesktop.org/gstreamer/gst-plugins-rs/-/tree/main/utils/tracers?ref_type=heads)

```console
python scripts/buffer_lateness.py /tmp/buffer_lateness_sender.log --include-filter "(src_(left|right)|rtpbin:*)"
```
```console
python scripts/buffer_lateness.py /tmp/buffer_lateness_received.log --include-filter "(rtpjitterbuffer0|avdec*|webrtc|decoder)"
```
