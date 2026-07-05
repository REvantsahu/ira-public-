"""UIAutomation element annotator — draws red numbered boxes on clickable elements."""
import os
import json
import uiautomation as auto
from PIL import ImageDraw, ImageFont, Image

def get_clickable_elements():
    """Traverse UIAutomation tree of the active foreground window to find clickable elements."""
    auto.SetGlobalSearchTimeout(0.3)
    
    fg = auto.GetForegroundControl()
    if not fg:
        print("[UIA] No active foreground window found.")
        return []
        
    clickable_types = {
        auto.ControlType.ButtonControl,
        auto.ControlType.HyperlinkControl,
        auto.ControlType.MenuItemControl,
        auto.ControlType.TabItemControl,
        auto.ControlType.ListItemControl,
        auto.ControlType.CheckBoxControl,
        auto.ControlType.RadioButtonControl,
        auto.ControlType.ComboBoxControl,
        auto.ControlType.EditControl,
        auto.ControlType.DocumentControl,
        auto.ControlType.DataItemControl,
        auto.ControlType.TreeItemControl,
    }

    elements = []
    
    try:
        from stop import is_stop_requested
    except Exception:
        def is_stop_requested(): return False

    try:
        walk_count = 0
        for control, depth in auto.WalkControl(fg, includeTop=True, maxDepth=6):
            if is_stop_requested():
                break
            walk_count += 1
            if walk_count > 1000:
                print("[UIA] WalkControl exceeded 1000 controls, aborting for safety.")
                break
            if control.ControlType not in clickable_types:
                continue
            try:
                if getattr(control, 'IsOffscreen', True):
                    continue
                rect = control.BoundingRectangle
                if rect.width() <= 4 or rect.height() <= 4:
                    continue
                # Skip tiny or off-screen elements
                if rect.left < -100 or rect.top < -100:
                    continue
                    
                center_x = rect.left + (rect.width() // 2)
                center_y = rect.top + (rect.height() // 2)
                
                elements.append({
                    "rect": (rect.left, rect.top, rect.right, rect.bottom),
                    "center": (center_x, center_y),
                    "name": getattr(control, 'Name', '') or '',
                    "type": control.ControlType
                })
            except Exception:
                continue
    except Exception as e:
        print(f"[UIA] Walk error: {e}")
        
    return elements


def annotate_image(img: Image.Image) -> dict:
    """Draw clean bounding boxes and numbers on the image. Return mapping of number -> center coords."""
    elements = get_clickable_elements()
    draw = ImageDraw.Draw(img)
    
    # Try to load a clean font
    font = None
    for fname in ["arial.ttf", "Arial.ttf", "segoeui.ttf", "SegoeUI.ttf"]:
        try:
            font = ImageFont.truetype(fname, 13)
            break
        except IOError:
            continue
    if font is None:
        try:
            font = ImageFont.truetype("C:\\Windows\\Fonts\\arial.ttf", 13)
        except Exception:
            font = ImageFont.load_default()
        
    mapping = {}
    
    # Sort elements top-to-bottom, left-to-right
    elements = sorted(elements, key=lambda e: (e["rect"][1], e["rect"][0]))
    
    for idx, el in enumerate(elements, start=1):
        num_str = str(idx)
        left, top, right, bottom = el["rect"]
        center_x, center_y = el["center"]
        
        mapping[num_str] = (center_x, center_y)
        
        # Thin red bounding box (1px outline only)
        draw.rectangle([left, top, right, bottom], outline=(255, 40, 40), width=1)
        
        # Small number label — red background, white text
        try:
            text_bbox = draw.textbbox((0, 0), num_str, font=font)
            text_w = text_bbox[2] - text_bbox[0]
            text_h = text_bbox[3] - text_bbox[1]
        except AttributeError:
            text_w = len(num_str) * 7
            text_h = 12
            
        # Number badge — positioned at top-left of the box
        badge_x = left
        badge_y = top - text_h - 4
        if badge_y < 0:
            badge_y = top + 1  # Inside the box if no room above
        
        draw.rectangle(
            [badge_x, badge_y, badge_x + text_w + 6, badge_y + text_h + 3],
            fill=(220, 30, 30)
        )
        draw.text(
            (badge_x + 3, badge_y + 1),
            num_str,
            fill=(255, 255, 255),
            font=font
        )

    return mapping


def save_mapping(mapping: dict):
    """Save the click mapping to scratch directory."""
    scratch_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scratch")
    os.makedirs(scratch_dir, exist_ok=True)
    map_file = os.path.join(scratch_dir, "click_map.json")
    with open(map_file, "w", encoding="utf-8") as f:
        json.dump(mapping, f)


def get_mapping() -> dict:
    """Load the click mapping."""
    map_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scratch", "click_map.json")
    if os.path.exists(map_file):
        try:
            with open(map_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}
