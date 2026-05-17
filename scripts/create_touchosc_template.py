#!/usr/bin/env python3
"""
Generate a touchOSC template reference (JSON) for PTZ control.

This script creates a JSON reference template that can be imported into touchOSC Editor.
"""

import json

def create_touchosc_template():
    """Create a minimal touchOSC template in JSON format (can be imported)."""

    template = {
        "version": 2,
        "name": "PTZ Camera Controller",
        "width": 600,
        "height": 800,
        "controls": [
            # Pan Fader
            {
                "type": "fader",
                "id": "fader_pan",
                "x": 50,
                "y": 100,
                "width": 100,
                "height": 250,
                "label": "Pan",
                "address": "/ptz/1/pan",
                "min": -1.0,
                "max": 1.0,
                "value": 0.0,
                "orientation": "vertical",
                "color": {"r": 0, "g": 136, "b": 255}  # Blue
            },
            # Tilt Fader
            {
                "type": "fader",
                "id": "fader_tilt",
                "x": 200,
                "y": 100,
                "width": 100,
                "height": 250,
                "label": "Tilt",
                "address": "/ptz/1/tilt",
                "min": -1.0,
                "max": 1.0,
                "value": 0.0,
                "orientation": "vertical",
                "color": {"r": 0, "g": 221, "b": 0}  # Green
            },
            # Zoom Fader
            {
                "type": "fader",
                "id": "fader_zoom",
                "x": 350,
                "y": 100,
                "width": 100,
                "height": 250,
                "label": "Zoom",
                "address": "/ptz/1/zoom",
                "min": -1.0,
                "max": 1.0,
                "value": 0.0,
                "orientation": "vertical",
                "color": {"r": 255, "g": 170, "b": 0}  # Orange
            },
            # Camera 1 Button
            {
                "type": "toggle",
                "id": "button_cam1",
                "x": 50,
                "y": 400,
                "width": 150,
                "height": 60,
                "label": "Camera 1",
                "address": "/ptz/1/select",
                "value": 1,
                "color": {"r": 0, "g": 136, "b": 255}  # Blue
            },
            # Camera 2 Button
            {
                "type": "toggle",
                "id": "button_cam2",
                "x": 225,
                "y": 400,
                "width": 150,
                "height": 60,
                "label": "Camera 2",
                "address": "/ptz/2/select",
                "value": 0,
                "color": {"r": 0, "g": 136, "b": 255}
            },
            # Camera 3 Button
            {
                "type": "toggle",
                "id": "button_cam3",
                "x": 400,
                "y": 400,
                "width": 150,
                "height": 60,
                "label": "Camera 3",
                "address": "/ptz/3/select",
                "value": 0,
                "color": {"r": 0, "g": 136, "b": 255}
            },
            # Stop Button
            {
                "type": "toggle",
                "id": "button_stop",
                "x": 150,
                "y": 500,
                "width": 300,
                "height": 80,
                "label": "⏹ STOP",
                "address": "/ptz/1/stop",
                "value": 0,
                "color": {"r": 221, "g": 0, "b": 0}  # Red
            }
        ],
        "network": {
            "osc_ip": "192.168.1.100",
            "osc_port": 9000
        }
    }

    return template

if __name__ == "__main__":
    template = create_touchosc_template()

    # Export as JSON (can be imported into touchOSC Editor)
    with open("touchosc-ptz-template.json", "w") as f:
        json.dump(template, f, indent=2)

    print("✅ Template created: touchosc-ptz-template.json")
    print("\nHow to use:")
    print("1. In touchOSC Editor: File → Import")
    print("2. Select touchosc-ptz-template.json")
    print("3. Configure network IP in Properties")
    print("4. Export as .tosc if desired")
