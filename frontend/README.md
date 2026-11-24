# Attenda frontend

Giao diện đã chốt được lấy lại từ bản `attenda-frontend.zip` ban đầu; giữ nguyên phần CSS và hệ layout. Các trang đã nối REST API thực của FastAPI, WebSocket, form quản trị, CSV và đăng nhập.

Development: `npm.cmd install` (lần đầu), `npm.cmd run dev` (Vite 5173, proxy `/api` + `/ws` về FastAPI localhost:8000).

Build production: `npm.cmd run build`, FastAPI phục vụ file trong `frontend/dist` khi chạy `start.bat`.

Không truy vấn SQLite trực tiếp từ React, không lưu device tokens ở frontend, không có AI/khuôn mặt trong phiên bản này.
