
#!/usr/bin/env python3
"""
UAS Edge Node - runs on Raspberry Pi
Publishes position + sensor data to MQTT broker.
When broker is unreachable, queues messages locally.
On reconnect, flushes the queue automatically.
"""

import json
import math
import os
import random
import sqlite3
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

# ── Config ────────────────────────────────────────────────────────────────────
BROKER_HOST = "YOUR_LAPTOP_IP"   # <-- change this to your laptop's IP
BROKER_PORT = 1883
NODE_ID     = "UAS-01"
QUEUE_DB    = "/tmp/uas_queue.db"

# Simulated flight path: circle over a fire area (Nashville coords as placeholder)
BASE_LAT  =  36.174
BASE_LON  = -86.767
RADIUS_KM =  0.5

# ── Local queue (SQLite) ───────────────────────────────────────────────────────
def init_queue():
    conn = sqlite3.connect(QUEUE_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS queue (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            topic     TEXT NOT NULL,
            payload   TEXT NOT NULL,
            queued_at REAL NOT NULL
        )
    """)
    conn.commit()
    return conn

def enqueue(conn, topic, payload):
    conn.execute(
        "INSERT INTO queue (topic, payload, queued_at) VALUES (?, ?, ?)",
        (topic, json.dumps(payload), time.time())
    )
    conn.commit()
    count = conn.execute("SELECT COUNT(*) FROM queue").fetchone()[0]
    print(f"  [QUEUE] Stored locally ({count} messages queued)")

def flush_queue(conn, client):
    rows = conn.execute("SELECT id, topic, payload FROM queue ORDER BY id").fetchall()
    if not rows:
        return
    print(f"  [SYNC]  Flushing {len(rows)} queued messages...")
    for row_id, topic, payload in rows:
        result = client.publish(topic, payload, qos=1)
        result.wait_for_publish(timeout=3)
        conn.execute("DELETE FROM queue WHERE id = ?", (row_id,))
        conn.commit()
        print(f"  [SYNC]  Sent queued message id={row_id}")
    print(f"  [SYNC]  Queue flushed.")

# ── Simulated sensor data ──────────────────────────────────────────────────────
def generate_position(t):
    """Fly a slow circle over the fire area."""
    angle = (t * 0.05) % (2 * math.pi)
    lat = BASE_LAT + (RADIUS_KM / 111.0) * math.sin(angle)
    lon = BASE_LON + (RADIUS_KM / 111.0) * math.cos(angle)
    alt = 120 + 10 * math.sin(angle * 2)   # altitude oscillates 110-130m
    return round(lat, 6), round(lon, 6), round(alt, 1)

def generate_telemetry(t):
    lat, lon, alt = generate_position(t)
    return {
        "node_id":        NODE_ID,
        "node_type":      "UAS",
        "timestamp":      datetime.now(timezone.utc).isoformat(),
        "lat":            lat,
        "lon":            lon,
        "alt_m":          alt,
        "battery_pct":    max(10, round(100 - (t * 0.05) % 90, 1)),
        "thermal_temp_c": round(320 + random.uniform(-15, 15), 1),  # fire heat signature
        "smoke_index":    round(random.uniform(0.6, 0.95), 2),
        "gps_sats":       random.randint(6, 12),
        "speed_ms":       round(random.uniform(8, 14), 1),
        "heading_deg":    round((t * 2.9) % 360, 1),
    }

# ── MQTT callbacks ─────────────────────────────────────────────────────────────
connected = False

def on_connect(client, userdata, flags, rc, props=None):
    global connected
    if rc == 0:
        connected = True
        print(f"[MQTT]  Connected to broker at {BROKER_HOST}:{BROKER_PORT}")
        # announce presence
        client.publish(
            f"wildfire/nodes/{NODE_ID}/status",
            json.dumps({"node_id": NODE_ID, "status": "online",
                        "timestamp": datetime.now(timezone.utc).isoformat()}),
            retain=True
        )
        # flush any queued messages
        flush_queue(userdata["conn"], client)
    else:
        connected = False
        print(f"[MQTT]  Connection failed (rc={rc})")

def on_disconnect(client, userdata, rc, props=None, reason=None):
    global connected
    connected = False
    print(f"[MQTT]  Disconnected (rc={rc}) — entering offline mode")

# ── Main loop ──────────────────────────────────────────────────────────────────
def main():
    conn = init_queue()

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=NODE_ID,
        clean_session=False   # broker remembers us across reconnects
    )
    client.user_data_set({"conn": conn})
    client.on_connect    = on_connect
    client.on_disconnect = on_disconnect

    # Will message: marks node offline if connection drops unexpectedly
    client.will_set(
        f"wildfire/nodes/{NODE_ID}/status",
        json.dumps({"node_id": NODE_ID, "status": "offline",
                    "timestamp": datetime.now(timezone.utc).isoformat()}),
        retain=True
    )

    print(f"[INIT]  UAS Edge Node {NODE_ID} starting...")
    print(f"[INIT]  Broker: {BROKER_HOST}:{BROKER_PORT}")
    print(f"[INIT]  Queue:  {QUEUE_DB}")
    print()

    client.connect_async(BROKER_HOST, BROKER_PORT, keepalive=10)
    client.loop_start()

    t = 0
    try:
        while True:
            telemetry = generate_telemetry(t)
            topic = f"wildfire/nodes/{NODE_ID}/telemetry"

            if connected:
                result = client.publish(topic, json.dumps(telemetry), qos=1)
                try:
                    result.wait_for_publish(timeout=2)
                    print(f"[TX]    lat={telemetry['lat']} lon={telemetry['lon']} "
                          f"alt={telemetry['alt_m']}m bat={telemetry['battery_pct']}% "
                          f"thermal={telemetry['thermal_temp_c']}°C")
                except Exception:
                    # publish timed out — treat as disconnected
                    enqueue(conn, topic, telemetry)
            else:
                enqueue(conn, topic, telemetry)

            t += 1
            time.sleep(2)

    except KeyboardInterrupt:
        print("\n[STOP]  Shutting down edge node.")
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    main()