import os
import json
import folder_paths

try:
    from huggingface_hub import hf_hub_download
    HF_HUB_AVAILABLE = True
except Exception:
    HF_HUB_AVAILABLE = False


class AnyType(str):
    def __ne__(self, __value: object) -> bool:
        return False


any_type = AnyType("*")


def resolve_path(relative_path):
    base = getattr(folder_paths, "base_path", os.getcwd())
    return os.path.abspath(os.path.join(base, relative_path))


def get_installed_version_info():
    registry_path = resolve_path("umi_installed_models.json")
    if os.path.exists(registry_path):
        try:
            with open(registry_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


class UmiModelManager:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "repo_id": ("STRING", {"default": "Tinuva/Comfy-Umi", "multiline": False}),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("repo_id",)
    FUNCTION = "process"
    CATEGORY = "UmiAI/manager"

    def process(self, repo_id):
        return (repo_id,)


class UmiModelSelector:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "repo_id": ("STRING", {"default": "Tinuva/Comfy-Umi", "multiline": False}),
            },
            "hidden": {
                "model_name": ("STRING", {"default": ""}),
                "version": ("STRING", {"default": "auto"}),
            }
        }

    @classmethod
    def VALIDATE_INPUTS(cls, input_types):
        return True

    RETURN_TYPES = (any_type,)
    RETURN_NAMES = ("model_path",)
    FUNCTION = "get_path"
    CATEGORY = "UmiAI/manager"

    def get_path(self, repo_id, model_name="", version="auto"):
        if not HF_HUB_AVAILABLE:
            print("[UmiAI] ModelSelector Error: huggingface_hub is not installed.")
            return ("",)

        try:
            path = hf_hub_download(repo_id=repo_id, filename="model_updater.json")
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            models = data.get("models", [])
            target_name = str(model_name).strip()

            active_ver = None
            if version and version != "auto" and version.strip():
                active_ver = version.strip()
            else:
                registry = get_installed_version_info()
                active_ver = registry.get(target_name)
                if active_ver is None:
                    for k, v in registry.items():
                        if k.strip().lower() == target_name.lower():
                            active_ver = v
                            break

            def normalize_ver(v):
                return str(v).lower().lstrip('v').strip()

            found = None
            if active_ver:
                t_ver = normalize_ver(active_ver)
                matching_names = [m for m in models if m["name"].strip().lower() == target_name.lower()]
                for m in matching_names:
                    if normalize_ver(m["version"]) == t_ver:
                        found = m
                        break

            if found is None:
                matching_names = [m for m in models if m["name"].strip().lower() == target_name.lower()]
                if matching_names:
                    try:
                        from packaging import version as pkg_version
                        matching_names.sort(key=lambda x: pkg_version.parse(x["version"]), reverse=True)
                    except Exception:
                        matching_names.sort(key=lambda x: str(x["version"]), reverse=True)
                    found = matching_names[0]

            if found:
                local_path = found["local_path"]
                norm_path = local_path.replace("\\", "/")

                standard_prefixes = [
                    "models/loras/",
                    "models/checkpoints/",
                    "models/vae/",
                    "models/controlnet/",
                    "models/style_models/",
                    "models/upscale_models/",
                    "models/clip/",
                    "models/unet/",
                    "models/diffusers/",
                    "models/configs/"
                ]

                relative_path = norm_path
                for prefix in standard_prefixes:
                    if norm_path.startswith(prefix):
                        relative_path = norm_path[len(prefix):]
                        break

                relative_path = relative_path.replace("\\", "/")
                print(f"[UmiAI] ModelSelector Result: {relative_path}")
                return (relative_path,)

            print(f"[UmiAI] ModelSelector: Model '{model_name}' not found.")
            return ("",)

        except Exception as e:
            print(f"[UmiAI] ModelSelector Error: {e}")
            return ("",)


NODE_CLASS_MAPPINGS = {
    "UmiModelManager": UmiModelManager,
    "UmiModelSelector": UmiModelSelector,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "UmiModelManager": "Umi Model Manager",
    "UmiModelSelector": "Umi Model Selector",
}
