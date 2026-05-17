# touchOSC Template Reference

## Visual Layout

```
╔════════════════════════════════════════════════════════════╗
║                  PTZ Camera Control                        ║
║            Server: 192.168.1.100:9000                     ║
╠═════════════════╤═════════════════╤═════════════════════╤═╣
║                 │                 │                     │ ║
║      PAN        │     TILT        │     ZOOM            │ ║
║                 │                 │                     │ ║
║    ┌─────────┐  │   ┌─────────┐   │   ┌─────────┐     │ ║
║    │         │  │   │         │   │   │         │     │ ║
║    │         │  │   │         │   │   │         │     │ ║
║    │  [|||]  │  │   │  [|||]  │   │   │  [|||]  │     │ ║
║    │         │  │   │         │   │   │         │     │ ║
║    │         │  │   │         │   │   │         │     │ ║
║    └─────────┘  │   └─────────┘   │   └─────────┘     │ ║
║  ← Left → Right │ ↓ Down ↑ Up    │ 🔍 Out ← → In 🔍 │ ║
║                 │                 │                     │ ║
╠════════════════════════════════════════════════════════════╣
║   [Camera 1]    [Camera 2]        [Camera 3]               ║
║                                                            ║
║      [⏹ STOP]               ℹ Double-tap faders to reset   ║
╚════════════════════════════════════════════════════════════╝
```

---

## Control Reference

### Pan Fader (Left Column)
- **Type:** Vertical fader
- **Range:** -1.0 (left) to +1.0 (right)
- **OSC Address:** `/ptz/1/pan`
- **Color:** Blue (#0088ff)
- **Behavior:** Spring-back when released (handled by PTZ app)

### Tilt Fader (Middle Column)
- **Type:** Vertical fader
- **Range:** -1.0 (down) to +1.0 (up)
- **OSC Address:** `/ptz/1/tilt`
- **Color:** Green (#00dd00)
- **Behavior:** Spring-back when released

### Zoom Fader (Right Column)
- **Type:** Vertical fader
- **Range:** -1.0 (zoom out) to +1.0 (zoom in)
- **OSC Address:** `/ptz/1/zoom`
- **Color:** Orange (#ffaa00)
- **Behavior:** Spring-back when released

### Camera Selector Buttons
- **Type:** Toggle buttons (one camera selected at a time)
- **Cameras:** 1, 2, 3 (configurable)
- **OSC Addresses:**
  - `/ptz/1/select` (Camera 1)
  - `/ptz/2/select` (Camera 2)
  - `/ptz/3/select` (Camera 3)
- **Visual Feedback:**
  - Active camera: Bright blue with dark text
  - Inactive cameras: Dark gray with light text
- **Behavior:**
  - Only one camera can be "selected" at a time
  - Toggles between on (1) and off (0)

### Stop Button
- **Type:** Toggle button (momentary)
- **OSC Address:** `/ptz/1/stop`
- **Color:** Red (#dd0000)
- **Text:** ⏹ STOP (Unicode stop symbol)
- **Behavior:** Sends value when pressed, resets when released
- **Purpose:** Emergency stop - halts all pan/tilt/zoom motion

---

## OSC Message Examples

### Pan (Moving Left)
```
Address: /ptz/1/pan
Value:   -0.75
Meaning: Move camera 1 pan left at 75% speed
```

### Pan (Neutral/Stopped)
```
Address: /ptz/1/pan
Value:   0.0
Meaning: Stop pan motion (no horizontal movement)
```

### Tilt (Moving Up)
```
Address: /ptz/1/tilt
Value:   0.50
Meaning: Move camera 1 tilt up at 50% speed
```

### Zoom (Maximum Zoom In)
```
Address: /ptz/1/zoom
Value:   1.0
Meaning: Zoom in at maximum speed
```

### Zoom (Zoom Out)
```
Address: /ptz/1/zoom
Value:   -0.5
Meaning: Zoom out at 50% speed
```

### Stop All Motion
```
Address: /ptz/1/stop
Value:   0
Meaning: Stop all pan, tilt, zoom motion on camera 1
```

---

## Multi-Camera Usage

The template can control multiple cameras by changing the camera number in the OSC address:

### Single Camera (Default)
```
/ptz/1/pan   ← Controls Camera 1 pan
/ptz/1/tilt  ← Controls Camera 1 tilt
/ptz/1/zoom  ← Controls Camera 1 zoom
```

### Switch to Camera 2
1. **Option A:** Click [Camera 2] button (recommended)
   - Sets focus to camera 2
   - Pan/tilt/zoom automatically use `/ptz/2/...`

2. **Option B:** Manually in OSC Editor
   - Edit fader addresses to use `/ptz/2/pan` etc.
   - Not recommended (confusing)

### Support for 4+ Cameras
1. Open template in touchOSC Editor
2. Duplicate camera button section
3. Adjust OSC addresses for new cameras:
   ```
   /ptz/4/select
   /ptz/4/pan
   /ptz/4/tilt
   /ptz/4/zoom
   ```
4. Re-export and import into app

---

## Color Scheme

The template uses a dark theme optimized for live use:

| Element | Color | Hex Code | Purpose |
|---------|-------|----------|---------|
| Background | Dark gray | #1a1a1a | Low glare, easy on eyes |
| Pan Fader | Blue | #0088ff | Standard pan color |
| Tilt Fader | Green | #00dd00 | Standard tilt color |
| Zoom Fader | Orange | #ffaa00 | Warm, distinct from pan/tilt |
| Stop Button | Red | #dd0000 | Danger/emergency color |
| Text | White | #ffffff | High contrast, readable |
| Labels | Gray | #888888 | Secondary information |
| Active Button | Blue | #0088ff | Camera selection |

**Dark theme rationale:**
- Reduces eye strain in dark theater/production environments
- Provides clear visual feedback with bright colors
- High contrast for rapid, accurate touch input

---

## Editing the Template

The template is a plain text `.toml` file. You can edit it with any text editor:

### Change Camera Names
```toml
# Before:
[button_camera_1]
text = "Camera 1"

# After:
[button_camera_1]
text = "Front Stage"
```

### Change Control Colors
```toml
# Before:
[fader_pan]
foreground_color = "0088ff"

# After:
[fader_pan]
foreground_color = "ff0088"    # Magenta instead of blue
```

### Add New Camera Button
```toml
[button_camera_4]
type = "toggle"
x = 0.10
y = 0.95
w = 0.22
h = 0.08
address = "/ptz/4/select"
text = "Camera 4"
text_color = "000000"
background_color = "0088ff"
background_color_off = "333333"
text_color_off = "ffffff"
value = 0
local_feedback = 1
```

### Change Fader Size/Position
```toml
# x, y, w, h represent: x-position, y-position, width, height
# Values are 0-1.0 (percentage of screen)

[fader_pan]
x = 0.10      # 10% from left
y = 0.28      # 28% from top
w = 0.18      # 18% width
h = 0.35      # 35% height (tall for vertical fader)
```

### Change OSC Port
```toml
# At top of file:
osc_outgoing_port = 9001    # Changed from 9000
```

---

## Keyboard Shortcuts (Editor)

When editing in touchOSC Editor:

| Action | Shortcut |
|--------|----------|
| Save | Ctrl+S (Win) / Cmd+S (Mac) |
| Open | Ctrl+O / Cmd+O |
| Export As | Ctrl+E / Cmd+E |
| Undo | Ctrl+Z / Cmd+Z |
| Redo | Ctrl+Y / Cmd+Y |
| Select All | Ctrl+A / Cmd+A |
| Copy | Ctrl+C / Cmd+C |
| Paste | Ctrl+V / Cmd+V |

---

## Common Customizations

### Create iPad-Landscape Variant

Position controls to use full horizontal space:

```toml
# Wider faders for landscape orientation
[fader_pan]
x = 0.05
w = 0.25       # Wider

[fader_tilt]
x = 0.35
w = 0.25

[fader_zoom]
x = 0.65
w = 0.25

# Buttons at bottom
[button_camera_1]
x = 0.10
y = 0.85

[button_camera_2]
x = 0.40
y = 0.85

[button_camera_3]
x = 0.70
y = 0.85
```

### Add XY Pad for Simultaneous Pan/Tilt

```toml
[xy_pad]
type = "xy"
x = 0.10
y = 0.20
w = 0.80
h = 0.60
address_x = "/ptz/1/pan"
address_y = "/ptz/1/tilt"
min = -1.0
max = 1.0
```

### Add Custom Labels for Each Camera

```toml
[label_camera_1_name]
type = "label"
text = "Pulpit"         # Instead of generic "Camera 1"

[label_camera_2_name]
type = "label"
text = "Left Stage"

[label_camera_3_name]
type = "label"
text = "Congregation"
```

---

## Performance Tips

1. **Use vertical faders** - Easier to control with one finger than XY pads
2. **Large touch targets** - Minimum 30px x 30px (template uses 44-60px)
3. **Clear labels** - Operators must recognize controls instantly
4. **Dark background** - Reduces eye strain in production environments
5. **Distinct colors** - Pan (blue), tilt (green), zoom (orange) are easily distinguished
6. **Emergency stop** - Bright red, large, always accessible

---

## Testing Checklist

- [ ] Template opens in touchOSC Editor without errors
- [ ] All faders appear and move smoothly
- [ ] Camera buttons toggle between on/off
- [ ] Stop button is red and clearly visible
- [ ] Network IP entered in settings
- [ ] OSC port matches PTZ app port (default 9000)
- [ ] Faders send correct OSC messages (check with diagnostic panel)
- [ ] Camera buttons send correct `/ptz/N/select` messages
- [ ] Exported `.tosc` file can be imported into app
- [ ] Works on both portrait and landscape orientations
- [ ] Touch is responsive (no lag or delay)

---

## File Format Details

### .toml Format (touchOSC v1)

Plain text format with INI-like syntax:

```toml
[control_name]          # Control identifier (unique)
type = "fader"          # Control type
x = 0.10                # X position (0-1.0)
y = 0.20                # Y position (0-1.0)
w = 0.20                # Width (0-1.0)
h = 0.50                # Height (0-1.0)
address = "/ptz/1/pan"  # OSC address
min = -1.0              # Minimum value
max = 1.0               # Maximum value
value = 0.0             # Initial value
```

### .tosc Format (touchOSC v2)

Binary format (proprietary). Generated by exporting `.toml` in Editor.

**Advantages of .tosc:**
- Smaller file size
- Slightly faster loading
- Better compatibility with v2 features

**Advantages of .toml:**
- Human-readable
- Easy to edit
- Works with v1 directly

---

## Troubleshooting by Control Type

### Fader Issues
- **Not moving:** Check network connection
- **Jumps around:** Network latency (nothing to do)
- **Too sensitive:** Reduce sensitivity in PTZ app Settings
- **Stuck:** Refresh app or reconnect

### Button Issues
- **Won't toggle:** Check local_feedback setting
- **Wrong color:** Verify background_color and background_color_off values
- **Unresponsive:** May be receiving messages but app isn't responding

### Label Issues
- **Text is cut off:** Increase width (w) or reduce font_size
- **Not visible:** Check text_color and background_color contrast

---

## Next: Using the Template

Once you've created/imported the template:

1. Open **TOUCHOSC_SETUP.md** for connection instructions
2. Follow the **Network Configuration** section
3. Test with PTZ app running
4. Use diagnostic panel to verify message delivery
5. Adjust sensitivity in PTZ app if needed
6. Save custom layout if you make changes

---
