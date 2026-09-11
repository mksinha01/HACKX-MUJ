import React, { useEffect } from 'react';
import { Outlet } from 'react-router-dom';
import { Navbar } from './Navbar';
import { Footer } from './Footer';
import { useToast } from '../../context/ToastContext';
import { sseService, SightingAlertEvent } from '../../services/sseService';

export const AuthenticatedLayout: React.FC = () => {
  const { addToast } = useToast();

  useEffect(() => {
    const handleSightingAlert = (event: SightingAlertEvent) => {
      const simPct = Math.round(Number(event.similarity || 0) * 100);
      const name = event.person_name || 'Missing Person';
      const loc = event.camera_location || 'CCTV Camera';

      addToast(
        `🚨 Biometric Match (${simPct}%): ${name} spotted on ${loc}. Tap Alerts or Dashboard to inspect evidence.`,
        'warning',
        event.title || 'Possible Face Match Detected'
      );
    };

    const unsubscribe = sseService.subscribe(handleSightingAlert);
    sseService.connect();

    return () => unsubscribe();
  }, [addToast]);

  return (
    <div className="app-shell">
      <Navbar />
      <div className="app-surface">
        <main className="app-main">
          <Outlet />
        </main>
        <Footer />
      </div>
    </div>
  );
};
