# Wildfire Mesh Demo — Setup Guide

## What you're building
- **Laptop** = broker + dashboard + GROUND-01 node
- **Pi** = UAS-01 edge node (the one that disconnects)

When you pull the Pi off the network, the dashboard shows it go dark,
a staleness timer counts up, and a queue count appears. Reconnect the Pi
and watch it sync everything automatically.

---

## Step 1 — Laptop setup

### Install Mosquitto (MQTT broker)
```bash
brew install mosquitto
```

Edit the config to enable WebSockets (needed for the browser dashboard):
```bash
nano /opt/homebrew/etc/mosquitto/mosquitto.conf
```

Add these lines at the bottom:
```
listener 1883
allow_anonymous true

listener 9001
protocol websockets
allow_anonymous true
```

Start the broker:
```bash
brew services start mosquitto
# or run directly:
mosquitto -c /opt/homebrew/etc/mosquitto/mosquitto.conf
```

### Find your laptop's local IP
```bash
ipconfig getifaddr en0
# e.g. 192.168.1.42  ← you'll need this for the Pi
```

### Install Python MQTT library
```bash
pip3 install paho-mqtt
```

### Run the ground node (laptop)
```bash
python3 command_node.py
```

### Open the dashboard
Open `dashboard.html` in Chrome. You should see:
- Broker connected (green dot top right)
- GROUND-01 node appearing on the map

---

## Step 2 — Pi setup

### SSH into the Pi
```bash
ssh pi@raspberrypi.local
# or use its IP address
```

### Install dependencies
```bash
sudo apt update
sudo apt install python3-pip -y
pip3 install paho-mqtt
```

### Copy the edge node script to the Pi
From your laptop:
```bash
scp uas_edge_node.py pi@raspberrypi.local:/home/pi/
```

### Edit the broker IP
On the Pi, open the script and change line 20:
```python
BROKER_HOST = "YOUR_LAPTOP_IP"   # e.g. "192.168.1.42"
```

### Make sure Pi and laptop are on the same WiFi
Both devices need to be on the same network.

### Run the edge node
```bash
python3 uas_edge_node.py
```

You should see UAS-01 appear on the dashboard map.

---

## Step 3 — The demo disconnect

### Option A — Pull the Pi off WiFi (cleanest demo)
```bash
# On the Pi:
sudo ip link set wlan0 down
# reconnect:
sudo ip link set wlan0 up
```

### Option B — Block the Pi's connection with a firewall rule
```bash
# On your laptop, block the Pi's IP:
sudo /sbin/pfctl -e
echo "block from 192.168.1.XX" | sudo pfctl -f -
# unblock:
sudo pfctl -d
```

### Option C — Just kill and restart the Pi script
Ctrl+C to stop it. Watch the dashboard show it offline.
Restart it and watch the queue flush.

---

## What the audience sees

1. Both nodes live on the map, pulsing
2. UAS-01 goes offline → card turns red, staleness bar drains, "NODE OFFLINE" appears
3. Queue count appears on left panel showing messages stored on device
4. Pi reconnects → queue flushes, card goes green, all data syncs
5. Map updates with Pi's current position

---

## Pitch talking points

- "This Pi represents a UAS ground control station in a canyon with no signal."
- "When it loses connectivity, it doesn't crash — it queues everything locally."
- "The command dashboard shows exactly how stale each node's data is."
- "The moment it reconnects, the queued data syncs automatically — no manual action."
- "This is the edge layer. Above it sits a tactical mesh, above that the cloud."

---

## Troubleshooting

**Dashboard shows "BROKER DISCONNECTED"**
→ Check Mosquitto is running: `brew services list | grep mosquitto`
→ Check port 9001 is open: `lsof -i :9001`

**Pi can't reach broker**
→ Ping your laptop from the Pi: `ping 192.168.1.42`
→ Check both are on the same WiFi

**No messages appearing**
→ Test MQTT manually: `mosquitto_sub -h localhost -t 'wildfire/#' -v`
→ Should show messages when edge node is running
