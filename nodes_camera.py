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
# NODE REGISTRATION
# ==============================================================================

NODE_CLASS_MAPPINGS = {
    "UmiCameraControl": UmiCameraControl,
    "UmiVisualCameraControl": UmiVisualCameraControl,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "UmiCameraControl": "UmiAI Camera Control",
    "UmiVisualCameraControl": "UmiAI Visual Camera Control",
}
