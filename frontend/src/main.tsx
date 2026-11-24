import React from 'react';
import {createRoot} from 'react-dom/client';
import {AttendanceControlCenter} from './components/generated/AttendanceControlCenter';
import './style.css';
createRoot(document.getElementById('root')!).render(<React.StrictMode><AttendanceControlCenter/></React.StrictMode>);
