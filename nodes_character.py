"""
UmiAI Character Manager Node
Manages consistent character generation with outfit and emotion variations.
"""

import os
import yaml
import folder_paths
from PIL import Image
import numpy as np
import torch

# ==============================================================================
# CHARACTER LOADER
# ==============================================================================

class CharacterLoader:
    """Loads and caches character profiles from the characters/ folder."""
    
    _cache = {}
    _mtime_cache = {}
    
    @classmethod
    def get_characters_path(cls):
        """Get the path to the characters folder."""
        # Check in the UmiAI custom node folder
        node_path = os.path.dirname(os.path.abspath(__file__))
        chars_path = os.path.join(node_path, "characters")
        if os.path.isdir(chars_path):
            return chars_path
        return None
    
    @classmethod
    def list_characters(cls):
        """List all available character names."""
        chars_path = cls.get_characters_path()
        if not chars_path:
            return ["none"]
        
        characters = []
        for item in os.listdir(chars_path):
            item_path = os.path.join(chars_path, item)
            profile_path = os.path.join(item_path, "profile.yaml")
            if os.path.isdir(item_path) and os.path.isfile(profile_path):
                characters.append(item)
        
        return characters if characters else ["none"]
    
    @classmethod
    def load_character(cls, name):
        """Load a character profile, using cache if available."""
        chars_path = cls.get_characters_path()
        if not chars_path or name == "none":
            return None
        
        profile_path = os.path.join(chars_path, name, "profile.yaml")
        if not os.path.isfile(profile_path):
            return None
        
        # Check if cached and still valid
        mtime = os.path.getmtime(profile_path)
        if name in cls._cache and cls._mtime_cache.get(name) == mtime:
            return cls._cache[name]
        
        # Load fresh
        try:
            with open(profile_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                data['_folder'] = os.path.join(chars_path, name)
                cls._cache[name] = data
                cls._mtime_cache[name] = mtime
                return data
        except Exception as e:
            print(f"[UmiAI Character] Error loading {name}: {e}")
            return None
    
    @classmethod
    def get_outfits(cls, name):
        """Get list of outfit names for a character."""
        data = cls.load_character(name)
        if data and 'outfits' in data:
            return list(data['outfits'].keys())
        return ["default"]
    
    @classmethod
    def get_emotions(cls, name):
        """Get list of emotion names for a character."""
        data = cls.load_character(name)
        if data and 'emotions' in data:
            return list(data['emotions'].keys())
        return ["neutral"]
    
    @classmethod
    def get_poses(cls, name):
        """Get list of pose names for a character."""
        data = cls.load_character(name)
        if data and 'poses' in data:
            return list(data['poses'].keys())
        return ["none"]
    
    @classmethod
    def get_reference_image_path(cls, name):
        """Get path to reference image if it exists."""
        data = cls.load_character(name)
        if not data:
            return None
        
        folder = data.get('_folder', '')
        # Check common image names
        for ext in ['png', 'jpg', 'jpeg', 'webp']:
            for basename in ['reference', 'ref', 'base']:
                path = os.path.join(folder, f"{basename}.{ext}")
                if os.path.isfile(path):
                    return path
        return None
    
    @classmethod
    def get_pose_image_path(cls, name, pose):
        """Get path to pose ControlNet image if it exists."""
        data = cls.load_character(name)
        if not data or not pose or pose == "none":
            return None
        
        folder = data.get('_folder', '')
        pose_lower = pose.lower()
        
        if 'poses' in data and pose_lower in data['poses']:
            pose_data = data['poses'][pose_lower]
            if isinstance(pose_data, dict) and 'controlnet' in pose_data:
                pose_path = os.path.join(folder, pose_data['controlnet'])
                if os.path.isfile(pose_path):
                    return pose_path
        return None


# ==============================================================================
# CHARACTER MANAGER NODE
# ==============================================================================

class UmiCharacterManager:
    """
    Manages consistent character generation with outfit and emotion variations.
    Outputs prompts and reference images for use with IP-Adapter.
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        characters = CharacterLoader.list_characters()
        
        return {
            "required": {
                "character": (characters, {"default": characters[0] if characters else "none"}),
                "outfit": ("STRING", {"default": "casual", "multiline": False}),
                "emotion": ("STRING", {"default": "neutral", "multiline": False}),
            },
            "optional": {
                "pose": ("STRING", {"default": "standing_front", "multiline": False}),
                "include_lora": ("BOOLEAN", {"default": True}),
                "custom_additions": ("STRING", {"default": "", "multiline": True}),
            }
        }
    
    RETURN_TYPES = ("STRING", "STRING", "STRING", "IMAGE", "IMAGE",)
    RETURN_NAMES = ("prompt", "negative", "lora_string", "reference_image", "pose_image",)
    FUNCTION = "generate"
    CATEGORY = "UmiAI/Character"
    
    def generate(self, character, outfit, emotion, 
                 pose="", include_lora=True, custom_additions=""):
        """Generate a complete character prompt with the specified outfit, emotion, and pose."""
        
        # Load character data
        data = CharacterLoader.load_character(character)
        if not data:
            return ("", "", "", self._empty_image(), self._empty_image())
        
        # Build prompt parts
        parts = []
        
        # Add LoRA if requested
        lora_string = ""
        if include_lora and data.get('lora'):
            lora_name = data['lora']
            lora_strength = data.get('lora_strength', 1.0)
            lora_string = f"<lora:{lora_name}:{lora_strength}>"
            parts.append(lora_string)
        
        # Add base character prompt
        if data.get('base_prompt'):
            parts.append(data['base_prompt'])
        
        # Add outfit
        outfit_lower = outfit.lower()
        if 'outfits' in data and outfit_lower in data['outfits']:
            outfit_data = data['outfits'][outfit_lower]
            if isinstance(outfit_data, dict):
                parts.append(outfit_data.get('prompt', ''))
            else:
                parts.append(str(outfit_data))
        
        # Add emotion
        emotion_lower = emotion.lower()
        if 'emotions' in data and emotion_lower in data['emotions']:
            emotion_data = data['emotions'][emotion_lower]
            if isinstance(emotion_data, dict):
                parts.append(emotion_data.get('prompt', ''))
            else:
                parts.append(str(emotion_data))
        
        # Add pose prompt
        pose_lower = pose.lower() if pose else ""
        if pose_lower and 'poses' in data and pose_lower in data['poses']:
            pose_data = data['poses'][pose_lower]
            if isinstance(pose_data, dict):
                parts.append(pose_data.get('prompt', ''))
            else:
                parts.append(str(pose_data))
        
        # Add custom additions
        if custom_additions:
            parts.append(custom_additions)
        
        # Combine into final prompt
        prompt = ", ".join(filter(None, parts))
        
        # Get negative prompt
        negative = data.get('negative_prompt', '')
        
        # Load reference image if available
        ref_image = self._load_reference_image(character)
        
        # Load pose ControlNet image if available
        pose_image = self._load_pose_image(character, pose)
        
        return (prompt, negative, lora_string, ref_image, pose_image)
    
    def _empty_image(self):
        """Return an empty placeholder image."""
        # Create a 64x64 black image as placeholder
        empty = np.zeros((64, 64, 3), dtype=np.float32)
        return torch.from_numpy(empty).unsqueeze(0)
    
    def _load_reference_image(self, character):
        """Load the reference image for a character."""
        ref_path = CharacterLoader.get_reference_image_path(character)
        if not ref_path:
            return self._empty_image()
        
        try:
            img = Image.open(ref_path).convert('RGB')
            img_array = np.array(img).astype(np.float32) / 255.0
            return torch.from_numpy(img_array).unsqueeze(0)
        except Exception as e:
            print(f"[UmiAI Character] Error loading reference image: {e}")
            return self._empty_image()
    
    def _load_pose_image(self, character, pose):
        """Load the pose ControlNet image."""
        pose_path = CharacterLoader.get_pose_image_path(character, pose)
        if not pose_path:
            return self._empty_image()
        
        try:
            img = Image.open(pose_path).convert('RGB')
            img_array = np.array(img).astype(np.float32) / 255.0
            return torch.from_numpy(img_array).unsqueeze(0)
        except Exception as e:
            print(f"[UmiAI Character] Error loading pose image: {e}")
            return self._empty_image()


# ==============================================================================
# CHARACTER BATCH NODE
# ==============================================================================

class UmiCharacterBatch:
    """
    Generates batch variations of a character.
    Outputs all outfits OR all emotions for batch processing.
    """
    
    BATCH_MODES = ["all_outfits", "all_emotions", "all_poses", "outfit_emotion_matrix"]
    
    @classmethod
    def INPUT_TYPES(cls):
        characters = CharacterLoader.list_characters()
        
        return {
            "required": {
                "character": (characters, {"default": characters[0] if characters else "none"}),
                "batch_mode": (cls.BATCH_MODES, {"default": "all_outfits"}),
            },
            "optional": {
                "fixed_outfit": ("STRING", {"default": "", "multiline": False}),
                "fixed_emotion": ("STRING", {"default": "neutral", "multiline": False}),
                "fixed_pose": ("STRING", {"default": "standing_front", "multiline": False}),
                "include_lora": ("BOOLEAN", {"default": True}),
            }
        }
    
    RETURN_TYPES = ("STRING", "STRING", "INT",)
    RETURN_NAMES = ("prompts_list", "labels_list", "count",)
    FUNCTION = "generate_batch"
    CATEGORY = "UmiAI/Character"
    OUTPUT_IS_LIST = (True, True, False)
    
    def generate_batch(self, character, batch_mode, 
                       fixed_outfit="", fixed_emotion="neutral", fixed_pose="standing_front",
                       include_lora=True):
        """Generate batch prompts based on mode."""
        
        data = CharacterLoader.load_character(character)
        if not data:
            return ([""], ["none"], 0)
        
        prompts = []
        labels = []
        
        if batch_mode == "all_outfits":
            outfits = list(data.get('outfits', {}).keys()) or ["default"]
            for outfit in outfits:
                prompt = self._build_prompt(data, outfit, fixed_emotion, fixed_pose, include_lora)
                prompts.append(prompt)
                labels.append(f"{character}_{outfit}_{fixed_emotion}")
        
        elif batch_mode == "all_emotions":
            emotions = list(data.get('emotions', {}).keys()) or ["neutral"]
            for emotion in emotions:
                prompt = self._build_prompt(data, fixed_outfit or "casual", emotion, fixed_pose, include_lora)
                prompts.append(prompt)
                labels.append(f"{character}_{fixed_outfit or 'casual'}_{emotion}")
        
        elif batch_mode == "all_poses":
            poses = list(data.get('poses', {}).keys()) or ["standing_front"]
            for pose in poses:
                prompt = self._build_prompt(data, fixed_outfit or "casual", fixed_emotion, pose, include_lora)
                prompts.append(prompt)
                labels.append(f"{character}_{pose}")
        
        elif batch_mode == "outfit_emotion_matrix":
            outfits = list(data.get('outfits', {}).keys()) or ["default"]
            emotions = list(data.get('emotions', {}).keys()) or ["neutral"]
            for outfit in outfits:
                for emotion in emotions:
                    prompt = self._build_prompt(data, outfit, emotion, fixed_pose, include_lora)
                    prompts.append(prompt)
                    labels.append(f"{character}_{outfit}_{emotion}")
        
        return (prompts, labels, len(prompts))
    
    def _build_prompt(self, data, outfit, emotion, pose, include_lora):
        """Build a single prompt from character data."""
        parts = []
        
        # LoRA
        if include_lora and data.get('lora'):
            parts.append(f"<lora:{data['lora']}:{data.get('lora_strength', 1.0)}>")
        
        # Base prompt
        if data.get('base_prompt'):
            parts.append(data['base_prompt'])
        
        # Outfit
        outfit_lower = outfit.lower() if outfit else ""
        if outfit_lower and 'outfits' in data and outfit_lower in data['outfits']:
            outfit_data = data['outfits'][outfit_lower]
            if isinstance(outfit_data, dict):
                parts.append(outfit_data.get('prompt', ''))
            else:
                parts.append(str(outfit_data))
        
        # Emotion
        emotion_lower = emotion.lower() if emotion else ""
        if emotion_lower and 'emotions' in data and emotion_lower in data['emotions']:
            emotion_data = data['emotions'][emotion_lower]
            if isinstance(emotion_data, dict):
                parts.append(emotion_data.get('prompt', ''))
            else:
                parts.append(str(emotion_data))
        
        # Pose
        pose_lower = pose.lower() if pose else ""
        if pose_lower and 'poses' in data and pose_lower in data['poses']:
            pose_data = data['poses'][pose_lower]
            if isinstance(pose_data, dict):
                parts.append(pose_data.get('prompt', ''))
            else:
                parts.append(str(pose_data))
        
        return ", ".join(filter(None, parts))


# ==============================================================================
# SPRITE EXPORT NODE
# ==============================================================================

class UmiSpriteExport:
    """
    Saves character sprites with organized folder structure.
    Output: character_name/outfit/emotion_pose.png
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "character_name": ("STRING", {"default": "character"}),
                "outfit": ("STRING", {"default": "casual"}),
                "emotion": ("STRING", {"default": "neutral"}),
            },
            "optional": {
                "pose": ("STRING", {"default": ""}),
                "output_prefix": ("STRING", {"default": "sprites"}),
                "format": (["png", "webp"], {"default": "png"}),
                "label": ("STRING", {"default": ""}),
            }
        }
    
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("output_path",)
    FUNCTION = "save_sprite"
    CATEGORY = "UmiAI/Character"
    OUTPUT_NODE = True
    
    def save_sprite(self, images, character_name, outfit, emotion,
                    pose="", output_prefix="sprites", format="png", label=""):
        """Save sprite to organized folder structure."""
        import folder_paths
        from datetime import datetime
        
        # Build output path: output/sprites/character/outfit/
        output_dir = folder_paths.get_output_directory()
        sprite_dir = os.path.join(output_dir, output_prefix, character_name, outfit)
        os.makedirs(sprite_dir, exist_ok=True)
        
        # Build filename
        if label:
            filename = f"{label}.{format}"
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            pose_part = f"_{pose}" if pose else ""
            filename = f"{emotion}{pose_part}_{timestamp}.{format}"
        
        filepath = os.path.join(sprite_dir, filename)
        
        # Convert tensor to image and save
        for i, image in enumerate(images):
            img_array = image.cpu().numpy()
            img_array = (img_array * 255).astype(np.uint8)
            
            if len(images) > 1:
                base, ext = os.path.splitext(filepath)
                save_path = f"{base}_{i:03d}{ext}"
            else:
                save_path = filepath
            
            img = Image.fromarray(img_array)
            
            if format == "png":
                img.save(save_path, "PNG")
            else:
                img.save(save_path, "WEBP", quality=95)
            
            print(f"[UmiAI Sprite] Saved: {save_path}")
        
        return (sprite_dir,)


# ==============================================================================
# CHARACTER PROFILE INFO NODE
# ==============================================================================

class UmiCharacterInfo:
    """
    Outputs information about a character's available options.
    Useful for debugging and planning.
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        characters = CharacterLoader.list_characters()
        
        return {
            "required": {
                "character": (characters, {"default": characters[0] if characters else "none"}),
            }
        }
    
    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "INT", "INT", "INT",)
    RETURN_NAMES = ("character_info", "outfits_list", "emotions_list", "poses_list", "outfit_count", "emotion_count", "pose_count",)
    FUNCTION = "get_info"
    CATEGORY = "UmiAI/Character"
    
    def get_info(self, character):
        """Get character profile information."""
        data = CharacterLoader.load_character(character)
        if not data:
            return ("Character not found", "", "", "", 0, 0, 0)
        
        outfits = list(data.get('outfits', {}).keys())
        emotions = list(data.get('emotions', {}).keys())
        poses = list(data.get('poses', {}).keys())
        
        info_lines = [
            f"Name: {data.get('name', character)}",
            f"Description: {data.get('description', 'N/A')}",
            f"LoRA: {data.get('lora', 'None')} @ {data.get('lora_strength', 1.0)}",
            f"Outfits ({len(outfits)}): {', '.join(outfits)}",
            f"Emotions ({len(emotions)}): {', '.join(emotions)}",
            f"Poses ({len(poses)}): {', '.join(poses)}",
        ]
        
        return (
            "\n".join(info_lines),
            ", ".join(outfits),
            ", ".join(emotions),
            ", ".join(poses),
            len(outfits),
            len(emotions),
            len(poses),
        )


# ==============================================================================
# NODE REGISTRATION
# ==============================================================================

NODE_CLASS_MAPPINGS = {
    "UmiCharacterManager": UmiCharacterManager,
    "UmiCharacterBatch": UmiCharacterBatch,
    "UmiSpriteExport": UmiSpriteExport,
    "UmiCharacterInfo": UmiCharacterInfo,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "UmiCharacterManager": "UmiAI Character Manager",
    "UmiCharacterBatch": "UmiAI Character Batch Generator",
    "UmiSpriteExport": "UmiAI Sprite Export",
    "UmiCharacterInfo": "UmiAI Character Info",
}
