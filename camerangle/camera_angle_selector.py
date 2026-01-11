"""
Camera Angle Selector Node for ComfyUI
A custom node that provides a 3D visual interface for selecting camera angles.
The 3D visualization renders directly inside the node using Three.js.
"""

import json

# View directions (8 angles)
VIEW_DIRECTIONS = [
    "front view",
    "front-right quarter view",
    "right side view",
    "back-right quarter view",
    "back view",
    "back-left quarter view",
    "left side view",
    "front-left quarter view",
]

# Height angles (4 types)
HEIGHT_ANGLES = [
    "low-angle shot",
    "eye-level shot",
    "elevated shot",
    "high-angle shot",
]

# Shot sizes (3 types)
SHOT_SIZES = [
    "close-up",
    "medium shot",
    "wide shot",
]

# Generate all 96 combinations
CAMERA_ANGLES = []
for direction in VIEW_DIRECTIONS:
    for height in HEIGHT_ANGLES:
        for size in SHOT_SIZES:
            CAMERA_ANGLES.append({
                "direction": direction,
                "height": height,
                "size": size,
                "prompt": f"<sks> {direction} {height} {size}"
            })


class CameraAngleSelector:
    """
    ComfyUI custom node for selecting camera angles using a 3D visual interface.
    The 3D visualization is rendered by the companion JavaScript extension.
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "selected_indices": ("STRING", {
                    "default": "[]",
                    "multiline": False,
                }),
            },
        }
    
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("selected_angles",)
    OUTPUT_IS_LIST = (True,)
    FUNCTION = "execute"
    CATEGORY = "camera"
    DESCRIPTION = "Select camera angles using a 3D visual interface rendered directly in the node"
    
    def execute(self, selected_indices="[]"):
        """
        Execute the node and return the list of selected prompts.
        
        Args:
            selected_indices: JSON string containing list of selected indices
            
        Returns:
            Tuple containing list of selected angle prompts
        """
        # Parse selected indices
        try:
            indices = json.loads(selected_indices)
        except (json.JSONDecodeError, TypeError):
            indices = []
        
        if not isinstance(indices, list):
            indices = []
        
        # Clamp indices to valid range
        clamped_indices = []
        for idx in indices:
            if isinstance(idx, int):
                clamped_indices.append(max(0, min(idx, len(CAMERA_ANGLES) - 1)))
        
        # Build <sks> ... prompts from clamped indices
        selected_prompts = []
        for idx in clamped_indices:
            selected_prompts.append(CAMERA_ANGLES[idx]["prompt"])
        
        return (selected_prompts,)


NODE_CLASS_MAPPINGS = {
    "CameraAngleSelector": CameraAngleSelector,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "CameraAngleSelector": "Camera Angle Selector",
}
