# touchOSC PTZ Controller Setup Guide

## Overview

This guide explains how to use touchOSC to control PTZ cameras over the network via OSC (OpenSound Control) protocol. touchOSC lets you create custom virtual joystick layouts on iPad, iPhone, or Android tablets to control pan, tilt, and zoom from a second device.

## What You Need

- **touchOSC app** (v1.x or v2.x - free on iOS, Android, macOS, Windows)
  - Download from: https://hexler.net/products/touchosc
  - Supports iOS 12+ (iPad recommended for comfort)
  
- **PTZ Preset Control app** with OSC enabled
  - Network connection between both devices (same WiFi or routable network)
  - OSC port configured (default: 9000)

- **Network Setup**
  - Both devices must be on the same network
  - Firewall must allow UDP on OSC port
  - Note the IP address of the machine running PTZ Preset Control

## Step 1: Enable OSC in PTZ Preset Control

1. Open the Settings panel (gear icon at bottom right)
2. Go to the **"Joystick Control"** tab
3. Scroll down to **"OSC Controller (touchOSC)"** section
4. Check **"Enable OSC Listener"**
5. Note the **OSC Port** (default: 9000)
6. Adjust sensitivity sliders if desired:
   - Pan Sensitivity: 0.1-2.0x (default: 1.0x)
   - Tilt Sensitivity: 0.1-2.0x (default: 1.0x)
   - Zoom Sensitivity: 0.1-2.0x (default: 1.0x)
7. (Optional) Check **"Show OSC Diagnostic Panel"** to see incoming OSC messages

**Important:** Settings are saved automatically. The OSC listener will start on the configured port.

## Step 2: Create/Download touchOSC Template

### Option A: Use Provided Template (Recommended)

A pre-made touchOSC template is provided in the repository. Look for:
- `touchosc-ptz-template.tosc` (touchOSC v2 binary format)

**To import:**
1. Copy the template file to your iPad/iPhone
2. Open the Files app and locate the `.tosc` file
3. Tap to open → touchOSC will launch and import it
4. Confirm the import
5. The template appears in your touchOSC library

### Option B: Create Your Own Template (Advanced)

If you want to customize the layout:

1. **On macOS/Windows:** Open touchOSC Editor
2. **Create a new blank project**
3. **Add controls:**
   - **Pan Fader** (vertical slider, -1 to 1)
     - OSC: `/ptz/1/pan`
   - **Tilt Fader** (vertical slider, -1 to 1)
     - OSC: `/ptz/1/tilt`
   - **Zoom Fader** (vertical slider, -1 to 1)
     - OSC: `/ptz/1/zoom`
   - **Camera Buttons** (one per camera, 1-indexed)
     - Add custom labels for each camera
     - Optional: use buttons to change active camera
   - **Stop Button** (momentary toggle)
     - OSC: `/ptz/1/stop`

4. **Configure each control's OSC output:**
   - Select control → Properties panel
   - Enable OSC output
   - Set address: `/ptz/{cam_id}/{control}`
   - Example: `/ptz/1/pan` for camera 1 pan

5. **Save** as `.tosc` file (touchOSC v2) or `.toml` (v1)

6. **Transfer to mobile device** via iTunes, file sharing, or cloud storage

## Step 3: Configure touchOSC on Your Device

1. **Install touchOSC** from your device's app store
2. **Open touchOSC**
3. **Import the template** (see Step 2)
4. **Open the template**
5. **Configure OSC settings:**
   - Look for network settings (usually gear icon)
   - **Host/Server IP:** Enter the IP of your PTZ computer
     - Example: `192.168.1.100` or `172.16.0.50`
   - **Outgoing Port:** Set to match PTZ app OSC port (default: 9000)
   - Leave "Incoming Port" as default unless you need reverse feedback
6. **Save settings**

## Step 4: Test the Connection

### Quick Test:
1. Make sure PTZ app has OSC Listener enabled
2. In touchOSC, touch the pan fader and drag left/right
3. Watch the PTZ app or connected camera for movement
4. Test tilt (up/down) and zoom (in/out)

### Debug OSC Messages:
1. **In PTZ app:**
   - Open Settings → Joystick Control
   - Check "Show OSC Diagnostic Panel"
   - Watch for incoming messages as you move faders in touchOSC
   
   Expected messages:
   ```
   /ptz/1/pan = 0.50      (50% pan right)
   /ptz/1/tilt = -0.25    (25% tilt down)
   /ptz/1/zoom = 0.75     (75% zoom in)
   ```

2. **Timestamp tracking:**
   - Diagnostic panel shows time, address, and value
   - Confirms message delivery in real-time

## Troubleshooting

### "No messages in diagnostic panel"

**Problem:** OSC messages are not arriving.

**Solutions:**
1. **Verify network connection:**
   - Both devices on same WiFi?
   - Can you ping the PTZ computer from iPad?
   ```
   iOS: Use Network Analyzer app to test connectivity
   ```

2. **Check port configuration:**
   - PTZ app OSC port = touchOSC "Outgoing Port"?
   - Default both to 9000
   
3. **Verify IP address:**
   - In touchOSC network settings, is the correct server IP entered?
   - Check PTZ app's network settings to confirm listening address
   - Try: `ifconfig` or `ipconfig` on PTZ computer to find IP
   - Not 127.0.0.1 or localhost (those are local only)

4. **Firewall issues:**
   - Is UDP port 9000 open on the PTZ computer?
   - Windows: Check Windows Defender Firewall
   - macOS: System Preferences → Security & Privacy → Firewall
   - Linux: Check `ufw` or `iptables`

### "Camera doesn't move"

**Problem:** Messages arrive but camera doesn't move.

**Solutions:**
1. **Check live mode lock:**
   - If camera is on ATEM program and "Protect Live Camera" is enabled, movement is blocked
   - Check PTZ app fullscreen joystick for red "LIVE - LOCKED" indicator
   - Solution: Switch to different camera or disable live protection

2. **Verify camera IP:**
   - Is the camera configured in PTZ app settings?
   - Does it have a valid IP address?
   - Can it be controlled from the main PTZ app interface?

3. **Check camera index:**
   - OSC uses 1-indexed cameras: `/ptz/1/pan` is Camera 1
   - If you want Camera 2, use: `/ptz/2/pan`
   - Verify camera index matches your setup

4. **Rate limiting:**
   - OSC is limited to 30 messages/second per camera
   - Rapid slider movements are coalesced
   - This is intentional for stability; increase via Settings if needed

### "Movement is slow or unresponsive"

**Solutions:**
1. **Adjust sensitivity in PTZ app:**
   - Settings → Joystick Control → OSC Controller
   - Increase pan/tilt/zoom sensitivity (up to 2.0x)
   - Save settings

2. **Check network latency:**
   - Network lag = delayed response
   - Use local network only (WiFi, not cellular/LTE)
   - Move closer to router if needed

3. **Simplify touchOSC template:**
   - If template has many controls, disable unused ones
   - Reduces message volume

### "Wrong camera is moving"

**Problem:** Moving camera 1 fader controls camera 2 camera.

**Solutions:**
1. **Check active camera in PTZ app:**
   - Look at camera tabs at top
   - Click the correct camera to activate it
   - OR click camera button in touchOSC template to switch

2. **Verify OSC addresses in template:**
   - Pan control should have OSC address: `/ptz/1/pan`
   - Not `/ptz/2/pan` or `/ptz/0/pan`
   - Edit template in touchOSC Editor to fix

## Advanced: Custom Templates

### Pan/Tilt with Joystick Pad

Instead of separate faders, use an XY pad for pan/tilt:

1. In touchOSC Editor, add "XY Pad" control
2. Set X axis (left-right):
   - OSC: `/ptz/1/pan`
   - Range: -1 to 1
3. Set Y axis (up-down):
   - OSC: `/ptz/1/tilt`
   - Range: -1 to 1 (invert if needed)

This provides intuitive 2D control like a real joystick.

### Multi-Camera Layout

Create buttons to switch active camera:

1. Add buttons labeled "CAM 1", "CAM 2", "CAM 3"
2. Each button sends different message (for your custom backend)
3. Or: Create separate pan/tilt/zoom for each camera in same template
   - Camera 1: `/ptz/1/{pan,tilt,zoom}`
   - Camera 2: `/ptz/2/{pan,tilt,zoom}`
   - Camera 3: `/ptz/3/{pan,tilt,zoom}`

### Cut/Preview Buttons (Future)

The backend doesn't yet support ATEM cut via OSC, but can be added:

1. When implemented, buttons would send:
   - `/ptz/1/cut/preview` → set to preview
   - `/ptz/1/cut/program` → cut to program

## Performance Notes

- **Network latency:** Expect 50-200ms round-trip delay depending on network
- **Message rate:** Limited to 30 Hz (30 messages/second per camera) by design
- **Concurrent users:** Multiple touchOSC controllers can run simultaneously
- **Live safety:** Live mode lock is enforced; you cannot accidentally move on-air cameras

## Next Steps

1. **Test on iPad:** Fullscreen joystick is optimized for iPad use
2. **Compare workflows:** Use both fullscreen joystick page and touchOSC to find your preference
3. **Customize template:** Adjust layout and sensitivity to your comfort

## Support

- Check the **OSC Diagnostic Panel** in PTZ app settings
- Review **system logs** if the PTZ app crashes (check `server.py` output)
- File an issue on GitHub with:
  - Exact error or unexpected behavior
  - Network setup (same subnet? firewall rules?)
  - touchOSC version and template you're using
  - OSC diagnostic output (if available)
