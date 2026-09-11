import React, { useEffect, useState } from 'react';
import { AlertCircle, ArrowLeft, Clock, RefreshCw } from 'lucide-react';
import { useNavigate, useParams } from 'react-router-dom';
import { useLanguage } from '../context/LanguageContext';
import { reportsApi } from '../services/api';
import { PersonTimeline, TimelineBreadcrumb } from '../types/sighting';
import { TimelineMap } from '../components/reports/TimelineMap';
import { LoadingSpinner } from '../components/common/LoadingSpinner';

export const TimelinePage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { t } = useLanguage();
  const [timeline, setTimeline] = useState<PersonTimeline | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const fetchTimeline = async (silent = false) => {
    if (!id) return;
    if (!silent) setIsLoading(true); else setIsRefreshing(true);
    try { setTimeline(await reportsApi.getTimeline(id)); }
    catch (error) { console.error('Failed to load person timeline', error); }
    finally { setIsLoading(false); setIsRefreshing(false); }
  };

  useEffect(() => { void fetchTimeline(); }, [id]);
  if (isLoading) return <LoadingSpinner text="Mapping GPS movement breadcrumbs..." />;

  const entries: TimelineBreadcrumb[] = timeline?.entries || [];
  return (
    <div className="main-content">
      <div className="page-toolbar"><button type="button" onClick={() => navigate(-1)} className="btn btn-secondary btn-sm"><ArrowLeft size={16} aria-hidden="true" /> Back</button><button type="button" onClick={() => void fetchTimeline(true)} className="btn btn-secondary btn-sm" disabled={isRefreshing}><RefreshCw size={14} className={isRefreshing ? 'spin' : ''} aria-hidden="true" /> Refresh Map</button></div>
      <div className="section-header"><div><h2 className="section-title"><span aria-hidden="true">🗺️</span> {t.timeline.title}</h2><p className="section-subtitle">{timeline?.person_name ? `Tracking movement path for: ${timeline.person_name}` : t.timeline.subtitle}</p></div>{timeline?.last_seen_camera && <div className="last-seen-pill">🚨 {t.timeline.lastSeenHighlight}: {timeline.last_seen_camera}</div>}</div>
      <div className="timeline-layout"><TimelineMap breadcrumbs={entries} height="560px" /><div className="glass-panel timeline-stops"><h3 className="subsection-title">📍 {t.timeline.stopsCount.replace('{count}', entries.length.toString())}</h3>{entries.length === 0 ? <div className="timeline-empty"><AlertCircle size={31} aria-hidden="true" /><span>{t.timeline.noStops}</span></div> : <div className="timeline-stop-list">{entries.map((entry, index) => { const isLastSeen = index === entries.length - 1; return <button type="button" key={entry.sighting_id || index} className={`timeline-stop${isLastSeen ? ' is-latest' : ''}`} onClick={() => navigate(`/sightings/${entry.sighting_id}`)}><span className="timeline-stop__top"><strong>{isLastSeen ? `Stop #${index + 1} (Latest)` : `Stop #${index + 1}`}</strong><b>{Math.round(entry.similarity_score * 100)}% Match</b></span><span className="timeline-stop__camera">{entry.camera_name}</span><span className="timeline-stop__time"><Clock size={12} aria-hidden="true" /> {new Date(entry.detected_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} <span>•</span> {new Date(entry.detected_at).toLocaleDateString()}</span></button>; })}</div>}</div></div>
    </div>
  );
};
