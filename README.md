# Attenda — AIoT Attendance Dashboard

Bản project này giữ nguyên giao diện React/CSS gốc và đồng bộ backend với SQLite schema v3 và luồng xác minh NFC + khuôn mặt hai giai đoạn.

## Thành phần

- Frontend: React + TypeScript + Vite
- Backend: FastAPI
- Database: SQLite
- Thiết bị: ESP32 + PN532, ESP32-S3-CAM qua Wi-Fi hoặc USB Serial bridge tùy cấu hình

## Cài đặt trên Windows

1. Cài Python 3.11+ và Node.js LTS.
2. Giải nén toàn bộ project.
3. Chạy `setup.bat` và chờ cài Python packages, npm packages, khởi tạo database và build frontend.
4. Chạy `start.bat`.
5. Mở `http://127.0.0.1:8000`.

Tài khoản demo mặc định sau khi tạo `.env` từ `.env.example`:

- Username: `admin`
- Password: `attenda123`

Nếu đã có file `.env` từ bản cũ, `setup.bat` không ghi đè file đó. Kiểm tra `ADMIN_USERNAME` và `ADMIN_PASSWORD` trong `.env` khi đăng nhập không thành công.

## Database schema v3

- `students`: hồ sơ sinh viên, không lưu email.
- `nfc_cards`: UID thẻ NFC gắn với sinh viên.
- `face_templates`: nơi lưu embedding khuôn mặt (chưa thực hiện nhận diện trực tiếp bằng camera).
- `attendance_sessions`: buổi điểm danh.
- `verification_attempts`: trạng thái chờ/kết quả của mỗi lần xác minh, liên kết bằng `event_id`.
- `scan_events`: lưu kết quả cuối cùng của lượt xác minh; có thể lưu lượt không khớp khuôn mặt để tra cứu, nhưng không tính là điểm danh.
- `attendance_records`: kết quả điểm danh theo sinh viên và buổi.

Không còn chức năng quản lý `stations` hoặc API heartbeat. Backend tự nâng database cũ lên schema v3; trước khi chuyển đổi database legacy có bảng `stations`, sẽ tạo file backup `_legacy_backup.db`. Database v2 được bổ sung cột xác minh và bảng `verification_attempts` mà không xóa dữ liệu cũ.

## Thiết bị / simulator

- Khóa thiết bị dùng chung: `DEVICE_TOKEN` trong `.env`.
- Firmware: cập nhật `DEVICE_TOKEN` trong `firmware/include/config.h` trùng với `.env`.
- Mô phỏng toàn bộ hai giai đoạn: `python simulator/send_scan.py --uid A1B200000001 --face-result 1`.
- `--face-result 0` mô phỏng khuôn mặt không khớp; lượt này không được ghi nhận điểm danh.
- USB Serial bridge: `python simulator/serial_bridge.py --port COM5` (đổi COM5 theo máy).

ESP32 gửi UID + event ID để lấy embedding; sau khi ESP32-S3-CAM so sánh khuôn mặt, ESP32 gửi kết quả 0/1 với cùng event ID. Server chỉ ghi điểm danh nếu cả hai bước hợp lệ.

## Kiểm tra

- Backend tests: `python -m unittest discover -s tests -v`
- Frontend: `cd frontend && npm.cmd install && npm.cmd run build`
- API docs: `http://127.0.0.1:8000/docs`

Chỉ dùng cấu hình demo trong môi trường local. Trước khi đưa lên LAN, đổi mật khẩu admin, `APP_SECRET`, `DEVICE_TOKEN` và chạy `python scripts/check_lan_security.py`.
