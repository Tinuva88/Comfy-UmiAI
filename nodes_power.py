"""
UmiAI Power Features - Advanced Character Workflow Nodes
Pose Library, Expression Mixer, Scene Composer, Prompt Templates, LoRA Animator
Loads presets from presets/*.yaml files for easy customization.
"""

import json
import os
import yaml
import math

# Get presets directory
PRESETS_DIR = os.path.join(os.path.dirname(__file__), "presets")


def load_yaml_presets(filename):
    """Load presets from a YAML file."""
    path = os.path.join(PRESETS_DIR, filename)
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            print(f"[UmiAI] Error loading {filename}: {e}")
    return {}


def flatten_presets(data, prefix=""):
    """Flatten nested preset dict to flat list of names."""
    result = {}
    for key, value in data.items():
        if isinstance(value, dict):
            if "prompt" in value:
                # This is a preset entry
                full_key = f"{prefix}{key}" if prefix else key
                result[full_key] = value
            else:
                # This is a category, recurse
                nested = flatten_presets(value, f"{key}/")
                result.update(nested)
    return result


# ==============================================================================
# POSE LIBRARY
# ==============================================================================

class UmiPoseLibrary:
    """
    Built-in library of character poses loaded from presets/poses.yaml.
    """
    
    # Default fallback presets
    DEFAULT_PRESETS = {
        "standing_front": {"prompt": "standing, facing viewer, front view, full body", "tags": ["standing", "front"]},
    }
    
    @classmethod
    def get_presets(cls):
        """Load and cache presets."""
        if not hasattr(cls, '_cached_presets'):
            data = load_yaml_presets("poses.yaml")
            cls._cached_presets = flatten_presets(data) if data else cls.DEFAULT_PRESETS
        return cls._cached_presets
    
    @classmethod
    def INPUT_TYPES(cls):
        presets = cls.get_presets()
        pose_names = sorted(list(presets.keys()))
        if not pose_names:
            pose_names = ["standing_front"]
        
        return {
            "required": {
                "pose": (pose_names, {"default": pose_names[0]}),
            },
            "optional": {
                "custom_additions": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "Additional pose details to append"
                }),
            }
        }
    
    RETURN_TYPES = ("STRING", "STRING",)
    RETURN_NAMES = ("pose_prompt", "pose_tags",)
    CATEGORY = "UmiAI/Character"
    FUNCTION = "get_pose"
    
    @classmethod
    def IS_CHANGED(cls, **kwargs):
        # Check if YAML file was modified
        return os.path.getmtime(os.path.join(PRESETS_DIR, "poses.yaml")) if os.path.exists(os.path.join(PRESETS_DIR, "poses.yaml")) else 0
    
    def get_pose(self, pose, custom_additions=""):
        """Get pose prompt and tags from library."""
        presets = self.get_presets()
        preset = presets.get(pose, list(presets.values())[0] if presets else {"prompt": "standing", "tags": []})
        
        prompt = preset.get("prompt", "")
        if custom_additions:
            prompt = f"{prompt}, {custom_additions}"
        
        tags = preset.get("tags", [])
        tags_str = ", ".join(tags) if isinstance(tags, list) else str(tags)
        
        return (prompt, tags_str)


# ==============================================================================
# EXPRESSION MIXER
# ==============================================================================

class UmiExpressionMixer:
    """
    Blend multiple emotions with weighted percentages.
    Loads from presets/emotions.yaml.
    """
    
    DEFAULT_EMOTIONS = {
        "happy": {"prompt": "happy, smiling, cheerful expression", "tags": ["happy"], "intensity": 1.0},
        "neutral": {"prompt": "neutral expression, calm", "tags": ["neutral"], "intensity": 0.5},
    }
    
    @classmethod
    def get_presets(cls):
        """Load and cache emotion presets."""
        if not hasattr(cls, '_cached_presets'):
            data = load_yaml_presets("emotions.yaml")
            cls._cached_presets = flatten_presets(data) if data else cls.DEFAULT_EMOTIONS
        return cls._cached_presets
    
    @classmethod
    def INPUT_TYPES(cls):
        presets = cls.get_presets()
        emotion_names = sorted(list(presets.keys()))
        if not emotion_names:
            emotion_names = ["happy", "neutral"]
        
        return {
            "required": {
                "emotion_1": (emotion_names, {"default": emotion_names[0]}),
                "weight_1": ("FLOAT", {"default": 0.6, "min": 0.0, "max": 1.0, "step": 0.1}),
                "emotion_2": (emotion_names, {"default": emotion_names[min(1, len(emotion_names)-1)]}),
                "weight_2": ("FLOAT", {"default": 0.4, "min": 0.0, "max": 1.0, "step": 0.1}),
            },
            "optional": {
                "emotion_3": (["none"] + emotion_names, {"default": "none"}),
                "weight_3": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.1}),
            }
        }
    
    RETURN_TYPES = ("STRING", "STRING",)
    RETURN_NAMES = ("expression_prompt", "emotion_mix",)
    CATEGORY = "UmiAI/Character"
    FUNCTION = "mix_expressions"
    
    def mix_expressions(self, emotion_1, weight_1, emotion_2, weight_2, 
                        emotion_3="none", weight_3=0.0):
        """Mix emotions with weights."""
        presets = self.get_presets()
        parts = []
        mix_desc = []
        
        for emotion, weight in [(emotion_1, weight_1), (emotion_2, weight_2), (emotion_3, weight_3)]:
            if emotion == "none" or weight <= 0:
                continue
            preset = presets.get(emotion, {})
            prompt = preset.get("prompt", emotion)
            parts.append(f"({prompt}:{weight:.1f})")
            mix_desc.append(f"{emotion}:{int(weight*100)}%")
        
        prompt = ", ".join(parts) if parts else "neutral expression"
        mix_string = " + ".join(mix_desc) if mix_desc else "neutral"
        
        return (prompt, mix_string)


# ==============================================================================
# SCENE COMPOSER
# ==============================================================================

class UmiSceneComposer:
    """
    Combine character with background, lighting, and atmosphere presets.
    Loads from presets/scenes.yaml.
    """
    
    @classmethod
    def get_presets(cls):
        """Load and cache scene presets."""
        if not hasattr(cls, '_cached_presets'):
            data = load_yaml_presets("scenes.yaml")
            cls._cached_presets = data or {}
        return cls._cached_presets
    
    @classmethod
    def get_backgrounds(cls):
        presets = cls.get_presets()
        backgrounds = presets.get("backgrounds", {})
        return flatten_presets(backgrounds)
    
    @classmethod
    def get_lighting(cls):
        presets = cls.get_presets()
        return presets.get("lighting", {})
    
    @classmethod
    def get_atmosphere(cls):
        presets = cls.get_presets()
        return presets.get("atmosphere", {})
    
    @classmethod
    def INPUT_TYPES(cls):
        backgrounds = cls.get_backgrounds()
        bg_names = sorted(list(backgrounds.keys())) or ["studio_white"]
        
        lighting = cls.get_lighting()
        light_names = sorted(list(lighting.keys())) or ["natural"]
        
        atmosphere = cls.get_atmosphere()
        atmo_names = ["none"] + sorted(list(atmosphere.keys()))
        
        return {
            "required": {
                "background": (bg_names, {"default": bg_names[0]}),
                "lighting": (light_names, {"default": light_names[0]}),
            },
            "optional": {
                "atmosphere": (atmo_names, {"default": "none"}),
                "custom_scene": ("STRING", {"default": "", "multiline": True}),
            }
        }
    
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("scene_prompt",)
    CATEGORY = "UmiAI/Character"
    FUNCTION = "compose_scene"
    
    def compose_scene(self, background, lighting, atmosphere="none", custom_scene=""):
        """Compose scene prompt from presets."""
        parts = []
        
        # Background
        backgrounds = self.get_backgrounds()
        bg_preset = backgrounds.get(background, {})
        bg_prompt = bg_preset.get("prompt", background) if isinstance(bg_preset, dict) else str(bg_preset)
        parts.append(bg_prompt)
        
        # Lighting
        lighting_presets = self.get_lighting()
        light_preset = lighting_presets.get(lighting, {})
        light_prompt = light_preset.get("prompt", lighting) if isinstance(light_preset, dict) else str(light_preset)
        parts.append(light_prompt)
        
        # Atmosphere
        if atmosphere != "none":
            atmo_presets = self.get_atmosphere()
            atmo_preset = atmo_presets.get(atmosphere, {})
            atmo_prompt = atmo_preset.get("prompt", "") if isinstance(atmo_preset, dict) else str(atmo_preset)
            if atmo_prompt:
                parts.append(atmo_prompt)
        
        if custom_scene:
            parts.append(custom_scene)
        
        return (", ".join(parts),)


# ==============================================================================
# LORA STRENGTH ANIMATOR
# ==============================================================================

class UmiLoraAnimator:
    """
    Animate LoRA strength over frames for video/animation workflows.
    """
    
    CURVES = ["linear", "ease_in", "ease_out", "ease_in_out", "pulse", "wave"]
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "frame_index": ("INT", {"default": 0, "min": 0, "max": 9999}),
                "total_frames": ("INT", {"default": 100, "min": 1, "max": 9999}),
                "start_strength": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 2.0, "step": 0.05}),
                "end_strength": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.05}),
                "curve": (cls.CURVES, {"default": "linear"}),
            }
        }
    
    RETURN_TYPES = ("FLOAT", "STRING",)
    RETURN_NAMES = ("strength", "lora_weight_string",)
    CATEGORY = "UmiAI/Animation"
    FUNCTION = "animate"
    
    def animate(self, frame_index, total_frames, start_strength, end_strength, curve):
        """Calculate LoRA strength for current frame."""
        # Normalize progress (0 to 1)
        t = min(1.0, max(0.0, frame_index / max(1, total_frames - 1)))
        
        # Apply curve
        if curve == "linear":
            factor = t
        elif curve == "ease_in":
            factor = t * t
        elif curve == "ease_out":
            factor = 1 - (1 - t) ** 2
        elif curve == "ease_in_out":
            factor = 3 * t * t - 2 * t * t * t
        elif curve == "pulse":
            factor = math.sin(t * math.pi)
        elif curve == "wave":
            factor = (math.sin(t * math.pi * 4) + 1) / 2
        else:
            factor = t
        
        # Interpolate strength
        strength = start_strength + (end_strength - start_strength) * factor
        weight_string = f":{strength:.2f}"
        
        return (strength, weight_string)


# ==============================================================================
# PROMPT TEMPLATE MANAGER
# ==============================================================================

class UmiPromptTemplate:
    """
    Save and load prompt configurations as templates.
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        # List available templates
        template_dir = os.path.join(os.path.dirname(__file__), "templates")
        templates = ["none"]
        if os.path.exists(template_dir):
            for f in os.listdir(template_dir):
                if f.endswith(('.yaml', '.yml', '.json')):
                    templates.append(os.path.splitext(f)[0])
        
        return {
            "required": {
                "template_name": (templates, {"default": "none"}),
            },
            "optional": {
                "override_character": ("STRING", {"default": ""}),
                "override_outfit": ("STRING", {"default": ""}),
                "override_emotion": ("STRING", {"default": ""}),
            }
        }
    
    RETURN_TYPES = ("STRING", "STRING", "STRING",)
    RETURN_NAMES = ("prompt", "negative", "settings_info",)
    CATEGORY = "UmiAI/Character"
    FUNCTION = "load_template"
    
    def load_template(self, template_name, override_character="", override_outfit="", override_emotion=""):
        """Load and apply prompt template."""
        if template_name == "none":
            return ("", "", "No template selected")
        
        template_dir = os.path.join(os.path.dirname(__file__), "templates")
        
        # Try YAML first, then JSON
        for ext in ['.yaml', '.yml', '.json']:
            path = os.path.join(template_dir, f"{template_name}{ext}")
            if os.path.exists(path):
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        if ext == '.json':
                            data = json.load(f)
                        else:
                            data = yaml.safe_load(f)
                    
                    prompt = data.get('prompt', '')
                    negative = data.get('negative', '')
                    
                    # Apply overrides
                    if override_character:
                        prompt = prompt.replace('{character}', override_character)
                    if override_outfit:
                        prompt = prompt.replace('{outfit}', override_outfit)
                    if override_emotion:
                        prompt = prompt.replace('{emotion}', override_emotion)
                    
                    info = f"Template: {template_name}"
                    return (prompt, negative, info)
                    
                except Exception as e:
                    return ("", "", f"Error loading template: {e}")
        
        return ("", "", f"Template not found: {template_name}")


# ==============================================================================
# NODE REGISTRATION
# ==============================================================================

NODE_CLASS_MAPPINGS = {
    "UmiPoseLibrary": UmiPoseLibrary,
    "UmiExpressionMixer": UmiExpressionMixer,
    "UmiSceneComposer": UmiSceneComposer,
    "UmiLoraAnimator": UmiLoraAnimator,
    "UmiPromptTemplate": UmiPromptTemplate,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "UmiPoseLibrary": "UmiAI Pose Library",
    "UmiExpressionMixer": "UmiAI Expression Mixer",
    "UmiSceneComposer": "UmiAI Scene Composer",
    "UmiLoraAnimator": "UmiAI LoRA Strength Animator",
    "UmiPromptTemplate": "UmiAI Prompt Template",
}
