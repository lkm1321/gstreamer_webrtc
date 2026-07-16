import asyncio
import logging

import numpy as np
import numpy.typing as npt
from pollen_vision.camera_wrappers.depthai.cam_config import CamConfig
from rclpy.duration import Duration
from rclpy.node import Node
from sensor_msgs.msg import CameraInfo
from sensor_msgs.msg._compressed_image import CompressedImage
from sensor_msgs.msg._image import Image


class ROSPublisher(Node):  # type: ignore[misc]
    def __init__(
        self, cam_config: CamConfig, side: str, asyncio_loop: asyncio.AbstractEventLoop, stop_event: asyncio.Event
    ) -> None:
        super().__init__(f"teleop_camera_publisher_{side}")
        self._logger = logging.getLogger(__name__)
        self._stop_event = stop_event
        self._clock = self.get_clock()
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
        self._compr_img.header.stamp = stamp
        self._compr_img.data = frame  # Note: there is probably a copy here, hence the high CPU usage
        self._camera_info.header.stamp = stamp
        self._camera_publisher.publish(self._compr_img)
        self._camera_info_publisher.publish(self._camera_info)


class ROSDepthPublisher(Node):  # type: ignore[misc]
    """Publishes the head ToF depth map as a sensor_msgs/Image (16UC1, millimeters)."""

    def __init__(self, cam_config: CamConfig, asyncio_loop: asyncio.AbstractEventLoop, stop_event: asyncio.Event) -> None:
        super().__init__("teleop_camera_publisher_depth")
        self._logger = logging.getLogger(__name__)
        self._stop_event = stop_event
        self._clock = self.get_clock()

        height, width, distortion_model, D, K = cam_config.get_tof_camera_info()

        self._depth_publisher = self.create_publisher(Image, "teleop_camera/depth/image_raw", 1)
        self._logger.info(f'Launching "{self._depth_publisher.topic_name}" publisher.')

        self._img = Image()
        self._img.header.frame_id = "tof_camera_optical"
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
        # The ToF is not part of the stereo rectification: identity rotation, P is K with a zero translation column.
        self._camera_info.r = np.eye(3).flatten()
        self._camera_info.p = [K[0], K[1], K[2], 0.0, K[3], K[4], K[5], 0.0, K[6], K[7], K[8], 0.0]

        self._logger.info("Node teleop_camera_publisher_depth ready!")

    def publish_depth(self, frame: npt.NDArray[np.uint16], latency_ns: int = 0) -> None:
        """Publish a uint16 depth frame (millimeters) together with its CameraInfo, sharing a stamp.

        depth_image_proc synchronizes the depth image and its CameraInfo, so both must carry the same
        timestamp and be published together (not on an independent 1 Hz timer).
        """
        offset_duration = Duration(nanoseconds=latency_ns)
        stamp = (self._clock.now() - offset_duration).to_msg()
        self._img.header.stamp = stamp
        self._img.data = frame.tobytes()
        self._camera_info.header.stamp = stamp
        self._depth_publisher.publish(self._img)
        self._camera_info_publisher.publish(self._camera_info)
