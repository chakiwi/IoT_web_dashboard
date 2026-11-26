import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  LayoutDashboard,
  UsersRound,
  ScanFace,
  History,
  Settings2,
  Search,
  ArrowUpRight,
  CircleCheck,
  CreditCard,
  ShieldCheck,
  Download,
  CalendarDays,
  Menu,
  X,
  Plus,
  RefreshCw,
  LogOut,
  ChevronsUpDown,
  ChevronRight,
  Save,
  ClipboardList,
  Image as ImageIcon,
  Check,
  RotateCcw,
  Trash2,
  PackagePlus,
  Clock3,
} from 'lucide-react';
import {
  request,
  fmtTime,
  type ScanEvent,
  type Student,
  type Registration,
  type InventoryCard,
  type Stats,
  type Config,
} from '../../api';
import './AttendanceControlCenter.css';

type Page = 'overview' | 'students' | 'registrations' | 'activity' | 'settings';
type Result = 'verified' | 'review' | 'rejected' | 'pending' | 'legacy';
type Scan = {
  id: number;
  eventId: string;
  name: string;
  studentId: string;
  time: string;
  fullTime: string;
  result: Result;
  cardUid: string;
  initials: string;
  tone: string;
};
type StudentDraft = {
  student_code: string;
  full_name: string;
  class_name: string;
  is_active: boolean;
};

const nav = [
  { key: 'overview' as Page, label: 'Overview', icon: LayoutDashboard },
  { key: 'students' as Page, label: 'Students', icon: UsersRound },
  { key: 'registrations' as Page, label: 'New registrations', icon: ClipboardList },
  { key: 'activity' as Page, label: 'Scan History', icon: History },
];

const labels: Record<Page, string> = {
  overview: 'Overview',
  students: 'Students',
  registrations: 'New registrations',
  activity: 'Scan History',
  settings: 'Settings',
};

const statusNames: Record<Result, string> = {
  verified: 'Verified',
  review: 'Unregistered card',
  rejected: 'Verification failed',
  pending: 'Waiting for face match',
  legacy: 'Legacy NFC only · Not face verified',
};

const registrationStatusNames: Record<Registration['status'], string> = {
  waiting_for_scan: 'Waiting for scan',
  captured: 'Captured · Waiting for review',
  approved: 'Approved',
  rejected: 'Rejected',
};

const inventoryStatusNames: Record<InventoryCard['status'], string> = {
  available: 'Available',
  reserved: 'Reserved',
  assigned: 'Assigned',
  disabled: 'Disabled',
};

function mapScan(item: ScanEvent): Scan {
  const name = item.full_name || 'Unregistered card';
  const initials = item.full_name
    ? item.full_name.split(' ').slice(-2).map((part) => part[0]).join('').toUpperCase()
    : '?';
  const result: Result = item.result === 'recognized'
    ? 'verified'
    : item.result === 'unregistered'
      ? 'review'
      : item.result === 'pending'
        ? 'pending'
        : item.result === 'legacy_nfc_only'
          ? 'legacy'
          : 'rejected';
  return {
    id: item.id,
    eventId: item.event_id,
    name,
    studentId: item.student_code || 'No student ID',
    time: fmtTime(item.received_at),
    fullTime: fmtTime(item.received_at, true),
    result,
    cardUid: item.card_uid,
    initials,
    tone: result === 'review' ? 'yellow' : ['blue', 'peach', 'violet', 'green', 'pink'][Math.abs(item.id) % 5],
  };
}

function exportCsv(items: Scan[]) {
  const safe = (value: string) => {
    let text = String(value);
    if (/^[=+\-@]/.test(text)) text = "'" + text;
    return '"' + text.replaceAll('"', '""') + '"';
  };
  const headers = ['Student ID', 'Full name', 'Time', 'Result', 'Card UID'];
  const csv = [headers, ...items.map((item) => [item.studentId, item.name, item.fullTime, statusNames[item.result], item.cardUid])]
    .map((row) => row.map(safe).join(','))
    .join('\r\n');
  const anchor = document.createElement('a');
  const uri = URL.createObjectURL(new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8;' }));
  anchor.href = uri;
  anchor.download = 'attenda-scan-history.csv';
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(uri), 1000);
}

const StatusBadge = ({ status }: { status: Result }) => (
  <span className={'a-status a-status--' + status}>
    <span className="a-dot" />
    {statusNames[status]}
  </span>
);

function FaceMark() {
  return <span className="a-mark"><ScanFace size={30} strokeWidth={2} /></span>;
}

const emptyStudent: StudentDraft = {
  student_code: '',
  full_name: '',
  class_name: '',
  is_active: true,
};

export const AttendanceControlCenter = () => {
  const [token, setToken] = useState<string | null>(() => sessionStorage.getItem('attenda_admin_token'));
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('');
  const [loginError, setLoginError] = useState('');
  const [loggingIn, setLoggingIn] = useState(false);
  const [page, setPage] = useState<Page>('overview');
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState('all');
  const [rawScans, setRawScans] = useState<ScanEvent[]>([]);
  const [students, setStudents] = useState<Student[]>([]);
  const [registrations, setRegistrations] = useState<Registration[]>([]);
  const [inventoryCards, setInventoryCards] = useState<InventoryCard[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [config, setConfig] = useState<Config | null>(null);
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [selectedScan, setSelectedScan] = useState<Scan | null>(null);
  const [editingStudent, setEditingStudent] = useState<Student | null | undefined>(undefined);
  const [studentDraft, setStudentDraft] = useState<StudentDraft>(emptyStudent);
  const [selectedRegistration, setSelectedRegistration] = useState<Registration | null>(null);
  const [registrationImageUrl, setRegistrationImageUrl] = useState<string | null>(null);
  const [inventoryUid, setInventoryUid] = useState('');
  const [saving, setSaving] = useState(false);

  const scans = useMemo(() => rawScans.map(mapScan), [rawScans]);
  const filtered = useMemo(
    () => scans.filter((row) =>
      (row.name + ' ' + row.studentId + ' ' + row.cardUid).toLowerCase().includes(query.toLowerCase()) &&
      (filter === 'all' || row.result === filter),
    ),
    [scans, query, filter],
  );
  const studentFiltered = useMemo(
    () => students.filter((student) =>
      (student.full_name + ' ' + student.student_code + ' ' + student.class_name + ' ' + (student.card_uid || ''))
        .toLowerCase().includes(query.toLowerCase()),
    ),
    [students, query],
  );
  const availableCardCount = useMemo(
    () => inventoryCards.filter((card) => card.status === 'available').length,
    [inventoryCards],
  );

  function toast(message: string) {
    setNotice(message);
    window.setTimeout(() => setNotice(''), 3800);
  }

  const logout = useCallback(() => {
    sessionStorage.removeItem('attenda_admin_token');
    setToken(null);
    setConnected(false);
  }, []);

  const refresh = useCallback(async (showSpinner = false) => {
    if (!token) return;
    if (showSpinner) setLoading(true);
    try {
      const [scanResult, studentResult, registrationResult, cardResult, statsResult, configResult] = await Promise.all([
        request<ScanEvent[]>('/api/v1/scans?limit=300', token),
        request<Student[]>('/api/v1/students', token),
        request<Registration[]>('/api/v1/registrations', token),
        request<InventoryCard[]>('/api/v1/cards/inventory', token),
        request<Stats>('/api/v1/stats', token),
        request<Config>('/api/v1/config', token),
      ]);
      setRawScans(scanResult);
      setStudents(studentResult);
      setRegistrations(registrationResult);
      setSelectedRegistration((current) => {
        if (!current) return current;
        return registrationResult.find((item) => item.registration_id === current.registration_id) ?? current;
      });
      setInventoryCards(cardResult);
      setStats(statsResult);
      setConfig(configResult);
      setError('');
    } catch (caught) {
      const issue = caught as Error & { status?: number };
      if (issue.status === 401) {
        logout();
        return;
      }
      setError(issue.message || 'Could not retrieve data from FastAPI');
    } finally {
      setLoading(false);
    }
  }, [token, logout]);

  useEffect(() => {
    if (!token) return;
    void refresh(true);
    const interval = window.setInterval(() => void refresh(false), 15000);
    return () => window.clearInterval(interval);
  }, [token, refresh]);

  useEffect(() => {
    if (!token) return;
    let closed = false;
    let socket: WebSocket | null = null;
    let retry: number | undefined;
    const connect = () => {
      if (closed) return;
      const protocol = location.protocol === 'https:' ? 'wss' : 'ws';
      socket = new WebSocket(`${protocol}://${location.host}/ws/events`);
      socket.onopen = () => socket?.send(JSON.stringify({ type: 'auth', token }));
      socket.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          if (message.type === 'ready') setConnected(true);
          if (['scan.created', 'students.changed', 'registrations.changed', 'cards.changed', 'attendance.changed'].includes(message.type)) {
            void refresh();
          }
        } catch {
          // Ignore unknown WebSocket payloads.
        }
      };
      socket.onclose = () => {
        setConnected(false);
        if (!closed) retry = window.setTimeout(connect, 2500);
      };
      socket.onerror = () => setConnected(false);
    };
    connect();
    return () => {
      closed = true;
      if (retry) window.clearTimeout(retry);
      socket?.close();
      setConnected(false);
    };
  }, [token, refresh]);

  useEffect(() => {
    if (!selectedRegistration || !token || !selectedRegistration.has_face_image) {
      setRegistrationImageUrl(null);
      return;
    }
    let objectUrl: string | null = null;
    let cancelled = false;
    fetch(`/api/v1/registrations/${encodeURIComponent(selectedRegistration.registration_id)}/image`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: 'no-store',
    })
      .then((response) => {
        if (!response.ok) throw new Error('Image unavailable');
        return response.blob();
      })
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setRegistrationImageUrl(objectUrl);
      })
      .catch(() => setRegistrationImageUrl(null));
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [selectedRegistration?.registration_id, selectedRegistration?.has_face_image, token]);

  async function login(event: React.FormEvent) {
    event.preventDefault();
    setLoggingIn(true);
    setLoginError('');
    try {
      const result = await request<{ access_token: string }>('/api/v1/auth/login', null, {
        method: 'POST',
        body: JSON.stringify({ username, password }),
      });
      sessionStorage.setItem('attenda_admin_token', result.access_token);
      setToken(result.access_token);
      setPassword('');
    } catch (caught) {
      setLoginError((caught as Error).message);
    } finally {
      setLoggingIn(false);
    }
  }

  const go = (nextPage: Page) => {
    setPage(nextPage);
    setMobileOpen(false);
    setQuery('');
    setFilter('all');
  };

  const openStudent = (student?: Student) => {
    setEditingStudent(student || null);
    setStudentDraft(student
      ? {
          student_code: student.student_code,
          full_name: student.full_name,
          class_name: student.class_name,
          is_active: !!student.is_active,
        }
      : { ...emptyStudent },
    );
  };

  async function saveStudent(event: React.FormEvent) {
    event.preventDefault();
    if (!token) return;
    setSaving(true);
    try {
      if (editingStudent) {
        await request(`/api/v1/students/${editingStudent.id}`, token, {
          method: 'PUT',
          body: JSON.stringify(studentDraft),
        });
        setEditingStudent(undefined);
        await refresh();
        toast('Student information updated');
      } else {
        const result = await request<{ registration_id: string; card_uid: string }>('/api/v1/registrations', token, {
          method: 'POST',
          body: JSON.stringify({
            student_code: studentDraft.student_code,
            full_name: studentDraft.full_name,
            class_name: studentDraft.class_name,
          }),
        });
        setEditingStudent(undefined);
        await refresh();
        go('registrations');
        toast(`Registration created · Assigned card UID: ${result.card_uid}`);
      }
    } catch (caught) {
      toast('Could not save: ' + (caught as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function disableStudent(student: Student) {
    if (!token || !window.confirm(`Deactivate ${student.full_name} and the card currently in use?`)) return;
    try {
      await request(`/api/v1/students/${student.id}`, token, { method: 'DELETE' });
      setEditingStudent(undefined);
      await refresh();
      toast('Student deactivated');
    } catch (caught) {
      toast((caught as Error).message);
    }
  }

  async function addInventoryCard(event: React.FormEvent) {
    event.preventDefault();
    if (!token) return;
    setSaving(true);
    try {
      const result = await request<{ card_uid: string }>('/api/v1/cards/inventory', token, {
        method: 'POST',
        body: JSON.stringify({ card_uid: inventoryUid }),
      });
      setInventoryUid('');
      await refresh();
      toast(`Card ${result.card_uid} added to inventory`);
    } catch (caught) {
      toast('Could not add card: ' + (caught as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function removeInventoryCard(card: InventoryCard) {
    if (!token || !window.confirm(`Remove unused card ${card.uid} from inventory?`)) return;
    try {
      const result = await request<{ status: 'removed' | 'disabled' }>(`/api/v1/cards/inventory/${encodeURIComponent(card.uid)}`, token, { method: 'DELETE' });
      await refresh();
      toast(result.status === 'disabled' ? 'Card disabled to preserve registration history' : 'Card removed from inventory');
    } catch (caught) {
      toast((caught as Error).message);
    }
  }

  async function approveRegistration(registration: Registration) {
    if (!token || !window.confirm(`Approve registration for ${registration.full_name}?`)) return;
    setSaving(true);
    try {
      await request(`/api/v1/registrations/${encodeURIComponent(registration.registration_id)}/approve`, token, { method: 'POST' });
      setSelectedRegistration(null);
      await refresh();
      toast(`${registration.full_name} added to Students`);
    } catch (caught) {
      toast('Could not approve: ' + (caught as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function rejectRegistration(registration: Registration) {
    if (!token || !window.confirm(`Reject ${registration.full_name}'s registration and release the reserved card?`)) return;
    setSaving(true);
    try {
      await request(`/api/v1/registrations/${encodeURIComponent(registration.registration_id)}/reject`, token, { method: 'POST' });
      setSelectedRegistration(null);
      await refresh();
      toast('Registration rejected; card returned to Available inventory');
    } catch (caught) {
      toast((caught as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function retryRegistration(registration: Registration) {
    if (!token || !window.confirm(`Request a new face capture for ${registration.full_name}?`)) return;
    setSaving(true);
    try {
      await request(`/api/v1/registrations/${encodeURIComponent(registration.registration_id)}/retry`, token, { method: 'POST' });
      setSelectedRegistration({ ...registration, status: 'waiting_for_scan', has_face_image: 0, captured_at: null });
      await refresh();
      toast('Registration returned to Waiting for scan');
    } catch (caught) {
      toast((caught as Error).message);
    } finally {
      setSaving(false);
    }
  }

  if (!token) {
    return (
      <div className="a-login-screen">
        <form className="a-login-panel" onSubmit={login}>
          <FaceMark />
          <h1>attenda<span style={{ color: '#67a587' }}>.</span></h1>
          <p>Sign in to manage NFC and face attendance on the internal server.</p>
          <label>Username<input autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} required /></label>
          <label>Password<input type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required /></label>
          {loginError && <div className="a-inline-error">{loginError}</div>}
          <button type="submit" className="a-button a-button--dark" disabled={loggingIn}>{loggingIn ? 'Signing in…' : 'Sign in to Dashboard'}</button>
          <small>Default demo credentials: admin / attenda123. Change the password before using this on a shared network.</small>
        </form>
      </div>
    );
  }

  return (
    <div className="a-app">
      {mobileOpen && <button className="a-overlay" aria-label="Close menu" onClick={() => setMobileOpen(false)} />}
      <aside className={'a-sidebar ' + (collapsed ? 'is-collapsed ' : '') + (mobileOpen ? 'is-mobile-open' : '')}>
        <div className="a-brand">
          <FaceMark />
          <div className="a-brandtext"><strong>attenda<span>.</span></strong><small>Identity & attendance</small></div>
          <button className="a-collapse" aria-label="Collapse sidebar" onClick={() => setCollapsed((value) => !value)}><ChevronsUpDown size={16} /></button>
        </div>
        <div className="a-side-section">WORKSPACE</div>
        <nav className="a-nav" aria-label="Main navigation">
          {nav.map((item) => (
            <button key={item.key} className={'a-navitem ' + (page === item.key ? 'active' : '')} onClick={() => go(item.key)} title={item.label}>
              <item.icon size={19} strokeWidth={1.9} />
              <span>{item.label}</span>
              {item.key === 'activity' && <em>{Math.min(stats?.scans_today || 0, 99)}</em>}
              {item.key === 'registrations' && registrations.length > 0 && <em>{Math.min(registrations.length, 99)}</em>}
            </button>
          ))}
        </nav>
        <div className="a-side-section a-side-section--lower">SYSTEM</div>
        <nav className="a-nav">
          <button className={'a-navitem ' + (page === 'settings' ? 'active' : '')} onClick={() => go('settings')} title="Settings">
            <Settings2 size={19} strokeWidth={1.9} /><span>Settings</span>
          </button>
        </nav>
        <div className="a-side-bottom">
          <button className="a-profile" onClick={logout} title="Log out">
            <span className="a-avatar a-avatar--admin">AD</span>
            <span><strong>Administrator</strong><small>Log out</small></span>
            <LogOut size={20} />
          </button>
        </div>
      </aside>

      <main className="a-main">
        <header className="a-topbar">
          <div className="a-top-left">
            <button className="a-mobile-menu" onClick={() => setMobileOpen(true)} aria-label="Open menu"><Menu size={21} /></button>
            <span>Workspace</span><ChevronRight size={15} /><strong>{labels[page]}</strong>
          </div>
          <div className="a-top-right">
            <span className="a-demo-label"><span /> {connected ? 'Connected' : config?.demo_mode ? 'Demo mode' : 'Connecting'}</span>
            <span className="a-separator" />
            <span className="a-avatar a-avatar--top">AD</span>
          </div>
        </header>

        <div className="a-content">
          <div className="a-page-head">
            <div>
              <p className="a-kicker">NFC ATTENDANCE SYSTEM</p>
              {page !== 'overview' && <h1>{labels[page]}</h1>}
              <p className="a-subtitle">
                {page === 'overview' ? 'Monitor NFC and face verification in one place.' :
                  page === 'students' ? 'Manage approved student profiles and registered cards.' :
                    page === 'registrations' ? 'Collect card and face data, then review registrations before approval.' :
                      page === 'activity' ? 'Review NFC and face verification events from the device.' :
                        'Configure the internal attendance system and unused NFC card inventory.'}
              </p>
            </div>
            <div className="a-head-actions">
              <span className="a-date"><CalendarDays size={16} /> {new Date().toLocaleDateString('en-US', { day: '2-digit', month: 'long', year: 'numeric', timeZone: 'Asia/Ho_Chi_Minh' })}</span>
            </div>
          </div>

          {error && <div className="a-inline-error">Could not sync with the backend: {error} <button onClick={() => void refresh(true)}>Retry</button></div>}
          {loading && <p className="a-loading">Loading data from SQLite via FastAPI…</p>}

          {page === 'overview' && <>
            <section className="a-feature">
              <div className="a-feature-copy">
                <div className="a-feature-chip"><span /> {connected ? 'Dashboard connected' : 'Checking connection'}</div>
                <h2>Every attendance check-in.<br /><span>Clearly verified.</span></h2>
                <button onClick={() => go('activity')}>View activity history <ArrowUpRight size={17} /></button>
              </div>
              <div className="a-feature-visual" aria-hidden="true">
                <div className="a-scan-panel">
                  <div className="a-scan-corners"><ScanFace size={72} strokeWidth={1.1} /></div>
                  <div className="a-scan-pulse" />
                  <div className="a-scan-progress"><span /><span /><span /><span /><span /><span /><span /><span /><span /><span /><span /><span /></div>
                  <div className="a-scan-confirm"><CircleCheck size={15} /> NFC + face verified</div>
                </div>
                <div className="a-nfc-float"><CreditCard size={18} /><span>NFC events</span><i /></div>
              </div>
            </section>
            <section className="a-metrics" aria-label="Statistics">
              <div className="a-metric"><div className="a-metric-top"><span>Total students</span><UsersRound size={24} /></div><strong>{stats?.students ?? '—'}</strong><p>Active in SQLite</p></div>
              <div className="a-metric"><div className="a-metric-top"><span>Today's attempts</span><ScanFace size={24} /></div><strong>{stats?.scans_today ?? '—'}</strong><p>NFC scans received</p></div>
              <div className="a-metric"><div className="a-metric-top"><span>Face verified</span><ShieldCheck size={24} /></div><strong>{stats?.registered_rate ?? '—'}<span className="a-percent">%</span></strong><p>Of today's attempts</p></div>
            </section>
            <div className="a-two-col">
              <section className="a-panel a-activity-panel">
                <div className="a-panel-head"><div><h3>Recent activity</h3><p>Latest verification attempts saved on the server</p></div><button className="a-linkbtn" onClick={() => go('activity')}>View all <ArrowUpRight size={15} /></button></div>
                <ScanTable rows={scans.slice(0, 5)} onSelect={setSelectedScan} />
              </section>
            </div>
            <div className="a-note"><span><ShieldCheck size={16} /></span><p><strong>Attendance requires both checks.</strong> A valid NFC card identifies the registered student; attendance is recorded only after the face match succeeds.</p></div>
          </>}

          {page === 'activity' && <section className="a-panel a-full-panel">
            <div className="a-panel-head"><div><h3>Verification history</h3><p>{filtered.length} events match the current filters</p></div><button className="a-button a-button--outline" onClick={() => exportCsv(filtered)}><Download size={16} /> Export CSV</button></div>
            <div className="a-toolbar">
              <div className="a-search"><Search size={18} /><input aria-label="Search scans" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search by student, UID, or student ID..." /></div>
              <div className="a-filters">
                {([['all', 'All'], ['verified', 'Verified'], ['review', 'Unregistered'], ['rejected', 'Failed'], ['pending', 'Pending'], ['legacy', 'Legacy NFC only']] as const).map(([key, label]) =>
                  <button key={key} className={filter === key ? 'selected' : ''} onClick={() => setFilter(key)}>{label}</button>,
                )}
              </div>
            </div>
            <ScanTable rows={filtered} onSelect={setSelectedScan} />
          </section>}

          {page === 'students' && <section className="a-panel a-full-panel">
            <div className="a-panel-head"><div><h3>Student directory</h3><p>Only approved registrations appear here</p></div><button className="a-button a-button--dark" onClick={() => openStudent()}><Plus size={16} /> Add student</button></div>
            <div className="a-toolbar">
              <div className="a-search"><Search size={18} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search by name, class, student ID, or UID..." aria-label="Search students" /></div>
              <span className="a-count-pill">{studentFiltered.length} students</span>
            </div>
            <div className="a-tablewrap">
              <table className="a-table">
                <thead><tr><th>STUDENT</th><th>STUDENT ID</th><th>CLASS</th><th>CARD UID</th><th>FACE</th><th>STATUS</th><th /></tr></thead>
                <tbody>
                  {studentFiltered.map((student) => <tr key={student.id} onClick={() => openStudent(student)} tabIndex={0} onKeyDown={(event) => event.key === 'Enter' && openStudent(student)}>
                    <td><div className="a-person"><span className="a-avatar a-avatar--blue">{student.full_name.split(' ').slice(-2).map((part) => part[0]).join('').toUpperCase()}</span><span><strong>{student.full_name}</strong><small>Student</small></span></div></td>
                    <td>{student.student_code}</td><td>{student.class_name}</td><td><span className="a-location">{student.card_uid || 'No card assigned'}</span></td>
                    <td><span className={'a-student-status ' + (student.has_face ? 'online' : 'offline')}><i />{student.has_face ? 'Registered' : 'Missing'}</span></td>
                    <td><span className={'a-student-status ' + (student.is_active ? 'online' : 'offline')}><i />{student.is_active ? 'Active' : 'Invalid'}</span></td><td><ChevronRight size={17} /></td>
                  </tr>)}
                </tbody>
              </table>
              {studentFiltered.length === 0 && <div className="a-empty">No matching students. Add a student or change your search term.</div>}
            </div>
          </section>}

          {page === 'registrations' && <section className="a-panel a-full-panel">
            <div className="a-panel-head"><div><h3>Registration queue</h3><p>Reserved cards are linked to each student's registration before the student scans</p></div><span className="a-count-pill">{registrations.length} pending</span></div>
            <div className="a-queue-summary">
              <div><strong>{registrations.filter((item) => item.status === 'waiting_for_scan').length}</strong><span>Waiting for scan</span></div>
              <div><strong>{registrations.filter((item) => item.status === 'captured').length}</strong><span>Ready for review</span></div>
              <div><strong>{availableCardCount}</strong><span>Unused cards available</span></div>
            </div>
            <div className="a-tablewrap">
              <table className="a-table">
                <thead><tr><th>STUDENT</th><th>STUDENT ID</th><th>CLASS</th><th>RESERVED CARD UID</th><th>STATUS</th><th /></tr></thead>
                <tbody>
                  {registrations.map((registration) => <tr key={registration.registration_id} onClick={() => setSelectedRegistration(registration)} tabIndex={0} onKeyDown={(event) => event.key === 'Enter' && setSelectedRegistration(registration)}>
                    <td><div className="a-person"><span className="a-avatar a-avatar--blue">{registration.full_name.split(' ').slice(-2).map((part) => part[0]).join('').toUpperCase()}</span><span><strong>{registration.full_name}</strong><small>{registration.registration_id}</small></span></div></td>
                    <td>{registration.student_code}</td><td>{registration.class_name}</td><td><span className="a-location">{registration.card_uid}</span></td>
                    <td><span className={'a-registration-status a-registration-status--' + registration.status}>{registrationStatusNames[registration.status]}</span></td><td><ChevronRight size={17} /></td>
                  </tr>)}
                </tbody>
              </table>
              {registrations.length === 0 && <div className="a-empty">No pending registrations. Use Add student to create a new registration.</div>}
            </div>
          </section>}

          {page === 'settings' && <>
            <section className="a-panel a-settings">
              <h3>System config</h3>
              <div className="a-setting-row"><span><strong>Current API</strong><small>Backend provides data for React and ESP32</small></span><code>{location.origin}</code></div>
              <div className="a-setting-row"><span><strong>Transmission method</strong><small>ESP32 sends NFC and face verification data</small></span><code>{config?.transport.join(' / ') || 'Loading'}</code></div>
              <div className="a-setting-row"><span><strong>Database</strong><small>Stored on the internal Windows server</small></span><code>{config?.database || 'SQLite'}</code></div>
              <div className="a-setting-row"><span><strong>Operating mode</strong><small>Demo mode seeds fictional student records</small></span><span className="a-status a-status--review">{config?.demo_mode ? 'Demo mode' : 'Production mode'}</span></div>
              <div className="a-setting-row"><span><strong>Real-time updates</strong><small>WebSocket with automatic resynchronization after disconnection</small></span><code>{connected ? 'Connected' : 'Reconnecting'}</code></div>
              <div className="a-settings-actions"><button className="a-button a-button--outline" onClick={() => void refresh(true)}><RefreshCw size={16} /> Sync data</button><button className="a-button a-button--outline" onClick={logout}><LogOut size={16} /> Log out</button></div>
            </section>
            <section className="a-panel a-inventory-panel">
              <div className="a-panel-head"><div><h3>Unused NFC card inventory</h3><p>Add scanned UIDs of blank cards here before creating student registrations.</p></div><span className="a-count-pill">{availableCardCount} available</span></div>
              <form className="a-inventory-form" onSubmit={(event) => void addInventoryCard(event)}>
                <label>Card UID<input value={inventoryUid} onChange={(event) => setInventoryUid(event.target.value.toUpperCase())} placeholder="Example: AABBCCDD" required /></label>
                <button className="a-button a-button--dark" type="submit" disabled={saving}><PackagePlus size={16} /> Add unused card</button>
              </form>
              <div className="a-tablewrap">
                <table className="a-table"><thead><tr><th>CARD UID</th><th>STATUS</th><th>ADDED</th><th /></tr></thead>
                  <tbody>{inventoryCards.map((card) => <tr key={card.uid}><td><strong>{card.uid}</strong></td><td><span className={'a-registration-status a-registration-status--' + card.status}>{inventoryStatusNames[card.status]}</span></td><td>{fmtTime(card.created_at, true)}</td><td>{card.status === 'available' && <button className="a-icon-action" title="Remove unused card" onClick={() => void removeInventoryCard(card)}><Trash2 size={16} /></button>}</td></tr>)}</tbody>
                </table>
                {inventoryCards.length === 0 && <div className="a-empty">No blank NFC cards have been added yet.</div>}
              </div>
              <div className="a-note"><span><CreditCard size={16} /></span><p><strong>Important:</strong> Add the real UID of each physical blank card first. When a registration is created, the system reserves one Available UID and displays it in the queue so staff can hand out the matching physical card.</p></div>
            </section>
          </>}
        </div>
        <footer className="a-footer"><span>© 2026 Attenda · AIoT Attendance System</span><span>Local-first · NFC + face verification</span></footer>
      </main>

      {selectedScan && <div className="a-modal-backdrop" onClick={() => setSelectedScan(null)}>
        <section className="a-modal" role="dialog" aria-modal="true" aria-label="Verification details" onClick={(event) => event.stopPropagation()}>
          <div className="a-modal-top"><h3>Verification details</h3><button onClick={() => setSelectedScan(null)} aria-label="Close"><X size={20} /></button></div>
          <div className="a-modal-person"><span className={'a-avatar a-avatar--' + selectedScan.tone}>{selectedScan.initials}</span><span><strong>{selectedScan.name}</strong><small>{selectedScan.studentId}</small></span></div>
          <div className="a-modal-details"><div><span>Result</span><StatusBadge status={selectedScan.result} /></div><div><span>Card UID</span><strong>{selectedScan.cardUid}</strong></div><div><span>Time</span><strong>{selectedScan.fullTime}</strong></div><div><span>Method</span><strong>NFC + face</strong></div><div><span>Event ID</span><strong className="a-small-id">{selectedScan.eventId}</strong></div></div>
          <button className="a-button a-button--dark" onClick={() => setSelectedScan(null)}>Close details</button>
        </section>
      </div>}

      {editingStudent !== undefined && <div className="a-modal-backdrop" onClick={() => setEditingStudent(undefined)}>
        <section className="a-modal a-form-modal a-student-form-modal" role="dialog" aria-modal="true" aria-label="Student information" onClick={(event) => event.stopPropagation()}>
          <div className="a-modal-top"><h3>{editingStudent ? 'Edit student' : 'Add student'}</h3><button onClick={() => setEditingStudent(undefined)} aria-label="Close"><X size={20} /></button></div>
          <form onSubmit={(event) => void saveStudent(event)} className="a-form">
            <div className={!editingStudent ? 'a-registration-form-grid' : ''}>
              <div className="a-registration-fields">
                <label>Full name<input required value={studentDraft.full_name} onChange={(event) => setStudentDraft((draft) => ({ ...draft, full_name: event.target.value }))} /></label>
                <label>Student ID<input required value={studentDraft.student_code} onChange={(event) => setStudentDraft((draft) => ({ ...draft, student_code: event.target.value }))} /></label>
                <label>Class<input required value={studentDraft.class_name} onChange={(event) => setStudentDraft((draft) => ({ ...draft, class_name: event.target.value }))} /></label>
                {editingStudent && <label className="a-check-label"><input type="checkbox" checked={studentDraft.is_active} onChange={(event) => setStudentDraft((draft) => ({ ...draft, is_active: event.target.checked }))} /> Active</label>}
              </div>
              {!editingStudent && <div className="a-face-preview-wrap"><strong>Face image</strong><div className="a-face-preview"><ImageIcon size={30} /><span>No image</span></div><small>Face image will appear after the student scans the assigned card.</small></div>}
            </div>
            {!editingStudent && <p className="a-registration-hint">Confirming this form creates a pending registration and reserves one unused NFC card. The student is not added to the official directory until a manager approves the captured face data.</p>}
            <button disabled={saving} type="submit" className="a-button a-button--dark"><Save size={16} /> {saving ? 'Saving…' : editingStudent ? 'Save changes' : 'Confirm registration'}</button>
            {editingStudent && !!editingStudent.is_active && <button type="button" className="a-danger-button" onClick={() => void disableStudent(editingStudent)}>Deactivate student</button>}
          </form>
        </section>
      </div>}

      {selectedRegistration && <div className="a-modal-backdrop" onClick={() => setSelectedRegistration(null)}>
        <section className="a-modal a-registration-detail-modal" role="dialog" aria-modal="true" aria-label="Registration details" onClick={(event) => event.stopPropagation()}>
          <div className="a-modal-top"><div><h3>Registration review</h3><small className="a-registration-id">{selectedRegistration.registration_id}</small></div><button onClick={() => setSelectedRegistration(null)} aria-label="Close"><X size={20} /></button></div>
          <div className="a-registration-review-grid">
            <div className="a-registration-review-info">
              <div className="a-modal-details">
                <div><span>Full name</span><strong>{selectedRegistration.full_name}</strong></div>
                <div><span>Student ID</span><strong>{selectedRegistration.student_code}</strong></div>
                <div><span>Class</span><strong>{selectedRegistration.class_name}</strong></div>
                <div><span>Reserved card UID</span><strong>{selectedRegistration.card_uid}</strong></div>
                <div><span>Status</span><span className={'a-registration-status a-registration-status--' + selectedRegistration.status}>{registrationStatusNames[selectedRegistration.status]}</span></div>
                <div><span>Captured at</span><strong>{fmtTime(selectedRegistration.captured_at, true)}</strong></div>
              </div>
              {selectedRegistration.status === 'waiting_for_scan' && <div className="a-inline-info"><Clock3 size={16} /> Waiting for the student to scan the assigned physical card at the reader.</div>}
              {selectedRegistration.status === 'captured' && <div className="a-inline-info"><ShieldCheck size={16} /> Check that the face image is clear and belongs to the student before approval.</div>}
            </div>
            <div className="a-review-image-wrap"><strong>Captured face image</strong><div className="a-review-image">{registrationImageUrl ? <img src={registrationImageUrl} alt={`Face capture for ${selectedRegistration.full_name}`} /> : <><ImageIcon size={32} /><span>No image</span></>}</div><small>{selectedRegistration.has_face_image ? 'Image stored by the server' : 'No face image captured yet'}</small></div>
          </div>
          <div className="a-registration-actions">
            {selectedRegistration.status === 'captured' && <button className="a-button a-button--outline" disabled={saving} onClick={() => void retryRegistration(selectedRegistration)}><RotateCcw size={16} /> Request recapture</button>}
            <button className="a-danger-button" disabled={saving} onClick={() => void rejectRegistration(selectedRegistration)}>Reject</button>
            {selectedRegistration.status === 'captured' && <button className="a-button a-button--dark" disabled={saving} onClick={() => void approveRegistration(selectedRegistration)}><Check size={16} /> Confirm registration</button>}
          </div>
        </section>
      </div>}

      {notice && <div className="a-toast"><CircleCheck size={18} />{notice}<button aria-label="Dismiss notification" onClick={() => setNotice('')}><X size={15} /></button></div>}
    </div>
  );
};

function ScanTable({ rows, onSelect }: { rows: Scan[]; onSelect: (scan: Scan) => void }) {
  return <div className="a-tablewrap">
    <table className="a-table">
      <thead><tr><th>STUDENT / CARD</th><th>TIME</th><th>RESULT</th><th /></tr></thead>
      <tbody>{rows.map((row) => <tr key={row.eventId} onClick={() => onSelect(row)} onKeyDown={(event) => event.key === 'Enter' && onSelect(row)} tabIndex={0}>
        <td><div className="a-person"><span className={'a-avatar a-avatar--' + row.tone}>{row.initials}</span><span><strong>{row.name}</strong><small>{row.studentId}</small></span></div></td>
        <td><span className="a-time">{row.time}</span></td><td><StatusBadge status={row.result} /></td><td><ChevronRight size={16} className="a-row-chevron" /></td>
      </tr>)}</tbody>
    </table>
    {rows.length === 0 && <div className="a-empty">No matching verification events. Try a different filter.</div>}
  </div>;
}
