# Attenda frontend

React/TypeScript dashboard connected to the FastAPI v3 endpoints. The existing dashboard structure and visual language are retained; additions include the new-registration queue, the reserved-card display, face-image review, and blank NFC-card inventory under Settings.

Development on Windows: `npm.cmd install` (first run), then `npm.cmd run dev` (Vite on 5173; API/WebSocket proxy to FastAPI on 8000).

Production build: `npm.cmd run build`. FastAPI serves `frontend/dist` when `start.bat` is used.

The browser uses admin bearer authentication for protected API requests. Device tokens are not stored in frontend code.
