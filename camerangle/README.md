# ComfyUI Camera Angle Selector

A ComfyUI custom node that provides an interactive 3D interface for selecting camera angles for the FAL multi angle lora [https://huggingface.co/fal/Qwen-Image-Edit-2511-Multiple-Angles-LoRA] for **Qwen-Image-Edit-2511**. Select from 96 different camera angle combinations (8 view directions × 4 height angles × 3 shot sizes) with visual feedback and multi-selection support.

![Camera Angle Selector Screenshot]
<img width="1849" height="1275" alt="Screenshot 2026-01-10 112331" src="https://github.com/user-attachments/assets/451e4a70-9275-4263-8cd9-d6fc0940a7f9" />

## Features

- **3D Visualization**: Interactive 3D scene showing camera positions around a central subject
- **Multi-Selection**: Select multiple camera angles simultaneously
- **Color-Coded Cameras**: Direction-based colors (green=front, red=back) with height indicator rings
- **Three Shot Size Layers**: Close-up (inner), Medium (middle), Wide (outer) rings
- **Filter Controls**: Filter by view direction, height angle, and shot size
- **Drag to Rotate**: Click and drag to rotate the 3D scene
- **Zoom**: Mouse wheel to zoom in/out
- **Resizable**: Node scales with 1:1 aspect ratio 3D viewport
- **Selection List**: View and manage selected angles with individual removal
- **List Output**: Returns a list of formatted prompt strings

## Camera Angles

### View Directions (8 angles)
- Front view
- Front-right quarter view
- Right side view
- Back-right quarter view
- Back view
- Back-left quarter view
- Left side view
- Front-left quarter view

### Height Angles (4 types)
- Low-angle shot
- Eye-level shot
- Elevated shot
- High-angle shot

### Shot Sizes (3 types)
- Close-up
- Medium shot
- Wide shot

**Total: 96 unique camera angle combinations**

## Installation

### Prerequisites
- ComfyUI installed and running
- Python 3.8 or higher

### Step-by-Step Installation

1. **Navigate to ComfyUI's custom_nodes directory:**
   ```bash
   cd ComfyUI/custom_nodes
   ```

2. **Clone or copy this repository:**
   ```bash
   git clone <repository-url> ComfyUI_CameraAngleSelector
   ```
   
   Or if you have the files locally:
   ```bash
   cp -r /path/to/ComfyUI_CameraAngleSelector .
   ```

3. **Restart ComfyUI** to load the new node.

## Usage

### In ComfyUI

1. **Add the Node:**
   - Right-click in the node editor
   - Search for "Camera Angle Selector"
   - Add the node to your workflow

2. **Select Camera Angles:**
   - Click on the 3D visualization to open the full interface
   - Click on camera icons to select/deselect angles
   - Drag the scene to rotate the view
   - Use filters to narrow down visible cameras
   - Use "Select Visible" to select all currently filtered cameras
   - Use "Clear All" to deselect all cameras

3. **Connect the Output:**
   - Connect the `selected_angles` output to any node that accepts string inputs
   - The output is a list of strings, one per selected camera angle

### Output Format

Each selected camera angle is returned as a formatted string:

```
<sks> {view_direction} {height_angle} {shot_size}
```

**Example outputs:**
```
<sks> front view low-angle shot close-up
<sks> front-right quarter view eye-level shot medium shot
<sks> back view high-angle shot wide shot
```

## Node Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `selected_indices` | STRING | Internal parameter (auto-managed by the 3D interface) |

## Node Outputs

| Output | Type | Description |
|--------|------|-------------|
| `selected_angles` | STRING (List) | List of selected camera angle prompt strings |

## Interface Controls

### 3D View
- **Click** on a camera to select/deselect it
- **Drag** to rotate the view around the subject
- **Hover** over cameras to see their details

### Filters
- **View Direction**: Filter by front, side, or back views
- **Height Angle**: Filter by low, eye-level, elevated, or high angles
- **Shot Size**: Filter by close-up, medium, or wide shots

### Action Buttons
- **Clear All**: Deselect all cameras
- **Select Visible**: Select all currently visible (filtered) cameras

### Legend

**Camera Body Colors (Direction):**
- **Green**: Front view
- **Light Green**: Front quarter views
- **Yellow**: Side views (left/right)
- **Orange**: Back quarter views
- **Red**: Back view

**Shot Size Layers (Distance from subject):**
- **Inner ring**: Close-up shots
- **Middle ring**: Medium shots
- **Outer ring**: Wide shots

**Height Indicator Ring (on top of camera):**
- **Red**: Low-angle
- **Blue**: Eye-level
- **Purple**: Elevated
- **Teal**: High-angle

## File Structure

```
ComfyUI_CameraAngleSelector/
├── __init__.py                      # Node registration
├── camera_angle_selector.py         # Main Python node class
├── screenshot.png                   # Screenshot for README
├── web/
│   └── js/
│       └── camera_angle_extension.js  # Three.js ComfyUI extension
└── README.md                        # This file
```

## Technical Details

### Python Node
- Uses `OUTPUT_IS_LIST = (True,)` to enable list output
- Returns `("STRING",)` as `RETURN_TYPES`
- Handles JSON input from the frontend interface

### Frontend
- Built with Three.js for 3D rendering
- Uses raycasting for click detection on 3D objects
- Implements drag-to-rotate camera controls
- PostMessage API for ComfyUI integration

## Troubleshooting

### Node not appearing in ComfyUI
- Ensure the folder is in `ComfyUI/custom_nodes/`
- Restart ComfyUI after installation
- Check for errors in the ComfyUI console

### 3D interface not loading
- Check browser console for JavaScript errors
- Ensure Three.js CDN is accessible
- Try refreshing the page

### Selections not persisting
- Make sure you're clicking directly on camera icons
- Check that the node is properly connected in the workflow

## License

This project is provided as-is for use with ComfyUI.

## Credits

Built for ComfyUI to provide an intuitive 3D interface for camera angle selection in AI image generation workflows.
Thank for the amazing lora [[Qwen-Image-Edit-2511](https://huggingface.co/fal/Qwen-Image-Edit-2511-Multiple-Angles-LoRA)] to the FAL.AI team
