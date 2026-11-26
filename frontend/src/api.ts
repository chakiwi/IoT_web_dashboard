export type ScanResult =
  | 'recognized'
  | 'unregistered'
  | 'inactive_card'
  | 'pending'
  | 'face_mismatch'
  | 'no_face_template'
  | 'expired'
  | 'legacy_nfc_only';

export type ScanEvent = {
  id: number;
  event_id: string;
  card_uid: string;
  result: ScanResult;
  student_code: string | null;
  full_name: string | null;
  class_name: string | null;
  occurred_at: string;
  received_at: string;
};

export type Student = {
  id: number;
  student_code: string;
  full_name: string;
  class_name: string;
  is_active: number;
  card_uid: string | null;
  card_active: number | null;
  last_scan_at: string | null;
  has_face: number;
};

export type InventoryCard = {
  id: number;
  uid: string;
  status: 'available' | 'reserved' | 'assigned' | 'disabled';
  created_at: string;
  reserved_at: string | null;
  assigned_at: string | null;
};

export type Registration = {
  registration_id: string;
  student_code: string;
  full_name: string;
  class_name: string;
  card_uid: string;
  status: 'waiting_for_scan' | 'captured' | 'approved' | 'rejected';
  created_at: string;
  captured_at: string | null;
  reviewed_at: string | null;
  rejection_reason: string | null;
  has_face_image: number;
};

export type Stats = {
  students: number;
  scans_today: number;
  recognized_today: number;
  flagged_today: number;
  registered_rate: number;
  face_templates: number;
  server_time: string;
};

export type Config = {
  demo_mode: boolean;
  database: string;
  api: string;
  transport: string[];
  timezone: string;
  server_time: string;
};

export async function request<T>(url: string, token: string | null, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {};
  if (options.body) headers['Content-Type'] = 'application/json';
  if (token) headers.Authorization = 'Bearer ' + token;
  const response = await fetch(url, {
    ...options,
    headers: { ...headers, ...options.headers },
    cache: 'no-store',
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const reason = typeof body.detail === 'string' ? body.detail : response.status + ' ' + response.statusText;
    const error = new Error(reason) as Error & { status?: number };
    error.status = response.status;
    throw error;
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function fmtTime(value: string | null | undefined, full = false): string {
  if (!value) return '—';
  try {
    return new Intl.DateTimeFormat('vi-VN', {
      timeZone: 'Asia/Ho_Chi_Minh',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      ...(full ? ({ day: '2-digit', month: '2-digit', year: 'numeric' } as const) : {}),
    }).format(new Date(value));
  } catch {
    return value;
  }
}
