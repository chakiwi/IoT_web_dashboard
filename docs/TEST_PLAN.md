# Kiểm thử và giới hạn

## Đã chạy trong môi trường phát triển

- FastAPI startup tự tạo SQLite schema v3 và seed 12 sinh viên demo.
- Login và chặn truy cập không có token.
- Xác minh NFC, lấy embedding, xác minh khuôn mặt thành công/thất bại, retry idempotent và xung đột event ID.
- Thêm/sửa/vô hiệu hóa sinh viên và liên kết thẻ.
- WebSocket nhận sự kiện mới sau khi commit.

Lệnh: `python -m unittest discover -s tests -v` (dùng `.venv\\Scripts\\python.exe` trên Windows).

## Cần kiểm thử trực tiếp trên máy người dùng

- `setup.bat`: npm install / Vite build trên Windows sau khi giải nén.
- Trình duyệt Edge/Chrome xem giao diện, đăng nhập, tạo sinh viên, nhấn mô phỏng, kiểm tra phản hồi và dữ liệu lưu sau restart.
- Windows Firewall và các địa chỉ LAN thật.
- ESP32-S3 CAM: chân SPI trống/nguồn, USB CDC/COM, mode PN532, đầu đọc và tính tương thích của thẻ sinh viên thật.
- Không có đo lường độ ổn định 24/7; chưa test mất điện, ngoại tuyến dài ngày, nhiều trạm concurrent trong thực tế.

## Thử tay trên laptop

1. Đăng nhập, xem danh sách ban đầu.
2. Thêm sinh viên mới và UID hex chưa trùng.
3. Đăng ký face template cho sinh viên.
4. Chạy `python simulator/send_scan.py --uid <UID> --face-result 1`; xác nhận chỉ sau bước complete mới có scan event.
5. Chạy lại với `--face-result 0`; xác nhận sự kiện có trạng thái face mismatch nhưng không có attendance record.
6. Gửi cùng `event_id` lần complete hai lần; xác nhận không tạo bản ghi trùng.
7. Gửi UID không đăng ký hoặc sinh viên chưa có face template; xác nhận backend từ chối.
8. Tắt `start.bat`, mở lại để xác nhận dữ liệu SQLite vẫn còn.
