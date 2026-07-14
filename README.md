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

### Head ToF depth (Reachy 2)

If the camera config json contains `"tof": true` (see `CONFIG_IMX296.json`), the depthai pipeline
decodes the head ToF module on-device. The ToF board socket is auto-detected at runtime (the only
sensor reporting the ToF type). Add `--tof` (requires `--ros` and a video stream) to publish it to ROS:

```console
streaming_service --config CONFIG_IMX296 producer --name robot --stream audiovideo --ros --tof
```

- `teleop_camera/depth/image_raw`: `sensor_msgs/Image`, encoding `16UC1`, raw depth in **millimeters** (no scaling).
- `teleop_camera/depth/camera_info`: `sensor_msgs/CameraInfo` at 1 Hz. If the device EEPROM has no intrinsics
  for the ToF socket, approximate intrinsics are synthesized from the datasheet FoV (a warning is logged).

The depth stream never enters the WebRTC/GStreamer pipeline; it is published to ROS only.
`scripts/probe_tof.py` from the pollen-vision repo inspects the device (sockets, sensors, EEPROM intrinsics).
Note that the runtime copy of the config json ships inside the pollen-vision package
(`config_files_vision/`); the copy in `config/` here is a mirror kept in sync for humans.
Known limits: the ToF is validated on USB3; on `--force-usb2` the raw ToF stream (~18 MB/s) may saturate the link.

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
