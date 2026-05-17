# Create touchOSC Template in Editor (Step-by-Step)

**Time required:** 10 minutes  
**Difficulty:** Easy  
**No file format issues** - You're creating visually!

---

## 1. Download & Open touchOSC Editor

Go to: https://hexler.net/products/touchosc

Download **touchOSC Editor** (free, Mac/Windows/Linux)

Once installed, open it.

---

## 2. Create a New Project

In touchOSC Editor:
- **File** → **New**
- You'll see a blank canvas

**Canvas size:** 600 × 800 pixels (default is fine)

---

## 3. Add Pan Fader (Left Side)

### Step 1: Click the Fader Tool

In the toolbar, find the **Fader** icon (looks like a vertical slider)

Click it once.

### Step 2: Draw the Fader

Click and drag to create a vertical fader on the **left side** of your canvas:
- Start position: **x=50, y=100**
- Drag down to **x=150, y=350** (tall, vertical fader)

You should see a fader appear.

### Step 3: Configure the Fader

In the **Properties panel** on the right, set:

```
Name:           pan
Type:           Fader (vertical)
X:              50
Y:              100
Width:          100
Height:         250
Label:          Pan
OSC Address:    /ptz/1/pan
Min Value:      -1.0
Max Value:      1.0
Initial Value:  0.0
Orientation:    Vertical
Color:          Blue (#0088ff)
```

**To set color:** Click the color box → Enter `#0088ff` → OK

---

## 4. Add Tilt Fader (Middle)

### Step 1: Click Fader Tool Again

Click the fader icon in toolbar.

### Step 2: Draw Another Fader

Create a fader in the **middle** of the canvas:
- Start: **x=200, y=100**
- Drag to: **x=300, y=350**

### Step 3: Configure

```
Name:           tilt
Label:          Tilt
OSC Address:    /ptz/1/tilt
Min Value:      -1.0
Max Value:      1.0
Color:          Green (#00dd00)
```

---

## 5. Add Zoom Fader (Right)

### Step 1: Click Fader Tool

Click fader icon.

### Step 2: Draw Fader on Right

- Start: **x=350, y=100**
- Drag to: **x=450, y=350**

### Step 3: Configure

```
Name:           zoom
Label:          Zoom
OSC Address:    /ptz/1/zoom
Min Value:      -1.0
Max Value:      1.0
Color:          Orange (#ffaa00)
```

---

## 6. Add Camera Selector Buttons

### Step 1: Click Toggle Button Tool

In toolbar, find **Toggle** button (looks like a square button).

Click it.

### Step 2: Create Camera 1 Button

Click and drag below the faders:
- Start: **x=50, y=400**
- Drag to: **x=200, y=460**

### Step 3: Configure Camera 1

```
Name:           camera_1
Label:          Camera 1
OSC Address:    /ptz/1/select
Value:          1 (checked)
Color:          Blue (#0088ff)
```

### Step 4: Create Camera 2 Button

Click Toggle tool again.
- Start: **x=225, y=400**
- Drag to: **x=375, y=460**

Configure:
```
Label:          Camera 2
OSC Address:    /ptz/2/select
Value:          0 (unchecked)
```

### Step 5: Create Camera 3 Button

Click Toggle tool again.
- Start: **x=400, y=400**
- Drag to: **x=550, y=460**

Configure:
```
Label:          Camera 3
OSC Address:    /ptz/3/select
Value:          0 (unchecked)
```

---

## 7. Add STOP Button (Big Red Button)

### Step 1: Click Toggle Button Tool

Click it.

### Step 2: Draw Large Button

Create a large button below cameras:
- Start: **x=100, y=500**
- Drag to: **x=500, y=580**

### Step 3: Configure

```
Name:           stop
Label:          ⏹ STOP
OSC Address:    /ptz/1/stop
Value:          0
Color:          Red (#dd0000)
```

---

## 8. Configure Network Settings

### Step 1: Open Properties

- **File** → **Properties** (or use gear icon)

### Step 2: Network Tab

Click the **Network** tab.

### Step 3: Set Network Parameters

```
OSC Server IP:    192.168.1.100  ← CHANGE THIS to your PTZ computer IP
OSC Outgoing Port: 9000          ← Match your PTZ app OSC port
```

**Where to find your IP:**
- **Windows:** Open Command Prompt, type `ipconfig`, look for IPv4 address
- **Mac:** System Preferences → Network → Copy IP address
- **Linux:** Terminal, type `ip addr`, look for inet address

### Step 4: Save

Click **OK** or **Save**.

---

## 9. Test in Editor

### Step 1: Drag a Fader

In your template, click and drag the **Pan fader** up/down.

### Step 2: Check OSC Output

At the bottom of the editor, you should see:
```
OSC: /ptz/1/pan = 0.50
```

This confirms the fader is sending OSC messages. ✅

### Step 3: Try Other Controls

Drag Tilt and Zoom to verify they show:
```
OSC: /ptz/1/tilt = ...
OSC: /ptz/1/zoom = ...
```

---

## 10. Save Your Template

- **File** → **Save**
- Name it: `ptz-template`
- Location: Anywhere convenient

File will be saved as `.tosc` (touchOSC v2 binary format).

---

## 11. Transfer to iPad

### Option A: AirDrop (Easiest)

1. On Mac with the `.tosc` file saved:
   - Find file in Finder
   - Right-click → **Send via AirDrop**
   - Select your iPad

2. On iPad:
   - When you see the AirDrop notification, tap **Accept**
   - File downloads to iPad

### Option B: Cloud Storage

1. Move `.tosc` file to cloud storage (Google Drive, iCloud, Dropbox)
2. On iPad:
   - Open app (Google Drive, etc.)
   - Download file
   - Open in touchOSC

### Option C: Email

1. Email the `.tosc` file to yourself
2. On iPad, open email
3. Tap file → **Open in touchOSC**

---

## 12. Import into touchOSC App on iPad

1. **Open touchOSC app** on iPad
2. Go to **Library**
3. Look for your imported file (name you saved)
4. Tap the template name
5. It loads into the app

---

## 13. Configure iPad Network Settings

1. In touchOSC app on iPad:
   - Tap **gear icon** (settings)
   - **Network settings**
   
2. Set:
   ```
   Host:        192.168.1.100  ← Your PTZ computer IP
   Send OSC to: Port 9000       ← Match PTZ app OSC port
   ```

3. **Save/Done**

---

## 14. Test with PTZ App

1. Make sure **PTZ Preset Control** is running on your computer
2. Make sure **OSC Listener is enabled** in PTZ app:
   - Settings → Joystick Control → OSC Controller → Enable
3. On iPad, drag the **Pan fader**
4. Watch your connected camera move! 🎥

If it doesn't move:
- Check **PTZ app diagnostic panel** (Settings → Show OSC Diagnostic Panel)
- Should see messages like: `/ptz/1/pan = 0.50`
- If no messages, check IP and port settings

---

## 15. Customize (Optional)

### Change Colors

In Editor:
1. Click any control
2. In Properties, find **Color**
3. Click the color box
4. Enter hex code:
   - Blue: `#0088ff`
   - Green: `#00dd00`
   - Orange: `#ffaa00`
   - Red: `#dd0000`

### Change Labels

1. Click any control
2. In Properties, change **Label** text
3. Drag the label around if needed

### Resize Controls

1. Click and drag the edges of any control
2. Resize as needed

### Save Changes

- **File** → **Save**
- The `.tosc` file updates
- You can re-transfer to iPad if needed

---

## Troubleshooting

### "I don't see OSC output at bottom"

- Make sure network IP and port are set in Properties
- Try dragging a fader again
- Look carefully at the bottom status bar

### "Button won't toggle"

- Click the button in the editor
- In Properties, find "Value" and toggle it
- Make sure it's a **Toggle** button, not a regular button

### "Colors don't match what I selected"

- Click the control
- Click the color box again
- Make sure you're entering hex codes (starting with #)

### "Faders too sensitive on iPad"

- No issue with the template - adjust in PTZ app:
  - Settings → OSC Controller → Sensitivity sliders
  - Increase/decrease sensitivity until comfortable

---

## You're Done! 🎉

You now have a fully functional touchOSC template for PTZ control:

✅ Pan fader (left)  
✅ Tilt fader (middle)  
✅ Zoom fader (right)  
✅ Camera selector buttons  
✅ Stop button  
✅ Network configured  
✅ Imported on iPad  
✅ Ready to use!

---

## Next Steps

1. Test basic pan/tilt/zoom movement
2. Try switching cameras with buttons
3. Use Stop button in emergency
4. Adjust sensitivity in PTZ app if needed
5. Add more cameras or customize layout if desired

For detailed info, see:
- **TOUCHOSC_SETUP.md** - Complete setup guide
- **TOUCHOSC_TEMPLATE_REFERENCE.md** - Advanced customization

Enjoy your remote PTZ control! 🚀
