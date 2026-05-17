# touchOSC PTZ Template - Quick Start

## Template File

**File:** `touchosc-ptz-template.json`

This is a pre-configured touchOSC template reference (JSON format) ready to use for PTZ camera control. You can import this into touchOSC Editor or manually create the template using the step-by-step instructions in `CREATE_TOUCHOSC_TEMPLATE.md`.

### What's Included

- **Pan Fader**: Vertical slider, ← Left to Right →
- **Tilt Fader**: Vertical slider, ↓ Down to Up ↑
- **Zoom Fader**: Vertical slider, 🔍 Out to In 🔍
- **Camera Selector**: Toggle buttons for Camera 1, 2, 3
- **Stop Button**: Red emergency stop button
- **Status Display**: Shows server connection info

### Template Layout

```
┌─────────────────────────────────────┐
│ PTZ Camera Control                  │
│ Server: 192.168.1.100:9000         │
├──────────┬──────────┬──────────────┤
│   Pan    │  Tilt   │    Zoom      │
│   [||||] │ [||||]  │   [||||]     │
│          │         │              │
│ ←Left →  │ ↓Down↑  │ 🔍Out In🔍   │
├──────────┴──────────┴──────────────┤
│  [Camera 1] [Camera 2] [Camera 3]  │
│      [⏹ STOP]    ℹ Double-tap...  │
└────────────────────────────────────┘
```

---

## How to Use (touchOSC v1.x)

### Step 1: Open in touchOSC Editor

1. Download **touchOSC Editor** (macOS, Windows, Linux)
   - https://hexler.net/products/touchosc

2. Open the template:
   ```
   File → Open
   Select: touchosc-ptz-template.toml
   ```

3. Review the layout (you should see Pan, Tilt, Zoom faders + camera buttons)

### Step 2: Configure Network Settings

1. **File → Properties**
2. **Network Tab:**
   - **OSC Server IP:** Enter IP of your PTZ computer
     - Example: `192.168.1.100` or `172.16.0.50`
     - NOT `localhost` or `127.0.0.1`
   - **Outgoing Port:** `9000` (match PTZ app setting)
   - Click **Save**

### Step 3: Test in Editor

1. **File → Open in Editor Window** (if not already visible)
2. Try dragging the Pan fader left/right
3. The OSC message should display at bottom:
   ```
   /ptz/1/pan = 0.50
   ```

### Step 4: Export & Transfer to Mobile

#### Option A: Export as .tosc (v2 format)

1. **File → Export As**
2. Choose format: **OSC Template (.tosc)**
3. Save as `touchosc-ptz-template.tosc`
4. Transfer file to iPad/iPhone via:
   - AirDrop
   - Cloud storage (iCloud Drive, Google Drive, etc.)
   - Email attachment
   - USB file sharing

#### Option B: Use v1 Format Directly

1. **File → Save As**
2. Save as `.toml` (keeps v1 format)
3. Transfer same way as Option A

### Step 5: Import into touchOSC App

**On iOS:**
1. Download **touchOSC** app from App Store
2. Open Files app → Find your template file
3. Tap the `.tosc` or `.toml` file
4. When prompted: **Open in touchOSC**
5. Confirm import
6. Template appears in your library

**On Android:**
1. Download **touchOSC** from Play Store
2. Transfer file via USB or cloud storage
3. In touchOSC: **Library → Import**
4. Select your template file
5. Template appears in your library

### Step 6: Connect to PTZ App

1. Open **touchOSC app** on iPad/iPhone
2. **Settings → Network:**
   - **Host:** IP address of PTZ computer (e.g., `192.168.1.100`)
   - **Send OSC to:** Port matching PTZ app (default `9000`)
   - Save

3. Open your imported template

4. **Try dragging faders:**
   - You should see camera movement
   - Check PTZ app diagnostic panel for incoming messages

---

## How to Use (touchOSC v2.x)

### Importing as v2 Template

1. **Editor:** Open `touchosc-ptz-template.toml`
2. **File → Export As → OSC Template (.tosc)**
3. Transfer `.tosc` file to iOS device
4. Open in touchOSC v2 app (File → Import)
5. Configure network settings (Host, Port)
6. Use same way as v1

### Native v2 Advantages

- Binary format (slightly smaller file)
- Better performance on older devices
- Same functionality as v1

---

## Customization Examples

### Change Camera Names

Edit the template in a text editor:

```toml
[button_camera_1]
text = "Front Stage"    # Changed from "Camera 1"

[button_camera_2]
text = "Side Angle"     # Changed from "Camera 2"

[button_camera_3]
text = "Wide"           # Changed from "Camera 3"
```

Save and re-import.

### Change Control Colors

Colors use hex format (RRGGBB):

```toml
[fader_pan]
foreground_color = "ff00ff"  # Change to magenta (was 0088ff = blue)

[button_stop]
background_color = "ff6600"  # Change to orange (was dd0000 = red)
```

### Add More Cameras

Uncomment the "ADVANCED MULTI-CAMERA SETUP" section in the template and add:

```toml
[button_camera_4]
type = "toggle"
x = 0.10
y = 0.95
w = 0.22
h = 0.08
address = "/ptz/4/select"
text = "Camera 4"
```

### Create Separate Pages (Advanced)

In touchOSC Editor:
1. **File → New Page**
2. Add different camera controls to each page
3. Users swipe between pages to access different cameras

---

## Troubleshooting Template Issues

### "Template won't open in Editor"

- Make sure you have **touchOSC Editor** installed (not just the app)
- The `.toml` file might be corrupted
- Try re-downloading from the repository

### "OSC messages show wrong address"

- Edit template in text editor
- Search for `address = "/ptz/..."`
- Verify camera number and control name match
- Example: `/ptz/1/pan` not `/ptz/01/pan`

### "Faders too sensitive or not sensitive enough"

- Adjust in PTZ app settings (**Settings → OSC Controller → Sensitivity**)
- Or edit in Editor and re-export
- Sensitivity values: 0.1x (very slow) to 2.0x (very fast)

### "Colors look wrong in app"

- Verify hex color codes in template
- Some devices have different color profiles
- Bright colors (like FFFFFF = white) may be hard to see on some screens

---

## Template Configuration Quick Reference

### OSC Message Format

All controls send normalized values (-1.0 to 1.0):

```
/ptz/1/pan = -0.5     (50% left)
/ptz/1/pan = 0.5      (50% right)
/ptz/1/tilt = 0.75    (75% up)
/ptz/1/zoom = 1.0     (100% zoom in)
/ptz/1/stop = 0       (stop all motion)
```

### Default Server Settings

```
Host:      192.168.1.100 (CHANGE THIS to your PTZ computer IP)
Port:      9000 (match OSC port in PTZ app)
Protocol:  OSC over UDP
```

### Control Mapping

| Control | Address | Range | Direction |
|---------|---------|-------|-----------|
| Pan | `/ptz/1/pan` | -1 to 1 | Left ↔ Right |
| Tilt | `/ptz/1/tilt` | -1 to 1 | Down ↔ Up |
| Zoom | `/ptz/1/zoom` | -1 to 1 | Out ↔ In |
| Stop | `/ptz/1/stop` | 0 | Emergency stop |

Replace `1` with `2` or `3` for other cameras.

---

## Next Steps

1. ✅ Download/create template
2. ✅ Configure touchOSC Editor
3. ✅ Export to `.tosc` format
4. ✅ Transfer to iPad/iPhone
5. ✅ Import into touchOSC app
6. ✅ Configure network (Host/Port)
7. ✅ Test pan/tilt/zoom movement
8. ✅ Check diagnostic panel for messages
9. 🎉 Use in production!

---

## Support

If you encounter issues:

1. **Check diagnostic panel** in PTZ app (Settings → Show OSC Diagnostic Panel)
2. **Verify network connectivity** (both devices on same WiFi?)
3. **Confirm IP address** (not 127.0.0.1 or localhost)
4. **Test with curl** (if you're technical):
   ```bash
   # Send test OSC message
   python3 -c "import socket; s = socket.socket(); s.sendto(b'/ptz/1/pan\x00,f\x00\x003f\x80\x00\x00', ('192.168.1.100', 9000))"
   ```

For detailed troubleshooting, see **TOUCHOSC_SETUP.md**.
