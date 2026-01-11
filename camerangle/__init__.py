from .camera_angle_selector import CameraAngleSelector

WEB_DIRECTORY = "web"

NODE_CLASS_MAPPINGS = {
    "CameraAngleSelector": CameraAngleSelector,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "CameraAngleSelector": "Camera Angle Selector",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
