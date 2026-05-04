# 8BitDo Zero 2 Gamepad Setup Guide

## Quick Summary

The main issue is that **8BitDo controllers have multiple modes** that change button mappings. The app expects **DirectInput/D-Input mode** with d-pad mapped to buttons 12-15.

## Step 1: Identify Your Gamepad Mode

### Open Debug Info
1. Go to Settings (⚙️ icon)
2. Scroll to **"Joystick Control"**
3. **Check "Show Debug Info"**
4. Look at the bottom section - you should see something like:

```
Gamepad: 8BitDo Zero 2 (16 btns, 6 axes)
```

### Check Button Count

| Button Count | Mode | Status |
|---|---|---|
| **16 buttons** | ✅ **DirectInput (D-Input)** | **Correct - Use "8BitDo Zero 2" profile** |
| 10 buttons | ❌ XInput | Wrong - Switch controller mode |
| 17 buttons | ❌ Switch mode | Wrong - Switch controller mode |

## Step 2: Switch to Correct Mode (if needed)

### 8BitDo Zero 2 Mode Switch

The 8BitDo Zero 2 uses **button combinations** to switch modes:

1. **Power on** the controller
2. **Hold X + Start** for ~3 seconds until LED flashes
3. Check the LED color pattern:
   - 🔴 Red flash = DirectInput (D-Input) ✅
   - 🔵 Blue flash = XInput
   - 🟢 Green flash = Switch mode

### Details for Different Modes

**DirectInput (D-Input)** - What you want:
- LED: Solid blue when connected
- Buttons: 16 total
- D-Pad: Buttons 12, 13, 14, 15
- Best for: This app

**XInput** - Don't use for d-pad:
- LED: Different color pattern
- Buttons: 10 total  
- D-Pad: Uses HAT switch (not supported by this app)

## Step 3: Verify D-Pad Buttons

Once in DirectInput mode:

1. Open Settings and enable **Show Debug Info**
2. Press d-pad buttons one at a time:
   - Press **Up** → should show `[12]`
   - Press **Right** → should show `[15]`
   - Press **Down** → should show `[13]`
   - Press **Left** → should show `[14]`

3. You should see in the "Pressed buttons" line: `[12]`, `[13]`, `[14]`, or `[15]`

**If you see different numbers or nothing**, the gamepad is in the wrong mode.

## Step 4: Configure in App

1. **Enable Joystick**: Check the checkbox
2. **Device Profile**: Select **"8BitDo Zero 2 (D-Pad)"**
3. **Sensitivity**: Adjust as needed (start with 1.0x for pan/tilt)
4. The debug panel should show a suggestion if mode is wrong

## Understanding Debug Output

When enabled, you'll see:

```
Pan: 1.000    Tilt: 0.000  [● glowing indicator]
Zoom: 0.500

Gamepad: 8BitDo Zero 2 (16 btns, 6 axes)
Pressed buttons: [15]
```

### What Each Line Means

- **Pan/Tilt/Zoom**: Current movement values (0 = stopped, 1 = full speed)
- **Indicator glow**: Shows when input is being registered
- **Gamepad line**: Device name and capabilities. If you see a warning like `"Try mode: 8bitdo-zero2"`, follow that suggestion
- **Pressed buttons**: Which physical buttons are being pressed (should be 12, 13, 14, or 15 for d-pad)

## Troubleshooting

### D-Pad Not Responding

**Symptoms**: Pressing d-pad does nothing

**Check**:
1. Is "Enable Joystick" checked?
2. Is debug "Pressed buttons" showing numbers when you press d-pad?
   - **No** → Wrong gamepad mode. Switch to DirectInput.
   - **Yes** → Check if buttons are 12-15. If not, check Profile setting.

### Camera Moving But Not Stopping

**Symptoms**: Camera keeps moving after releasing d-pad

**Check**:
1. Is the indicator still glowing after releasing?
   - **Yes** → D-pad button stuck or not releasing properly
   - **No** → VISCA stop command was sent. This might be a network delay.

2. Check browser console (`F12` → Console):
   - Should see `[GAMEPAD] Sending STOP command` when you release buttons
   - Should see button indices `[12]`, `[13]`, `[14]`, `[15]` for d-pad

### Inconsistent Response

**Symptoms**: Sometimes works, sometimes doesn't

**Likely cause**: Gamepad switching between modes
- Check gamepad LED color - should be solid when connected
- Try the mode switch combination again (X + Start)
- Look at debug output - does "button count" change?

### Visual Delay with Remote View

Since you're watching remotely:
- The **indicator glow** confirms your input was sent immediately
- Camera movement delay is from network lag, not the app
- VISCA commands are being sent correctly if you see the indicator

## Quick Reference

```
8BitDo Zero 2 Modes:
┌─────────────────────────────────────────────────┐
│ Hold X + Start for 3 seconds                    │
│ 🔴 Red flash   = DirectInput (D-Input) ✅       │
│ 🔵 Blue flash  = XInput ❌                      │
│ 🟢 Green flash = Switch ❌                      │
└─────────────────────────────────────────────────┘

DirectInput Button Mapping:
Up    = Button 12
Right = Button 15  
Down  = Button 13
Left  = Button 14
```

## Still Having Issues?

1. **Open browser console** (`F12`)
2. **Enable debug info** in settings
3. **Press d-pad** and watch both console and debug panel
4. Look for:
   - Gamepad connection message
   - D-pad button presses showing indices
   - STOP commands being sent
   - Any error messages

The console will help identify exactly where the breakdown is happening.
