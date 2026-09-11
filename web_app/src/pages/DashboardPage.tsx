import React, { useEffect, useState } from 'react';
import {
  Activity,
  AlertCircle,
  CheckCircle2,
  FileText,
  Lightbulb,
  PlusCircle,
  Radio,
  RefreshCw,
  Search,
  ShieldAlert,
  ShieldCheck,
  Users,
  X,
  Zap,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useLanguage } from '../context/LanguageContext';
import { reportsApi, sightingsApi } from '../services/api';
import { sseService, SightingAlertEvent } from '../services/sseService';
import { Sighting } from '../types/sighting';
import { SightingCard } from '../components/reports/SightingCard';
import { LoadingSpinner } from '../components/common/LoadingSpinner';

export const DashboardPage: React.FC = () => {
  const { t } = useLanguage();
  const navigate = useNavigate();
  const [stats, setStats] = useState({ active: 0, matches: 0, total: 0, found: 0 });
  const [sightings, setSightings] = useState<Sighting[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [liveAlert, setLiveAlert] = useState<SightingAlertEvent | null>(null);

  const loadDashboardData = async (silent = false) => {
    if (!silent) setIsLoading(true);
    else setIsRefreshing(true);

    try {
      const [allCasesRes, sightingsRes] = await Promise.all([
        reportsApi.getAllReports(undefined, 1, 100).catch(() => ({ items: [], total: 0, page: 1, per_page: 100 })),
        sightingsApi.listRecent(20).catch(() => []),
      ]);
      const cases = allCasesRes.items || [];
      setStats({
        active: cases.filter((item) => item.status === 'ACTIVE').length,
        matches: sightingsRes.length,
        total: allCasesRes.total || cases.length,
        found: cases.filter((item) => item.status === 'FOUND').length,
      });
      setSightings(sightingsRes);
    } catch (error) {
      console.error('Failed to load dashboard metrics', error);
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    void loadDashboardData();

    const handleLiveSighting = (event: SightingAlertEvent) => {
      // 1. Instantly increment matches counter
      setStats((prev) => ({ ...prev, matches: prev.matches + 1 }));

      // 2. Prepend live sighting to the top of the feed
      const newSighting: Sighting = {
        id: event.sighting_id,
        person_id: event.person_id || '',
        person_name: event.person_name || '',
        camera_id: event.camera_id || '',
        agent_id: '',
        similarity_score: Number(event.similarity || 0),
        confidence_level: event.confidence_level || 'CONFIRMED',
        num_frames_matched: event.num_frames_matched ?? 3,
        camera_location: event.camera_location || 'CCTV Surveillance Camera',
        latitude: event.latitude,
        longitude: event.longitude,
        detected_at: event.detected_at || new Date().toISOString(),
        face_crop_path: event.face_crop_path || '',
        full_frame_path: event.full_frame_path || '',
        video_clip_path: event.video_clip_path,
        status: 'PENDING',
        created_at: new Date().toISOString(),
      };

      setSightings((prev) => [newSighting, ...prev.filter((s) => s.id !== newSighting.id)]);
      setLiveAlert(event);

      // 3. Background refresh to keep case stats synchronized
      void loadDashboardData(true);
    };

    const unsubscribe = sseService.subscribe(handleLiveSighting);
    sseService.connect();

    const interval = setInterval(() => void loadDashboardData(true), 15000);
    return () => {
      unsubscribe();
      clearInterval(interval);
    };
  }, []);

  const metrics = [
    { label: t.stats.activeSearches, value: stats.active, hint: t.stats.monitoredFeeds, icon: Search, tone: 'accent' },
    { label: t.stats.cctvMatches, value: stats.matches, hint: t.stats.biometricLogged, icon: Zap, tone: 'success' },
    { label: t.stats.totalCases, value: stats.total, hint: t.stats.registeredCases, icon: Users, tone: 'warning' },
    { label: t.stats.personsFound, value: stats.found, hint: t.stats.resolvedCases, icon: CheckCircle2, tone: 'purple' },
  ];

  return (
    <div className="main-content">
      {/* Live Match Real-Time Banner */}
      {liveAlert && (
        <div className="glass-panel live-match-banner">
          <div className="live-match-banner__info">
            <div className="live-match-banner__icon">
              <ShieldAlert size={22} className="pulse-icon" aria-hidden="true" />
            </div>
            <div>
              <div className="live-match-banner__title-row">
                <span className="live-pill live-pill--urgent">LIVE BIOMETRIC ALERT</span>
                <strong>{liveAlert.title || 'Biometric Match Detected'}</strong>
              </div>
              <span className="live-match-banner__body">
                {liveAlert.body || `Possible biometric match spotted on camera ${liveAlert.camera_location || 'CCTV'}`}
              </span>
            </div>
          </div>
          <div className="live-match-banner__actions">
            <button
              type="button"
              onClick={() => navigate(`/sightings/${liveAlert.sighting_id}`)}
              className="btn btn-primary btn-sm"
            >
              <AlertCircle size={15} aria-hidden="true" />
              <span>Inspect Evidence</span>
            </button>
            <button
              type="button"
              onClick={() => setLiveAlert(null)}
              className="btn btn-secondary btn-sm"
              aria-label="Dismiss alert"
            >
              <X size={15} aria-hidden="true" />
            </button>
          </div>
        </div>
      )}

      {/* Top Level System Metrics */}
      <section className="stats-grid" aria-label="System metrics">
        {metrics.map(({ label, value, hint, icon: Icon, tone }) => (
          <div className={`glass-panel dashboard-metric dashboard-metric--${tone}`} key={label}>
            <div className="dashboard-metric__header">
              <span className="dashboard-metric__label">{label}</span>
              <span className="dashboard-metric__icon"><Icon size={18} aria-hidden="true" /></span>
            </div>
            <strong className="dashboard-metric__value">{value}</strong>
            <span className="dashboard-metric__hint">{hint}</span>
          </div>
        ))}
      </section>

      {/* Main Command Center Grid */}
      <div className="dashboard-grid">
        <section>
          <div className="section-header">
            <div>
              <div className="section-title-wrap">
                <h2 className="section-title">
                  <Radio size={20} className="section-title__icon" aria-hidden="true" />
                  <span>{t.dashboard.liveSightingsTitle}</span>
                </h2>
                <span className="live-pill">
                  <span className="pulse-dot" /> LIVE STREAM
                </span>
              </div>
              <p className="section-subtitle">{t.dashboard.liveSightingsSub}</p>
            </div>
            <button
              type="button"
              onClick={() => void loadDashboardData(true)}
              className="btn btn-secondary btn-sm"
              disabled={isRefreshing}
            >
              <RefreshCw size={14} className={isRefreshing ? 'spin' : ''} aria-hidden="true" />
              <span>{t.dashboard.refreshFeed}</span>
            </button>
          </div>

          {isLoading ? (
            <LoadingSpinner text="Scanning CCTV Sighting Streams..." />
          ) : sightings.length === 0 ? (
            <div className="glass-panel empty-state">
              <div className="empty-state__icon-wrap">
                <ShieldCheck size={42} strokeWidth={1.6} aria-hidden="true" />
              </div>
              <h3>No Active Sighting Alerts</h3>
              <p>{t.dashboard.noSightings}</p>
            </div>
          ) : (
            <div className="stack-list">
              {sightings.map((sighting) => (
                <SightingCard
                  key={sighting.id}
                  sighting={sighting}
                  personName={sighting.person_name || undefined}
                />
              ))}
            </div>
          )}
        </section>

        <aside className="dashboard-aside">
          {/* Quick Actions Panel */}
          <div className="glass-panel quick-actions">
            <div className="panel-header">
              <Zap size={16} className="panel-header__icon" aria-hidden="true" />
              <h3>{t.dashboard.quickActions}</h3>
            </div>
            <div className="quick-actions__list">
              <button
                type="button"
                onClick={() => navigate('/reports/new')}
                className="btn btn-primary quick-actions__button"
              >
                <PlusCircle size={16} aria-hidden="true" />
                <span>{t.dashboard.reportPersonBtn}</span>
              </button>
              <button
                type="button"
                onClick={() => navigate('/reports')}
                className="btn btn-secondary quick-actions__button"
              >
                <FileText size={16} aria-hidden="true" />
                <span>{t.dashboard.viewMyReportsBtn}</span>
              </button>
            </div>
          </div>

          {/* System Telemetry Specs */}
          <div className="glass-panel telemetry-card">
            <div className="panel-header">
              <Activity size={16} className="panel-header__icon" aria-hidden="true" />
              <h3>Surveillance Engine</h3>
            </div>
            <div className="telemetry-list">
              <div className="telemetry-item">
                <span>Facial Recognition</span>
                <strong>ArcFace 512-D</strong>
              </div>
              <div className="telemetry-item">
                <span>Object Tracking</span>
                <strong>ByteTrack Multi-Cam</strong>
              </div>
              <div className="telemetry-item">
                <span>Vector Search</span>
                <strong>FAISS Cosine Index</strong>
              </div>
              <div className="telemetry-item">
                <span>Edge Agent Sync</span>
                <span className="telemetry-status"><span className="status-dot" /> Real-Time</span>
              </div>
            </div>
          </div>

          {/* Accuracy Advisory */}
          <div className="glass-panel dashboard-tip">
            <div className="dashboard-tip__title">
              <Lightbulb size={16} aria-hidden="true" />
              <h4>{t.dashboard.proTipTitle}</h4>
            </div>
            <p>{t.dashboard.proTipBody}</p>
          </div>
        </aside>
      </div>
    </div>
  );
};
