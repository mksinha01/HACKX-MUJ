import React, { useEffect, useState } from 'react';
import { ArrowLeft, Calendar, Camera, CheckCircle, Map, MapPin, Phone, Plus, Shield, User, XCircle } from 'lucide-react';
import { useNavigate, useParams } from 'react-router-dom';
import { useLanguage } from '../context/LanguageContext';
import { useToast } from '../context/ToastContext';
import { reportsApi } from '../services/api';
import { MissingPerson, PhotoItem } from '../types/report';
import { Sighting } from '../types/sighting';
import { StatusBadge } from '../components/common/StatusBadge';
import { SightingCard } from '../components/reports/SightingCard';
import { ConfirmModal } from '../components/common/ConfirmModal';
import { LoadingSpinner } from '../components/common/LoadingSpinner';
import { APP_CONSTANTS } from '../config/constants';
import { compressImage } from '../services/imageService';
import { FIRStatusBadge } from '../components/common/FIRStatusBadge';

export const ReportDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { t } = useLanguage();
  const { addToast } = useToast();
  const [person, setPerson] = useState<MissingPerson | null>(null);
  const [sightings, setSightings] = useState<Sighting[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedPhotoIndex, setSelectedPhotoIndex] = useState(0);
  const [isMarkFoundOpen, setIsMarkFoundOpen] = useState(false);
  const [isCloseCaseOpen, setIsCloseCaseOpen] = useState(false);
  const [isAddPhotoOpen, setIsAddPhotoOpen] = useState(false);
  const [isProcessingAction, setIsProcessingAction] = useState(false);
  const [newPhotoFile, setNewPhotoFile] = useState<File | null>(null);
  const [newPhotoPreview, setNewPhotoPreview] = useState<string | null>(null);

  const loadData = async () => {
    if (!id) return;
    setIsLoading(true);
    try {
      const [personResponse, sightingsResponse] = await Promise.all([reportsApi.getById(id), reportsApi.getSightings(id).catch(() => [])]);
      setPerson(personResponse);
      setSightings(sightingsResponse);
    } catch (error) {
      console.error('Failed to load report details', error);
      addToast('Could not load report details', 'error');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => { void loadData(); }, [id]);

  const handleMarkFound = async () => {
    if (!person) return;
    setIsProcessingAction(true);
    try {
      await reportsApi.update(person.id, { status: 'FOUND' });
      addToast('Case status successfully updated to FOUND!', 'success');
      setIsMarkFoundOpen(false);
      void loadData();
    } catch { addToast('Failed to update case status', 'error'); }
    finally { setIsProcessingAction(false); }
  };

  const handleCloseCase = async () => {
    if (!person) return;
    setIsProcessingAction(true);
    try {
      await reportsApi.close(person.id);
      addToast('Report closed and facial embeddings deactivated on edge network.', 'info');
      setIsCloseCaseOpen(false);
      navigate('/reports');
    } catch { addToast('Failed to close report', 'error'); }
    finally { setIsProcessingAction(false); }
  };

  const handleUploadPhoto = async () => {
    if (!person || !newPhotoFile) return;
    setIsProcessingAction(true);
    try {
      const compressed = await compressImage(newPhotoFile);
      const formData = new FormData();
      formData.append('file', compressed.file);
      formData.append('is_primary', 'false');
      await reportsApi.uploadPhoto(person.id, formData);
      addToast('Additional photo uploaded and processed by ArcFace!', 'success');
      setIsAddPhotoOpen(false);
      setNewPhotoFile(null);
      setNewPhotoPreview(null);
      void loadData();
    } catch { addToast('Failed to process photo upload', 'error'); }
    finally { setIsProcessingAction(false); }
  };

  if (isLoading) return <LoadingSpinner text="Retrieving case details & biometric models..." />;
  if (!person) return <div className="main-content empty-state"><h2>Report Not Found</h2><button type="button" onClick={() => navigate('/reports')} className="btn btn-primary">Back to Reports</button></div>;

  const photos: PhotoItem[] = person.photos || [];
  const activePhoto = photos[selectedPhotoIndex];
  const resolveUrl = (path?: string | null) => path ? (path.startsWith('http') ? path : `${APP_CONSTANTS.API_BASE_URL}${path}`) : '';
  const activePhotoUrl = resolveUrl(activePhoto?.original_path) || person.primary_photo_url || '';
  const activeFaceCropUrl = resolveUrl(activePhoto?.face_crop_path);

  return (
    <div className="main-content">
      <div className="page-toolbar">
        <button type="button" onClick={() => navigate('/reports')} className="btn btn-secondary btn-sm"><ArrowLeft size={16} aria-hidden="true" /> {t.reports.title}</button>
        <div className="page-actions">
          <button type="button" onClick={() => navigate(`/reports/${person.id}/timeline`)} className="btn btn-secondary btn-sm"><Map size={16} aria-hidden="true" /> {t.reports.timelineBtn}</button>
          <button type="button" onClick={() => setIsAddPhotoOpen(true)} className="btn btn-secondary btn-sm"><Plus size={16} aria-hidden="true" /> {t.reports.addPhotoBtn}</button>
          {person.status !== 'FOUND' && <button type="button" onClick={() => setIsMarkFoundOpen(true)} className="btn btn-success btn-sm"><CheckCircle size={16} aria-hidden="true" /> {t.reports.markFoundBtn}</button>}
          {person.status !== 'CLOSED' && <button type="button" onClick={() => setIsCloseCaseOpen(true)} className="btn btn-danger btn-sm"><XCircle size={16} aria-hidden="true" /> {t.reports.closeCaseBtn}</button>}
        </div>
      </div>

      <div className="glass-panel report-detail-layout report-detail-card">
        <div className="report-detail__media-column">
          <div className="report-detail__hero-photo">
            {activePhotoUrl ? <img src={activePhotoUrl} alt={person.full_name} /> : <User size={64} aria-hidden="true" />}
            <span className="report-detail__status"><StatusBadge status={person.status} /></span>
            {activeFaceCropUrl && <div className="report-detail__face-inset"><img src={activeFaceCropUrl} alt="AI face crop" /><span><strong>ArcFace 512-D</strong><small>{person.status === 'ACTIVE' ? 'Face vector active' : 'Search closed (Vector inactive)'}</small></span></div>}
          </div>
          {photos.length > 1 && <div className="thumbnail-strip">{photos.map((photo, index) => <button key={photo.id || index} type="button" className={index === selectedPhotoIndex ? 'is-selected' : ''} onClick={() => setSelectedPhotoIndex(index)}><img src={resolveUrl(photo.original_path)} alt={`${person.full_name} photo ${index + 1}`} /></button>)}</div>}
        </div>

        <div className="report-detail__content">
          <div className="report-detail__heading"><h1>{person.full_name}</h1><p>{t.reports.ageGender.replace('{age}', person.age.toString()).replace('{gender}', person.gender)}</p></div>
          <div className="report-meta-grid">
            <div><span>{t.reports.lastSeen}</span><strong><MapPin size={15} aria-hidden="true" /> {person.last_seen_location}</strong></div>
            <div><span>Date & Time</span><strong><Calendar size={15} aria-hidden="true" /> {new Date(person.last_seen_time).toLocaleString()}</strong></div>
            {person.height_cm && <div><span>{t.reports.heightLabel}</span><strong>{person.height_cm} cm</strong></div>}
            <div><span>{t.reports.contactLabel}</span><strong><Phone size={15} aria-hidden="true" /> {person.contact_info}</strong></div>
          </div>
          {person.description && <div className="detail-description"><h4>{t.reports.identifyingFeatures}</h4><p>{person.description}</p></div>}

          {/* ── FIR Details Section ── */}
          {person.fir_number && (
            <div className="detail-description">
              <h4><Shield size={16} aria-hidden="true" /> FIR Verification</h4>
              <FIRStatusBadge status={person.fir_status} rejectionReason={person.fir_rejection_reason} />
              <div className="fir-details">
                <div className="fir-detail-item">
                  <span className="fir-detail-item__label">FIR Number</span>
                  <span className="fir-detail-item__value">{person.fir_number}</span>
                </div>
                <div className="fir-detail-item">
                  <span className="fir-detail-item__label">Police Station</span>
                  <span className="fir-detail-item__value">{person.fir_police_station || '—'}</span>
                </div>
                {person.fir_date && (
                  <div className="fir-detail-item">
                    <span className="fir-detail-item__label">FIR Date</span>
                    <span className="fir-detail-item__value">{new Date(person.fir_date).toLocaleDateString()}</span>
                  </div>
                )}
                {person.fir_verified_at && (
                  <div className="fir-detail-item">
                    <span className="fir-detail-item__label">Verified At</span>
                    <span className="fir-detail-item__value">{new Date(person.fir_verified_at).toLocaleString()}</span>
                  </div>
                )}
              </div>
              {person.fir_status === 'REJECTED' && person.fir_rejection_reason && (
                <div className="fir-rejection-banner">
                  <XCircle size={18} />
                  <div>
                    <strong>FIR Rejected</strong>
                    <span>{person.fir_rejection_reason}. Please update your FIR details and resubmit.</span>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      <section className="detail-section">
        <div className="section-header"><div><h3 className="section-title"><Camera size={20} aria-hidden="true" /> {t.reports.cctvSightingsTitle} ({sightings.length})</h3><p className="section-subtitle">Facial matches and temporal detections captured across monitored cameras.</p></div>{sightings.length > 0 && <button type="button" onClick={() => navigate(`/reports/${person.id}/timeline`)} className="btn btn-primary btn-sm"><Map size={16} aria-hidden="true" /> {t.reports.timelineBtn}</button>}</div>
        {sightings.length === 0 ? <div className="glass-panel empty-state"><Camera size={40} aria-hidden="true" /><h3>{t.reports.noSightingsYet}</h3><p>When Edge Agents detect this individual, verified photographic matches and GPS breadcrumbs will populate here.</p></div> : <div className="stack-list">{sightings.map((sighting) => <SightingCard key={sighting.id} sighting={sighting} personName={person.full_name} />)}</div>}
      </section>

      <ConfirmModal isOpen={isMarkFoundOpen} title={t.reports.markFoundBtn} message="Are you sure you want to mark this person as safely FOUND? Case status will transition and active edge CCTV alerts will be resolved." confirmText="Yes, Mark as Found" isLoading={isProcessingAction} onConfirm={() => void handleMarkFound()} onCancel={() => setIsMarkFoundOpen(false)} />
      <ConfirmModal isOpen={isCloseCaseOpen} title={t.reports.closeCaseBtn} message="Are you sure you want to close this case? All active ArcFace embeddings will be deactivated and tombstones synced to CCTV Edge Agents." confirmText="Yes, Close Report" isDanger isLoading={isProcessingAction} onConfirm={() => void handleCloseCase()} onCancel={() => setIsCloseCaseOpen(false)} />
      <ConfirmModal isOpen={isAddPhotoOpen} title={t.reports.addPhotoBtn} message="Upload an additional face photo to increase recognition accuracy across angles and lighting conditions." confirmText="Upload & Extract Face Vector" isLoading={isProcessingAction} onConfirm={() => void handleUploadPhoto()} onCancel={() => { setIsAddPhotoOpen(false); setNewPhotoFile(null); setNewPhotoPreview(null); }}>
        <div className="modal-upload"><input type="file" accept="image/*" onChange={(event) => { const file = event.target.files?.[0]; if (file) { setNewPhotoFile(file); setNewPhotoPreview(URL.createObjectURL(file)); } }} />{newPhotoPreview && <img src={newPhotoPreview} alt="New upload preview" />}</div>
      </ConfirmModal>
    </div>
  );
};
