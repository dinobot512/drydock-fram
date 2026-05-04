#!/usr/bin/env python3
"""
Command Node - runs on your laptop
Acts as the "ground crew" node on the network.
Also bridges MQTT -> WebSocket so the dashboard can subscribe.
"""

import json
import math
import random
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

NODE_ID     = "GROUND-01"
BROKER_HOST = "localhost"
BROKER_PORT = 1883

BASE_LAT =  36.172
BASE_LON = -86.769

def generate_telemetry(t):
    # Ground crew moves slowly along a patrol line
    lat = BASE_LAT + (t * 0.000005)
    lon = BASE_LON + math.sin(t * 0.1) * 0.001
    return {
        "node_id":    NODE_ID,
        "node_type":  "GROUND",
        "timestamp":  datetime.now(timezone.utc).isoformat(),
        "lat":        round(lat, 6),
        "lon":        round(lon, 6),
        "alt_m":      280,
        "status":     "active",
        "crew_size":  4,
        "water_pct":  max(0, round(100 - (t * 0.03) % 100, 1)),
    }

connected = False

def on_connect(client, userdata, flags, rc, props=None):
    global connected
    connected = (rc == 0)
    if connected:
        print(f"[MQTT]  Ground node connected to broker")
        client.publish(
            f"wildfire/nodes/{NODE_ID}/status",
            json.dumps({"node_id": NODE_ID, "status": "online",
                        "timestamp": datetime.now(timezone.utc).isoformat()}),
            retain=True
        )

def on_disconnect(client, userdata, rc, props=None, reason=None):
    global connected
    connected = False
    print(f"[MQTT]  Ground node disconnected")

def main():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=NODE_ID)
    client.on_connect    = on_connect
    client.on_disconnect = on_disconnect
    client.will_set(
        f"wildfire/nodes/{NODE_ID}/status",
        json.dumps({"node_id": NODE_ID, "status": "offline",
                    "timestamp": datetime.now(timezone.utc).isoformat()}),
        retain=True
    )

    print(f"[INIT]  Ground Command Node {NODE_ID} starting...")
    client.connect(BROKER_HOST, BROKER_PORT, keepalive=10)
    client.loop_start()

    t = 0
    try:
        while True:
            if connected:
                telemetry = generate_telemetry(t)
                client.publish(
                    f"wildfire/nodes/{NODE_ID}/telemetry",
                    json.dumps(telemetry), qos=1
                )
                print(f"[TX]    Ground crew at lat={telemetry['lat']} lon={telemetry['lon']} "
                      f"water={telemetry['water_pct']}%")
            t += 1
            time.sleep(2)
    except KeyboardInterrupt:
        print("\n[STOP]  Ground node shutting down.")
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    main()