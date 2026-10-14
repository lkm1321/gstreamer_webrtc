import asyncio
import logging

import numpy as np
import numpy.typing as npt
from pollen_vision.camera_wrappers.depthai.cam_config import CamConfig
from pollen_vision.camera_wrappers.depthai.utils import get_socket_from_name
from rclpy.duration import Duration
from rclpy.node import Node
from sensor_msgs.msg import CameraInfo
from sensor_msgs.msg._compressed_image import CompressedImage
from sensor_msgs.msg._image import Image


class ROSPublisher(Node):  # type: ignore[misc]
    def __init__(
        self,
        cam_config: CamConfig,
        side: str,
        asyncio_loop: asyncio.AbstractEventLoop,
        stop_event: asyncio.Event,
    ) -> None:
        super().__init__(f"teleop_camera_publisher_{side}")
        self._logger = logging.getLogger(__name__)
        self._stop_event = stop_event
        self._clock = self.get_clock()
        self._cam_config = cam_config
        self._side = side

        self._camera_publisher = self.create_publisher(
            CompressedImage, f"teleop_camera/{self._side}_image/image_raw/compressed", 1
        )
        self._logger.info(f'Launching "{self._camera_publisher.topic_name}" publisher.')

        self._compr_img = CompressedImage()
        self._compr_img.format = "jpeg"
        self._compr_img.header.frame_id = f"{side}_camera_optical"

        self._camera_info_publisher = self.create_publisher(
            CameraInfo, f"teleop_camera/{self._side}_image/image_raw/camera_info", 5
        )
        self._logger.info(f'Launching "{self._camera_info_publisher.topic_name}" publisher.')

        self._camera_info = CameraInfo()
        self._camera_info.header.frame_id = self._compr_img.header.frame_id
        height, width, distortion_model, D, K, R, P = cam_config.to_ROS_msg(side)
        self._camera_info.height = height
        self._camera_info.width = width
        self._camera_info.distortion_model = distortion_model
        self._camera_info.d = D
        self._camera_info.k = K
        self._camera_info.r = R
        self._camera_info.p = P

        self._logger.info(f"Node teleop_camera_publisher_{side} ready!")

    def publish_img(self, frame: bytes, latency_ns: int = 0) -> None:
        """Publishes the image together with its CameraInfo, sharing a single timestamp.

        depth_image_proc (and other message_filters-based nodes) time-synchronize the image and its
        CameraInfo, so the CameraInfo must be stamped with, and published alongside, each frame rather
        than on an independent 1 Hz timer with unrelated stamps.
        """
        offset_duration = Duration(nanoseconds=latency_ns)
        stamp = (self._clock.now() - offset_duration).to_msg()
        intrinsics = self._cam_config.rgb_intrinsics.get(self._side)
        if intrinsics is not None:
            K = np.array(intrinsics)
            self._camera_info.k = K.flatten().tolist()
            self._camera_info.p = np.column_stack((K, np.zeros(3))).flatten().tolist()
        self._compr_img.header.stamp = stamp
        self._compr_img.data = frame  # Note: there is probably a copy here, hence the high CPU usage
        self._camera_info.header.stamp = stamp
        self._camera_publisher.publish(self._compr_img)
        self._camera_info_publisher.publish(self._camera_info)


class ROSDepthPublisher(Node):  # type: ignore[misc]
    """Publishes the selected depth map as a sensor_msgs/Image (16UC1, millimeters)."""

    def __init__(
        self,
        cam_config: CamConfig,
        asyncio_loop: asyncio.AbstractEventLoop,
        stop_event: asyncio.Event,
    ) -> None:
        super().__init__("teleop_camera_publisher_depth")
        self._logger = logging.getLogger(__name__)
        self._stop_event = stop_event
        self._clock = self.get_clock()
        self._cam_config = cam_config

        if cam_config.depth_mode == "stereo":
            width, height = cam_config.depth_resolution
            socket = get_socket_from_name("left", cam_config.name_to_socket)
            K = np.array(cam_config.calib.getCameraIntrinsics(socket, width, height)).flatten().tolist()
            distortion_model, D = "plumb_bob", [0.0] * 5
        else:
            height, width, distortion_model, D, K = cam_config.get_tof_camera_info()

        self._depth_publisher = self.create_publisher(Image, "teleop_camera/depth/image_raw", 1)
        self._logger.info(f'Launching "{self._depth_publisher.topic_name}" publisher.')

        self._img = Image()
        self._img.header.frame_id = "left_camera_optical" if cam_config.depth_mode == "stereo" else "tof_camera_optical"
        self._img.height = height
        self._img.width = width
        self._img.encoding = "16UC1"
        self._img.is_bigendian = 0
        self._img.step = width * 2

        self._camera_info_publisher = self.create_publisher(CameraInfo, "teleop_camera/depth/camera_info", 1)
        self._logger.info(f'Launching "{self._camera_info_publisher.topic_name}" publisher.')

        self._camera_info = CameraInfo()
        self._camera_info.header.frame_id = self._img.header.frame_id
        self._camera_info.height = height
        self._camera_info.width = width
        self._camera_info.distortion_model = distortion_model
        self._camera_info.d = D
        self._camera_info.k = K
        # Depth is in the selected camera optical frame; P is K with zero translation.
        self._camera_info.r = np.eye(3).flatten()
        self._camera_info.p = [
            K[0],
            K[1],
            K[2],
            0.0,
            K[3],
            K[4],
            K[5],
            0.0,
            K[6],
            K[7],
            K[8],
            0.0,
        ]

        self._logger.info("Node teleop_camera_publisher_depth ready!")

    def publish_depth(self, frame: npt.NDArray[np.uint16], latency_ns: int = 0) -> None:
        """Publish a uint16 depth frame (millimeters) together with its CameraInfo, sharing a stamp.

        depth_image_proc synchronizes the depth image and its CameraInfo, so both must carry the same
        timestamp and be published together (not on an independent 1 Hz timer).
        """
        offset_duration = Duration(nanoseconds=latency_ns)
        stamp = (self._clock.now() - offset_duration).to_msg()
        intrinsics = self._cam_config.depth_intrinsics
        if intrinsics is not None:
            K = np.array(intrinsics)
            self._camera_info.k = K.flatten().tolist()
            self._camera_info.p = np.column_stack((K, np.zeros(3))).flatten().tolist()
        self._img.header.stamp = stamp
        self._img.data = frame.tobytes()
        self._camera_info.header.stamp = stamp
        self._depth_publisher.publish(self._img)
        self._camera_info_publisher.publish(self._camera_info)
