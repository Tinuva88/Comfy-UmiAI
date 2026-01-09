"""
UmiAI Auto Caption - Wrapper for image captioning models.
Works with existing ComfyUI captioner nodes or can use built-in BLIP if available.
"""

import os


class UmiAutoCaption:
    """
    Auto-generate captions for images.
    This is a wrapper/helper node that combines with existing captioners.
    For full functionality, download captioner models from Model Manager (Ctrl+Shift+M).
    """
    
    CAPTION_STYLES = [
        "natural_language",    # BLIP-style natural sentences
        "booru_tags",          # WD14-style comma-separated tags
        "detailed",            # Long, detailed descriptions
        "minimal",             # Short, essential tags only
        "custom"               # Use custom template
    ]
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "caption_input": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "Caption from external captioner node (BLIP, WD14, etc.)"
                }),
                "style": (cls.CAPTION_STYLES, {"default": "booru_tags"}),
            },
            "optional": {
                "trigger_word": ("STRING", {"default": "<sks>", "tooltip": "Prepend trigger word"}),
                "character_name": ("STRING", {"default": "", "tooltip": "Prepend character name"}),
                "remove_tags": ("STRING", {"default": "", "tooltip": "Comma-separated tags to remove"}),
                "add_tags": ("STRING", {"default": "", "tooltip": "Additional tags to add"}),
                "quality_tags": ("BOOLEAN", {"default": True, "tooltip": "Add masterpiece, best quality"}),
                "max_tags": ("INT", {"default": 0, "min": 0, "max": 100, "tooltip": "Max tags (0 = unlimited)"}),
                "tag_threshold": ("FLOAT", {"default": 0.35, "min": 0.0, "max": 1.0, "step": 0.05, 
                                            "tooltip": "Confidence threshold for WD14 output"}),
            }
        }
    
    RETURN_TYPES = ("STRING", "STRING",)
    RETURN_NAMES = ("processed_caption", "raw_caption",)
    CATEGORY = "UmiAI/Dataset"
    FUNCTION = "process_caption"
    
    def process_caption(self, caption_input, style, trigger_word="<sks>", character_name="",
                       remove_tags="", add_tags="", quality_tags=True, max_tags=0, tag_threshold=0.35):
        """Process and format caption for training."""
        
        raw_caption = caption_input.strip()
        
        # Parse tags (handle both comma and newline separated)
        if "\n" in raw_caption:
            tags = [t.strip() for t in raw_caption.split("\n") if t.strip()]
        else:
            tags = [t.strip() for t in raw_caption.split(",") if t.strip()]
        
        # Remove unwanted tags
        if remove_tags:
            remove_list = [t.strip().lower() for t in remove_tags.split(",")]
            tags = [t for t in tags if t.lower() not in remove_list]
        
        # Limit tags if specified
        if max_tags > 0 and len(tags) > max_tags:
            tags = tags[:max_tags]
        
        # Build output based on style
        parts = []
        
        # Add trigger word first
        if trigger_word:
            parts.append(trigger_word)
        
        # Add character name
        if character_name:
            parts.append(character_name)
        
        # Add quality tags (for training)
        if quality_tags:
            parts.append("masterpiece")
            parts.append("best quality")
        
        # Add processed tags
        if style == "natural_language":
            # Keep as sentence
            parts.append(", ".join(tags))
        elif style == "booru_tags":
            # Comma-separated tags
            parts.extend(tags)
        elif style == "detailed":
            parts.extend(tags)
            parts.append("highly detailed")
            parts.append("intricate")
        elif style == "minimal":
            # Only first few essential tags
            parts.extend(tags[:5])
        else:
            # Custom - just join as is
            parts.extend(tags)
        
        # Add extra tags
        if add_tags:
            extra = [t.strip() for t in add_tags.split(",") if t.strip()]
            parts.extend(extra)
        
        processed = ", ".join(parts)
        
        return (processed, raw_caption)


class UmiCaptionEnhancer:
    """
    Enhance captions with character-specific information.
    Useful for preparing training data with consistent character descriptions.
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "base_caption": ("STRING", {"default": "", "multiline": True}),
            },
            "optional": {
                "character_prompt": ("STRING", {"default": "", "multiline": True, 
                                                "tooltip": "Character description from UmiCharacterManager"}),
                "pose_prompt": ("STRING", {"default": "", "tooltip": "Pose from UmiPoseLibrary"}),
                "scene_prompt": ("STRING", {"default": "", "tooltip": "Scene from UmiSceneComposer"}),
                "expression_prompt": ("STRING", {"default": "", "tooltip": "Expression from UmiExpressionMixer"}),
                "camera_tags": ("STRING", {"default": "", "tooltip": "Camera angles from UmiCameraControl"}),
                "merge_mode": (["prepend", "append", "replace"], {"default": "prepend"}),
            }
        }
    
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("enhanced_caption",)
    CATEGORY = "UmiAI/Dataset"
    FUNCTION = "enhance"
    
    def enhance(self, base_caption, character_prompt="", pose_prompt="", scene_prompt="",
                expression_prompt="", camera_tags="", merge_mode="prepend"):
        """Combine caption with character information."""
        
        parts = []
        
        # Collect all UmiAI prompts
        umi_parts = []
        for prompt in [character_prompt, pose_prompt, scene_prompt, expression_prompt, camera_tags]:
            if prompt and prompt.strip():
                umi_parts.append(prompt.strip())
        
        umi_prompt = ", ".join(umi_parts)
        
        # Merge based on mode
        if merge_mode == "prepend":
            if umi_prompt:
                parts.append(umi_prompt)
            if base_caption:
                parts.append(base_caption)
        elif merge_mode == "append":
            if base_caption:
                parts.append(base_caption)
            if umi_prompt:
                parts.append(umi_prompt)
        else:  # replace
            if umi_prompt:
                parts.append(umi_prompt)
            # Ignore base_caption in replace mode
        
        return (", ".join(parts),)


# ==============================================================================
# NODE REGISTRATION
# ==============================================================================

NODE_CLASS_MAPPINGS = {
    "UmiAutoCaption": UmiAutoCaption,
    "UmiCaptionEnhancer": UmiCaptionEnhancer,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "UmiAutoCaption": "UmiAI Auto Caption (Wrapper)",
    "UmiCaptionEnhancer": "UmiAI Caption Enhancer",
}
