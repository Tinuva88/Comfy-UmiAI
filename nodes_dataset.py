"""
UmiAI Dataset Export - LoRA Training Dataset Generator
Creates properly formatted image+caption pairs for LoRA training (Kohya-compatible).
"""

import os
import json
import yaml
import re
from datetime import datetime


class UmiDatasetExport:
    """
    Export character images with auto-generated captions for LoRA training.
    Creates Kohya-compatible folder structure with repeats.
    """
    
    OUTPUT_FORMATS = ["kohya", "dreambooth", "simple"]
    CAPTION_FORMATS = ["txt", "caption", "json"]
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "dataset_name": ("STRING", {"default": "my_character"}),
                "trigger_word": ("STRING", {"default": "<sks>", "tooltip": "Trigger word for your LoRA"}),
                "repeats": ("INT", {"default": 10, "min": 1, "max": 100, "tooltip": "Number of repeats for training"}),
                "output_format": (cls.OUTPUT_FORMATS, {"default": "kohya"}),
                "caption_format": (cls.CAPTION_FORMATS, {"default": "txt"}),
            },
            "optional": {
                "character_name": ("STRING", {"default": "", "tooltip": "Character name to include in captions"}),
                "base_caption": ("STRING", {"default": "", "multiline": True, "tooltip": "Base caption for all images"}),
                "outfit_tag": ("STRING", {"default": ""}),
                "emotion_tag": ("STRING", {"default": ""}),
                "pose_tag": ("STRING", {"default": ""}),
                "camera_tags": ("STRING", {"default": ""}),
                "custom_tags": ("STRING", {"default": "", "tooltip": "Additional tags to include"}),
                "add_quality_tags": ("BOOLEAN", {"default": True}),
                "flip_augmentation": ("BOOLEAN", {"default": False, "tooltip": "Create horizontally flipped copies"}),
            }
        }
    
    RETURN_TYPES = ("STRING", "STRING", "INT",)
    RETURN_NAMES = ("output_path", "status", "image_count",)
    CATEGORY = "UmiAI/Dataset"
    FUNCTION = "export_dataset"
    OUTPUT_NODE = True
    
    def export_dataset(self, images, dataset_name, trigger_word, repeats, output_format,
                       caption_format, character_name="", base_caption="", outfit_tag="",
                       emotion_tag="", pose_tag="", camera_tags="", custom_tags="",
                       add_quality_tags=True, flip_augmentation=False):
        """Export images with captions for LoRA training."""
        import torch
        from PIL import Image
        import numpy as np
        import folder_paths
        
        # Setup output directory
        output_base = folder_paths.get_output_directory()
        dataset_dir = os.path.join(output_base, "datasets", dataset_name)
        
        # Create folder structure based on format
        if output_format == "kohya":
            # Kohya format: dataset_name/10_character_name/
            folder_name = f"{repeats}_{trigger_word.strip('<>') if trigger_word else dataset_name}"
            image_dir = os.path.join(dataset_dir, folder_name)
        elif output_format == "dreambooth":
            # Dreambooth format: class folder structure
            image_dir = os.path.join(dataset_dir, "instance")
        else:
            # Simple format: flat structure
            image_dir = dataset_dir
        
        os.makedirs(image_dir, exist_ok=True)
        
        # Build caption template
        caption_parts = []
        
        # Add trigger word
        if trigger_word:
            caption_parts.append(trigger_word)
        
        # Add character name
        if character_name:
            caption_parts.append(character_name)
        
        # Add base caption
        if base_caption:
            caption_parts.append(base_caption)
        
        # Add tags
        for tag in [outfit_tag, emotion_tag, pose_tag, camera_tags, custom_tags]:
            if tag and tag.strip():
                caption_parts.append(tag.strip())
        
        # Add quality tags
        if add_quality_tags:
            caption_parts.append("masterpiece, best quality, high resolution")
        
        base_caption_text = ", ".join(caption_parts)
        
        # Process images
        image_count = 0
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        for i, img_tensor in enumerate(images):
            # Convert tensor to PIL Image
            img_np = (img_tensor.cpu().numpy() * 255).astype(np.uint8)
            if img_np.ndim == 3 and img_np.shape[0] in [3, 4]:
                img_np = np.transpose(img_np, (1, 2, 0))
            pil_img = Image.fromarray(img_np)
            
            # Generate filename
            base_name = f"{dataset_name}_{timestamp}_{i:04d}"
            
            # Save image
            img_path = os.path.join(image_dir, f"{base_name}.png")
            pil_img.save(img_path, "PNG")
            image_count += 1
            
            # Generate and save caption
            caption = base_caption_text
            
            if caption_format == "txt":
                caption_path = os.path.join(image_dir, f"{base_name}.txt")
                with open(caption_path, 'w', encoding='utf-8') as f:
                    f.write(caption)
            elif caption_format == "caption":
                caption_path = os.path.join(image_dir, f"{base_name}.caption")
                with open(caption_path, 'w', encoding='utf-8') as f:
                    f.write(caption)
            elif caption_format == "json":
                caption_path = os.path.join(image_dir, f"{base_name}.json")
                with open(caption_path, 'w', encoding='utf-8') as f:
                    json.dump({"caption": caption, "tags": caption.split(", ")}, f, indent=2)
            
            # Flip augmentation
            if flip_augmentation:
                flipped = pil_img.transpose(Image.FLIP_LEFT_RIGHT)
                flip_name = f"{dataset_name}_{timestamp}_{i:04d}_flip"
                
                flip_img_path = os.path.join(image_dir, f"{flip_name}.png")
                flipped.save(flip_img_path, "PNG")
                image_count += 1
                
                if caption_format == "txt":
                    flip_caption_path = os.path.join(image_dir, f"{flip_name}.txt")
                    with open(flip_caption_path, 'w', encoding='utf-8') as f:
                        f.write(caption)
                elif caption_format == "caption":
                    flip_caption_path = os.path.join(image_dir, f"{flip_name}.caption")
                    with open(flip_caption_path, 'w', encoding='utf-8') as f:
                        f.write(caption)
                elif caption_format == "json":
                    flip_caption_path = os.path.join(image_dir, f"{flip_name}.json")
                    with open(flip_caption_path, 'w', encoding='utf-8') as f:
                        json.dump({"caption": caption, "tags": caption.split(", ")}, f, indent=2)
        
        # Create dataset config file
        config_path = os.path.join(dataset_dir, "dataset_config.yaml")
        config = {
            "dataset_name": dataset_name,
            "trigger_word": trigger_word,
            "repeats": repeats,
            "image_count": image_count,
            "output_format": output_format,
            "caption_format": caption_format,
            "created": datetime.now().isoformat(),
        }
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f)
        
        status = f"Exported {image_count} images to {image_dir}"
        
        return (dataset_dir, status, image_count)


class UmiCaptionGenerator:
    """
    Generate captions for existing images based on character profile.
    Useful for batch captioning of manually created variations.
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "character_name": ("STRING", {"default": ""}),
                "trigger_word": ("STRING", {"default": "<sks>"}),
            },
            "optional": {
                "outfit": ("STRING", {"default": ""}),
                "emotion": ("STRING", {"default": ""}),
                "pose": ("STRING", {"default": ""}),
                "background": ("STRING", {"default": ""}),
                "custom_tags": ("STRING", {"default": "", "multiline": True}),
                "add_quality_tags": ("BOOLEAN", {"default": True}),
                "shuffle_tags": ("BOOLEAN", {"default": False, "tooltip": "Randomize tag order for training variety"}),
            }
        }
    
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("caption",)
    CATEGORY = "UmiAI/Dataset"
    FUNCTION = "generate_caption"
    
    def generate_caption(self, character_name, trigger_word, outfit="", emotion="",
                         pose="", background="", custom_tags="", add_quality_tags=True,
                         shuffle_tags=False):
        """Generate a training caption from components."""
        import random
        
        parts = []
        
        # Always start with trigger word
        if trigger_word:
            parts.append(trigger_word)
        
        # Add character name
        if character_name:
            parts.append(character_name)
        
        # Collect variable tags
        variable_tags = []
        if outfit:
            variable_tags.append(outfit)
        if emotion:
            variable_tags.append(emotion)
        if pose:
            variable_tags.append(pose)
        if background:
            variable_tags.append(background)
        if custom_tags:
            for tag in custom_tags.split(','):
                tag = tag.strip()
                if tag:
                    variable_tags.append(tag)
        
        # Optionally shuffle
        if shuffle_tags:
            random.shuffle(variable_tags)
        
        parts.extend(variable_tags)
        
        # Add quality tags
        if add_quality_tags:
            parts.append("masterpiece, best quality, high resolution")
        
        caption = ", ".join(parts)
        
        return (caption,)


# ==============================================================================
# NODE REGISTRATION
# ==============================================================================

NODE_CLASS_MAPPINGS = {
    "UmiDatasetExport": UmiDatasetExport,
    "UmiCaptionGenerator": UmiCaptionGenerator,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "UmiDatasetExport": "UmiAI Dataset Export (LoRA Training)",
    "UmiCaptionGenerator": "UmiAI Caption Generator",
}
