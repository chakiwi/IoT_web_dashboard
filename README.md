# Attenda — AIoT Attendance Dashboard

Bản project này giữ nguyên giao diện React/CSS gốc và đồng bộ backend với SQLite schema v2.

## Thành phần

- Frontend: React + TypeScript + Vite
- Backend: FastAPI
- Database: SQLite
- Thiết bị: ESP32 / PN532 qua Wi-Fi HTTP hoặc USB Serial bridge

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

## Database schema v2

- `students`: hồ sơ sinh viên, không lưu email.
- `nfc_cards`: UID thẻ NFC gắn với sinh viên.
- `face_templates`: nơi lưu embedding khuôn mặt (chưa thực hiện nhận diện trực tiếp bằng camera).
- `attendance_sessions`: buổi điểm danh.
- `scan_events`: sự kiện quét thẻ NFC.
- `attendance_records`: kết quả điểm danh theo sinh viên và buổi.

Không còn bảng `stations`. API có một endpoint tương thích đọc-only `/api/v1/stations` để dashboard gốc không lỗi khi tải dữ liệu; endpoint này trả danh sách rỗng. Việc quản lý trạm không phải một phần của schema v2.

Khi chạy lần đầu, backend tự nâng database đã có lên schema v2 và giữ lại dữ liệu sinh viên, thẻ, lượt quét. Với database cũ có bảng `stations`, quá trình nâng cấp tạo file backup `_legacy_backup.db` trước khi chuyển đổi.

## Thiết bị / simulator

- Khóa thiết bị dùng chung: `DEVICE_TOKEN` trong `.env`.
- Firmware: cập nhật `DEVICE_TOKEN` trong `firmware/include/config.h` trùng với `.env`.
- Gửi lượt quét mẫu: `python simulator/send_scan.py --uid A1B200000001`.
- USB Serial bridge: `python simulator/serial_bridge.py --port COM5` (đổi COM5 theo máy).

ESP32 chỉ gửi UID và event ID. UID xác định thẻ đã đăng ký, không chứng minh danh tính người đang cầm thẻ.

## Kiểm tra

- Backend tests: `python -m unittest discover -s tests -v`
- Frontend: `cd frontend && npm.cmd install && npm.cmd run build`
- API docs: `http://127.0.0.1:8000/docs`

Chỉ dùng cấu hình demo trong môi trường local. Trước khi đưa lên LAN, đổi mật khẩu admin, `APP_SECRET`, `DEVICE_TOKEN` và chạy `python scripts/check_lan_security.py`.
