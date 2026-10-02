"""Simulated ESP32 sensor. Publishes FrameBatch JSON to prodos/sensors/{id}/frames."""

import argparse
import json
import random
import time
import uuid

import paho.mqtt.client as mqtt

CHANNELS = [1, 6, 11]
AP_BSSIDS = ["AA:BB:CC:00:00:01", "AA:BB:CC:00:00:02", "AA:BB:CC:00:00:03"]
ROGUE_BSSID = "DE:AD:BE:EF:00:99"
SSID = "CafeWiFi"
ATTACKER_MAC = "11:22:33:44:55:66"


class FakeSensor:
    def __init__(self, sensor_id: str) -> None:
        self.sensor_id = sensor_id
        self.started = time.monotonic()
        self.batch_seq = 0
        self.evil_twin = False

    def beacon_frames(self) -> list[dict]:
        aps = AP_BSSIDS + ([ROGUE_BSSID] if self.evil_twin else [])
        frames = []
        for _ in range(10):
            bssid = random.choice(aps)
            frames.append(
                {
                    "uptime_ms": int((time.monotonic() - self.started) * 1000),
                    "timestamp": None,
                    "channel": random.choice(CHANNELS),
                    "frame_type": "beacon",
                    "src_mac": bssid,
                    "dst_mac": "FF:FF:FF:FF:FF:FF",
                    "bssid": bssid,
                    "ssid": SSID,
                    "rssi": random.randint(-70, -35),
                    "seq_num": random.randint(0, 4095),
                }
            )
        return frames

    def deauth_frames(self) -> list[dict]:
        return [
            {
                "uptime_ms": int((time.monotonic() - self.started) * 1000),
                "timestamp": None,
                "channel": random.choice(CHANNELS),
                "frame_type": "deauth",
                "src_mac": ATTACKER_MAC,
                "dst_mac": AP_BSSIDS[0],
                "bssid": AP_BSSIDS[0],
                "ssid": SSID,
                "rssi": random.randint(-60, -30),
                "seq_num": random.randint(0, 4095),
            }
            for _ in range(60)
        ]

    def next_batch(self, deauth: bool) -> dict:
        elapsed = time.monotonic() - self.started
        frames: list[dict] = []

        if self.evil_twin and elapsed >= 15:
            self.evil_twin = False
            frames.append(
                {
                    "uptime_ms": int(elapsed * 1000),
                    "timestamp": None,
                    "channel": 6,
                    "frame_type": "beacon",
                    "src_mac": ROGUE_BSSID,
                    "dst_mac": "FF:FF:FF:FF:FF:FF",
                    "bssid": ROGUE_BSSID,
                    "ssid": SSID,
                    "rssi": -41,
                    "seq_num": random.randint(0, 4095),
                }
            )

        frames.extend(self.deauth_frames() if deauth else self.beacon_frames())
        self.batch_seq += 1
        return {
            "sensor_id": self.sensor_id,
            "batch_seq": self.batch_seq,
            "frames": frames[:200],
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sensor", default="sensor-01", help="sensor_id")
    parser.add_argument("--host", default="localhost", help="mqtt broker host")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--evil-twin", action="store_true", help="clone the AP after 15s")
    parser.add_argument("--deauth", action="store_true", help="60 deauth/s after 10s")
    args = parser.parse_args()

    sensor = FakeSensor(args.sensor)
    sensor.evil_twin = args.evil_twin

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=str(uuid.uuid4()))
    client.connect(args.host, args.port, keepalive=60)
    client.loop_start()
    topic = f"prodos/sensors/{args.sensor}/frames"

    print(f"[{args.sensor}] publishing to {args.host}:{args.port} {topic}")
    try:
        while True:
            elapsed = time.monotonic() - sensor.started
            deauth = args.deauth and elapsed >= 10
            batch = sensor.next_batch(deauth)
            client.publish(topic, json.dumps(batch), qos=0)
            if deauth and elapsed < 11:
                print(f"[{args.sensor}] DEAUTH FLOOD STARTED")
            if args.evil_twin and 15 <= elapsed < 16:
                print(f"[{args.sensor}] EVIL TWIN CLONE {ROGUE_BSSID} APPEARED")
            time.sleep(1)
    except KeyboardInterrupt:
        print(f"\n[{args.sensor}] stopping")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()