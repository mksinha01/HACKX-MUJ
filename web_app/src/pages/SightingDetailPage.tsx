import React, { useEffect, useState } from 'react';
import { ArrowLeft, CheckCircle, Clock, MapPin, Maximize2, ShieldCheck, X, XCircle } from 'lucide-react';
import { useNavigate, useParams } from 'react-router-dom';
import { useLanguage } from '../context/LanguageContext';
import { useToast } from '../context/ToastContext';
import { sightingsApi, reportsApi } from '../services/api';
import { Sighting } from '../types/sighting';
import { MissingPerson } from '../types/report';
import { StatusBadge } from '../components/common/StatusBadge';
import { SimilarityGauge } from '../components/common/SimilarityGauge';
import { LoadingSpinner } from '../components/common/LoadingSpinner';
import { APP_CONSTANTS } from '../config/constants';

export const SightingDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { t } = useLanguage();
  const { addToast } = useToast();
  const [sighting, setSighting] = useState<Sighting | null>(null);
  const [person, setPerson] = useState<MissingPerson | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [reviewNotes, setReviewNotes] = useState('');
  const [isSubmittingReview, setIsSubmittingReview] = useState(false);
  const [isZoomOpen, setIsZoomOpen] = useState(false);

  const loadSightingData = async () => {
    if (!id) return;
    setIsLoading(true);
    try {
      const currentSighting = await sightingsApi.getById(id);
      setSighting(currentSighting);
      if (currentSighting.person_id) setPerson(await reportsApi.getById(currentSighting.person_id).catch(() => null));
    } catch (error) {
      console.error('Failed to load sighting details', error);
      addToast('Could not load sighting evidence', 'error');
    } finally { setIsLoading(false); }
  };

  useEffect(() => { void loadSightingData(); }, [id]);

  const handleReview = async (action: 'confirm' | 'reject') => {
    if (!sighting) return;
    setIsSubmittingReview(true);
    try {
      const updated = action === 'confirm'
        ? await sightingsApi.confirm(sighting.id, reviewNotes.trim() || undefined)
        : await sightingsApi.reject(sighting.id, reviewNotes.trim() || undefined);
      setSighting(updated);
      if (action === 'confirm' && person) {
        setPerson({ ...person, status: 'FOUND' });
        if (updated.person_id) {
          void reportsApi.getById(updated.person_id).then((fresh) => fresh && setPerson(fresh)).catch(() => { });
        }
      }
      addToast(
        action === 'confirm'
          ? 'Verified Match confirmed! Active search closed (Person Found).'
          : 'Sighting flagged and rejected as false positive.',
        action === 'confirm' ? 'success' : 'info'
      );
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string | Array<{ msg: string }> } } };
      let msg = action === 'confirm' ? 'Failed to confirm sighting match' : 'Failed to reject sighting match';
      if (axiosErr?.response?.data?.detail) {
        const detail = axiosErr.response.data.detail;
        msg = typeof detail === 'string' ? detail : (Array.isArray(detail) ? detail.map((d) => d.msg).join(', ') : msg);
      }
      addToast(msg, 'error');
    } finally {
      setIsSubmittingReview(false);
    }
  };

  if (isLoading) return <LoadingSpinner text="Retrieving forensic CCTV media..." />;
  if (!sighting) return <div className="main-content empty-state"><h2>Sighting Not Found</h2><button type="button" onClick={() => navigate('/dashboard')} className="btn btn-primary">Back to Dashboard</button></div>;

  const resolveUrl = (path: string) => path.startsWith('http') ? path : `${APP_CONSTANTS.API_BASE_URL}${path}`;
  const faceCropUrl = resolveUrl(sighting.face_crop_path);
  const fullFrameUrl = resolveUrl(sighting.full_frame_path);
  const refPhoto = person?.photos?.find((photo) => photo.face_crop_path) || person?.photos?.[0];
  const refCropUrl = refPhoto?.face_crop_path ? resolveUrl(refPhoto.face_crop_path) : person?.primary_photo_url || null;

  return (
    <div className="main-content">
      <div className="page-toolbar"><button type="button" onClick={() => navigate(-1)} className="btn btn-secondary btn-sm"><ArrowLeft size={16} aria-hidden="true" /> Back</button>{person && <button type="button" onClick={() => navigate(`/reports/${person.id}`)} className="btn btn-secondary btn-sm">View Full Case: {person.full_name} ({person.status})</button>}</div>
      <div className="section-header"><div><h2 className="section-title"><ShieldCheck size={20} aria-hidden="true" /> {t.sighting.title}</h2><p className="section-subtitle">{t.sighting.subtitle}</p></div><StatusBadge status={sighting.status} /></div>

      <div className="glass-panel comparison-card"><h3 className="subsection-title">🔬 {t.sighting.faceComparison}</h3><div className="comparison-grid">
        <div className="comparison-side"><div className="comparison-image comparison-image--accent"><img src={faceCropUrl} alt="CCTV sighting face" /></div><strong>{t.sighting.sightingCrop}</strong><span>SCRFD + ByteTrack Cropped</span></div>
        <div className="comparison-gauge"><SimilarityGauge score={sighting.similarity_score} size={130} strokeWidth={12} /><span>ArcFace 512-D Cosine Sim</span></div>
        <div className="comparison-side"><div className="comparison-image comparison-image--success">{refCropUrl ? <img src={refCropUrl} alt="Registered reference face" /> : <span>No reference face</span>}</div><strong>{t.sighting.referenceCrop}</strong><span>{person?.full_name || 'Case Subject'}</span></div>
      </div></div>

      <div className="scene-grid"><div className="glass-panel scene-card"><div className="scene-card__header"><h3 className="subsection-title">{t.sighting.fullSceneCapture}</h3><button type="button" onClick={() => setIsZoomOpen(true)} className="btn btn-secondary btn-sm"><Maximize2 size={14} aria-hidden="true" /> Fullscreen</button></div><button type="button" className="scene-frame" onClick={() => setIsZoomOpen(true)} aria-label="Open fullscreen CCTV scene"><img src={fullFrameUrl} alt="Full CCTV scene capture" /></button></div>
        <div className="glass-panel camera-meta"><h3 className="subsection-title">📹 {t.sighting.cameraDetails}</h3><div><span>{t.sighting.location}</span><strong><MapPin size={15} aria-hidden="true" /> {sighting.camera_location || 'CCTV Surveillance Camera'}</strong></div><div><span>{t.sighting.detectedAt}</span><strong><Clock size={15} aria-hidden="true" /> {new Date(sighting.detected_at).toLocaleString()}</strong></div>{sighting.latitude && sighting.longitude && <div><span>{t.sighting.coordinates}</span><strong className="monospace">{sighting.latitude.toFixed(5)}, {sighting.longitude.toFixed(5)}</strong></div>}{sighting.num_frames_matched && <div><span>{t.sighting.framesMatched}</span><strong className="warning-text">{sighting.num_frames_matched} consecutive match frames</strong></div>}</div>
      </div>

      <div className="glass-panel review-card"><h3 className="subsection-title">⚖️ {t.sighting.reviewDecision}</h3>{sighting.status !== 'PENDING' ? <div className={`review-result review-result--${sighting.status === 'CONFIRMED' ? 'success' : 'muted'}`}><strong>{t.sighting.alreadyReviewed.replace('{status}', sighting.status)}</strong>{sighting.status === 'CONFIRMED' && <div style={{ marginTop: '0.5rem', display: 'flex', alignItems: 'center', gap: '0.4rem', color: '#10b981', fontWeight: 600 }}><CheckCircle size={16} aria-hidden="true" /><span>Active search closed • Individual marked as FOUND</span></div>}{sighting.review_notes && <p style={{ marginTop: '0.5rem' }}><strong>Review Notes:</strong> {sighting.review_notes}</p>}</div> : <><div className="form-group"><label className="form-label" htmlFor="review-notes">{t.sighting.reviewNotesLabel}</label><textarea id="review-notes" className="form-control" rows={2} placeholder={t.sighting.reviewNotesPlaceholder} value={reviewNotes} onChange={(event) => setReviewNotes(event.target.value)} /></div><div className="review-actions"><button type="button" onClick={() => void handleReview('confirm')} disabled={isSubmittingReview} className="btn btn-success"><CheckCircle size={18} aria-hidden="true" /> {isSubmittingReview ? 'Submitting...' : t.sighting.confirmMatchBtn}</button><button type="button" onClick={() => void handleReview('reject')} disabled={isSubmittingReview} className="btn btn-danger"><XCircle size={18} aria-hidden="true" /> {isSubmittingReview ? 'Submitting...' : t.sighting.rejectMatchBtn}</button></div></>}</div>

      {isZoomOpen && <div className="modal-overlay" onClick={() => setIsZoomOpen(false)}><div className="zoom-dialog" onClick={(event) => event.stopPropagation()}><img src={fullFrameUrl} alt="Fullscreen CCTV scene" /><button type="button" className="modal-close zoom-dialog__close" onClick={() => setIsZoomOpen(false)} aria-label="Close fullscreen image"><X size={18} aria-hidden="true" /></button></div></div>}
    </div>
  );
};
