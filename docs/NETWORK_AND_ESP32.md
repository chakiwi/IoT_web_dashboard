# Network and ESP32 communication

## Attendance flow

1. ESP32 reads the NFC card UID using PN532.
2. ESP32 creates one unique `event_id` for this tap and sends `event_id + card_uid` to `POST /api/v1/verification/start` over Wi-Fi using HTTPS when the server is exposed through Cloudflare Tunnel.
3. The server validates the NFC card, finds its student, retrieves that student's active face embedding, and returns the embedding with the same `event_id`.
4. ESP32 forwards the embedding and `event_id` to ESP32-S3-CAM.
5. ESP32-S3-CAM captures the face, compares it with the received embedding, and returns `0` (no match) or `1` (match) to ESP32.
6. ESP32 sends `event_id + face_result` to `POST /api/v1/verification/complete`.
7. The server writes attendance only if the NFC validation is still valid and face verification succeeds.

Use a new event ID for every new tap. Keep the same event ID for both server requests in that tap. The pending verification expires after 60 seconds.

## Payloads

Start:

```json
{"event_id":"GATE-BOOT7-000001","card_uid":"A1B200000001","session_id":1}
```

Complete:

```json
{"event_id":"GATE-BOOT7-000001","face_result":1}
```

The device sends `X-Device-Token` in both requests. Do not send the embedding back to the server; it is returned to ESP32 for forwarding to S3-CAM.

## USB serial bridge (optional)

The optional `simulator/serial_bridge.py` expects one JSON message per serial line:

- `{"type":"verification_start","event_id":"...","card_uid":"...","session_id":1}` — bridge calls `/verification/start` and writes a `verification_ready` JSON line containing the embedding.
- `{"type":"face_result","event_id":"...","face_result":1}` — bridge calls `/verification/complete` and writes a `verification_complete` JSON line.

Run with:

```bash
python simulator/serial_bridge.py --port COM5
```

## Network notes

- ESP32 and the server must be able to reach each other over the selected network.
- For a Cloudflare Tunnel hostname, the device connects to the public HTTPS URL; the local FastAPI service can remain HTTP behind `cloudflared`.
- Keep `DEVICE_TOKEN`, `APP_SECRET`, and admin credentials private. Change the example values in `.env` before exposing the service beyond a trusted LAN.
