"""
UmiAI Camera Control Nodes
Ported from VNCCS Utils for multi-angle LoRA prompt generation.
"""

import json


class UmiCameraControl:
    """
    Camera position control with sliders for azimuth, elevation, and distance.
    Generates prompts optimized for multi-angle LoRAs (e.g., Qwen-Image-Edit).
    """
    
    AZIMUTH_MAP = {
        0: "front view",
        45: "front-right quarter view",
        90: "right side view",
        135: "back-right quarter view",
        180: "back view",
        225: "back-left quarter view",
        270: "left side view",
        315: "front-left quarter view"
    }
    
    ELEVATION_MAP = {
        -30: "low-angle shot",
        0: "eye-level shot",
        30: "elevated shot",
        60: "high-angle shot"
    }
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "azimuth": ("INT", {
                    "default": 0, 
                    "min": 0, 
                    "max": 360, 
                    "step": 45, 
                    "display": "slider",
                    "tooltip": "Angle around subject (0=Front, 90=Right, 180=Back, 270=Left)"
                }),
                "elevation": ("INT", {
                    "default": 0, 
                    "min": -30, 
                    "max": 60, 
                    "step": 30, 
                    "display": "slider",
                    "tooltip": "Vertical angle (-30=Low, 0=Eye Level, 60=High)"
                }),
                "distance": (["close-up", "medium shot", "wide shot"], {
                    "default": "medium shot"
                }),
                "include_trigger": ("BOOLEAN", {
                    "default": True, 
                    "tooltip": "Include trigger word in output"
                }),
            },
            "optional": {
                "trigger_word": ("STRING", {
                    "default": "<sks>",
                    "tooltip": "Custom trigger word for your LoRA (e.g., <sks>, ohwx, etc.)"
                }),
            }
        }

    RETURN_TYPES = ("STRING", "STRING",)
    RETURN_NAMES = ("prompt", "camera_tags",)
    CATEGORY = "UmiAI/Camera"
    FUNCTION = "generate_prompt"
    
    def generate_prompt(self, azimuth, elevation, distance, include_trigger, trigger_word="<sks>"):
        """Generate camera angle prompt from settings."""
        # Normalize azimuth to 0-359
        azimuth = int(azimuth) % 360
        
        # Find closest azimuth step
        if azimuth > 337.5:
            closest_azimuth = 0
        else:
            closest_azimuth = min(self.AZIMUTH_MAP.keys(), key=lambda x: abs(x - azimuth))
        
        az_str = self.AZIMUTH_MAP[closest_azimuth]
        
        # Find closest elevation step
        closest_elevation = min(self.ELEVATION_MAP.keys(), key=lambda x: abs(x - elevation))
        el_str = self.ELEVATION_MAP[closest_elevation]
        
        # Build prompt parts
        parts = []
        if include_trigger and trigger_word:
            parts.append(trigger_word.strip())
        
        parts.append(az_str)
        parts.append(el_str)
        parts.append(distance)
        
        # Camera tags without trigger (for separate use)
        camera_tags = f"{az_str}, {el_str}, {distance}"
        
        return (" ".join(parts), camera_tags)


class UmiVisualCameraControl(UmiCameraControl):
    """
    Visual camera control with interactive canvas widget.
    Click to set azimuth/distance, drag slider for elevation.
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                # Hidden JSON input - controlled by JS widget
                "camera_data": ("STRING", {"default": "{}", "hidden": True}), 
            },
            "optional": {
                "trigger_word": ("STRING", {
                    "default": "<sks>",
                    "tooltip": "Custom trigger word for your LoRA"
                }),
            }
        }

    RETURN_TYPES = ("STRING", "STRING",)
    RETURN_NAMES = ("prompt", "camera_tags",)
    CATEGORY = "UmiAI/Camera"
    FUNCTION = "generate_prompt_from_json"

    def generate_prompt_from_json(self, camera_data, trigger_word="<sks>"):
        """Parse JSON camera data and generate prompt."""
        try:
            data = json.loads(camera_data)
        except json.JSONDecodeError:
            # Fallback defaults
            data = {
                "azimuth": 0, 
                "elevation": 0, 
                "distance": "medium shot", 
                "include_trigger": True
            }
        
        return self.generate_prompt(
            data.get("azimuth", 0), 
            data.get("elevation", 0), 
            data.get("distance", "medium shot"), 
            data.get("include_trigger", True),
            trigger_word
        )


# ==============================================================================
# UMI 3D CAMERA ANGLE SELECTOR (From Camerangle)
# ==============================================================================

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


class UmiCameraAngleSelector:
    """
    3D Camera Angle Selector with interactive Three.js visualization.
    Select from 96 camera angle combinations with multi-select support.
    Perfect for QWEN angle LoRA workflows.
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
            "optional": {
                "trigger_word": ("STRING", {
                    "default": "<sks>",
                    "tooltip": "Custom trigger word (default: <sks>)"
                }),
            }
        }
    
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("selected_angles",)
    OUTPUT_IS_LIST = (True,)
    FUNCTION = "execute"
    CATEGORY = "UmiAI/Camera"
    DESCRIPTION = "Select camera angles using a 3D visual interface with 96 angle combinations"
    
    def execute(self, selected_indices="[]", trigger_word="<sks>"):
        """
        Execute the node and return the list of selected prompts.
        
        Args:
            selected_indices: JSON string containing list of selected indices
            trigger_word: Custom trigger word to use instead of <sks>
            
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
        
        # Build prompts from clamped indices
        selected_prompts = []
        trigger = trigger_word.strip() if trigger_word else "<sks>"
        
        for idx in clamped_indices:
            angle = CAMERA_ANGLES[idx]
            prompt = f"{trigger} {angle['direction']} {angle['height']} {angle['size']}"
            selected_prompts.append(prompt)
        
        # Return at least empty list
        if not selected_prompts:
            selected_prompts = [f"{trigger} front view eye-level shot medium shot"]
        
        return (selected_prompts,)


# ==============================================================================
# NODE REGISTRATION
# ==============================================================================

NODE_CLASS_MAPPINGS = {
    "UmiCameraControl": UmiCameraControl,
    "UmiVisualCameraControl": UmiVisualCameraControl,
    "UmiCameraAngleSelector": UmiCameraAngleSelector,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "UmiCameraControl": "UmiAI Camera Control",
    "UmiVisualCameraControl": "UmiAI Visual Camera Control",
    "UmiCameraAngleSelector": "UmiAI 3D Camera Angle Selector",
}
