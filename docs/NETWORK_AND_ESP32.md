# Network and device API flow — Attenda v3

## Local network

The laptop runs FastAPI, SQLite, and the built React dashboard. ESP32 communicates with the laptop over the same local Wi-Fi network. Internet access is not required when the router/hotspot allows local devices to communicate.

| Component | Example | Role |
|---|---|---|
| Router / hotspot | 192.168.1.1 | Local network only |
| Laptop server | 192.168.1.10:8000 | FastAPI, SQLite, dashboard |
| ESP32 + PN532 | 192.168.1.20 | Reads NFC UID and exchanges API messages |
| ESP32-S3-CAM | Connected to ESP32 | Captures/processes face image |

The IPs are examples. Run `ipconfig` on Windows to find the laptop's current LAN address. For local access from another device, run `start-lan.bat` only after changing the demo credentials and secrets in `.env`.

## New-student enrollment flow

1. Staff reads the real UID of each unused physical NFC card and adds it to **Settings → Unused NFC card inventory**. These UIDs enter `card_inventory` as `available`.
2. Staff enters `student_code`, `full_name`, and `class_name` in **Students → Add student**.
3. On confirmation, the server reserves one available UID and creates a `registration_queue` row with status `waiting_for_scan`. The official `students` table is not modified yet.
4. Staff gives the student the physical card whose UID is shown on that queue row.
5. When the device reads the card and captures the face, it sends the UID, face embedding, and image payload to `POST /api/v1/registrations/capture` with `X-Device-Token`.
6. The server matches the incoming UID to the reserved queue row and marks it `captured`.
7. Staff checks the captured face image in the dashboard. Only after approval does the server create the official student, card, and face-template records.

The matching is based on the real preloaded card UID, not the order in which students arrive. Staff must hand each person the physical card corresponding to the UID reserved for that registration. If a different physical card is scanned, it will not match that registration.

## Daily attendance flow

Daily attendance uses the already approved card and face template:

1. ESP32 reads `card_uid` and generates one unique `event_id` for this scan.
2. It sends `POST /api/v1/verification/start` with `event_id`, `card_uid`, and optional `session_id`.
3. For a valid registered card, the server returns that student's `face_embedding` and the same `event_id`.
4. ESP32 forwards the embedding to the face-processing device. The camera/device performs the comparison.
5. ESP32 sends `POST /api/v1/verification/complete` with the original `event_id` and `face_result` (`true` or `false`).
6. The server records attendance only when both NFC and face checks pass. Both requests belong to one scan attempt and must reuse exactly the same `event_id`.

A pending verification expires after 90 seconds. NFC-only `POST /api/v1/scans` is disabled; it cannot mark attendance.

## Device authentication and payloads

Every device request uses `X-Device-Token`, matching `DEVICE_TOKEN` in `.env`. Send JSON with UTF-8 and `Content-Type: application/json`.

Attendance start:

```json
{"event_id":"SCAN-0001","card_uid":"AABBCCDD","session_id":1}
```

Attendance complete:

```json
{"event_id":"SCAN-0001","face_result":true}
```

Registration capture:

```json
{
  "card_uid":"AABBCCDD",
  "face_embedding":"BASE64_EMBEDDING_BYTES",
  "embedding_dim":512,
  "face_image_base64":"BASE64_JPEG_BYTES",
  "image_mime":"image/jpeg"
}
```

For enrollment, the device only needs to send the actual `card_uid`, Base64 `face_embedding`, and Base64 `face_image_base64`. `event_id` may be omitted; the server will generate it. The registration image is transmitted as Base64 because the API payload is JSON. The backend decodes it and stores the image as binary bytes in SQLite. `embedding_dim` defaults to 512; `model_name` and `model_version` are optional. Accepted decoded image formats: JPEG, PNG, WebP; maximum 5 MB. The face embedding is stored separately from the image.

## Security notes

- Do not expose the API through router port forwarding or a public IP.
- Use a private LAN and disable client/AP isolation so the laptop and ESP32 can communicate.
- Change `ADMIN_PASSWORD`, `APP_SECRET`, and `DEVICE_TOKEN` before allowing shared-LAN access.
- Use HTTPS/TLS and device-specific authentication for deployment beyond a controlled lab network.
- A reserved card UID links an incoming capture to a queue record; staff must still check the face image before approving the registration.
