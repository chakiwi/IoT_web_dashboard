# API contract phiên bản 1.0

## Auth (frontend → backend)

- `POST /api/v1/auth/login`: JSON `{ "username": "admin", "password": "..." }`, trả `access_token`, hạn 12 giờ.
- Request quản trị gửi `Authorization: Bearer <access_token>`.
- `GET /api/v1/students`: danh sách hồ sơ, UID đang hoạt động và lần quét gần nhất.
- `POST /api/v1/students`: `{student_code,full_name,class_name,email,card_uid,is_active}`.
- `PUT /api/v1/students/{id}`: cập nhật cả hồ sơ và liên kết UID.
- `DELETE /api/v1/students/{id}`: vô hiệu hóa hồ sơ/thẻ, không xóa lịch sử.
- `GET /api/v1/stations`, `POST /api/v1/stations`, `PUT /api/v1/stations/{id}`.
- `GET /api/v1/scans?limit=100`: các sự kiện, mới nhất trước.
- `GET /api/v1/stats`: đếm theo ngày trong múi giờ Việt Nam.
- `GET /api/v1/config`: chế độ demo, server, timezone.
- `POST /api/v1/demo/scan`: cùng payload với ESP32, chỉ khi `DEMO_MODE=true` và đã đăng nhập.
- `WS /ws/events`: sau `accept`, client gửi `{"type":"auth","token":"<admin-token>"}`, sau đó nhận `scan.created`, `stations.changed`, `students.changed`.

## Device (ESP32 / bridge → backend)

- `POST /api/v1/scans`: `X-Device-Token` riêng của từng trạm, JSON `event_id`, `station_id`, `card_uid`.
- `POST /api/v1/devices/heartbeat`: cùng header, JSON `{"station_id":"STATION_A"}`.
- `GET /api/v1/health`: kiểm tra server có chạy, không yêu cầu token.

**Ví dụ gửi từ Windows bằng Python `simulator/send_scan.py`:**

```json
{"event_id":"STATION_A-BOOT-1","station_id":"STATION_A","card_uid":"A1B200000001"}
```

**Phản hồi mẫu:**

```json
{
 "created":true,
 "event_id":"STATION_A-BOOT-1",
 "result":"recognized",
 "scan":{"event_id":"STATION_A-BOOT-1","station_id":"STATION_A","card_uid":"A1B200000001","full_name":"Nguyễn Minh Anh"},
 "message":"Đã lưu sự kiện"
}
```

`recognized` ở đây **chỉ** có nghĩa mã UID phù hợp thẻ đã đăng ký, không phải nhận diện người.

Khi ESP32 gửi lại **cùng event_id + station_id + UID**, phản hồi `created:false`; không thêm bản ghi. Nếu cùng event_id nhưng dữ liệu khác, server trả **409 Conflict**.

- `401`: token quản trị / thiết bị sai hoặc thiếu.
- `400`: dữ liệu trạm, UID hoặc nghiệp vụ không hợp lệ.
- `422`: JSON thiếu trường / sai kiểu.
- `409`: sự kiện xung đột hoặc MSSV/UID trùng.

Xem toàn bộ OpenAPI bằng `http://127.0.0.1:8000/docs`.
