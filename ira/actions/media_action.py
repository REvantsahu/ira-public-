"""
actions/media_action.py — Action Converter for IRA Native Media & Image Pipeline
"""

import os

def create_media_action(parameters: dict, player=None, speak=None) -> str:
    prompt = parameters.get("prompt", "")
    file_name = parameters.get("file_name", "generated_media")
    path = parameters.get("path", "")
    set_as_wallpaper = parameters.get("set_as_wallpaper", False)
    
    if not path:
        path = os.path.join(os.path.expanduser("~"), "Pictures", "IRA_Generated")
    os.makedirs(path, exist_ok=True)
    
    full_file_path = os.path.join(path, f"{file_name}.png")
    
    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (1024, 768), color=(15, 15, 26))
        d = ImageDraw.Draw(img)
        d.text((50, 50), f"IRA Media Artifact: {prompt[:80]}", fill=(0, 212, 255))
        img.save(full_file_path)
        
        wallpaper_set = False
        if set_as_wallpaper:
            try:
                from actions.desktop import set_wallpaper
                wallpaper_set = set_wallpaper(full_file_path)
            except Exception:
                pass
        
        if not set_as_wallpaper:
            lower_prompt = prompt.lower()
            lower_name = file_name.lower()
            if "wallpaper" in lower_prompt or "wallpaper" in lower_name:
                try:
                    from actions.desktop import set_wallpaper
                    wallpaper_set = set_wallpaper(full_file_path)
                except Exception:
                    pass
        
        if wallpaper_set:
            return f"Media created and set as wallpaper successfully at: {full_file_path}"
        return f"Media created successfully at: {full_file_path}"
    except Exception as e:
        return f"Media generation process attempted for '{prompt}' at {full_file_path}: {e}"
