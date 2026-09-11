import React, { useState } from 'react';
import { AlertCircle, ArrowLeft, Send, Shield } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useLanguage } from '../context/LanguageContext';
import { useToast } from '../context/ToastContext';
import { reportsApi } from '../services/api';
import { ImageDropzone } from '../components/forms/ImageDropzone';
import { FormField } from '../components/forms/FormField';
import { CompressedImage } from '../services/imageService';

export const NewReportPage: React.FC = () => {
  const { t } = useLanguage();
  const { addToast } = useToast();
  const navigate = useNavigate();
  const [photos, setPhotos] = useState<CompressedImage[]>([]);
  const [fullName, setFullName] = useState('');
  const [age, setAge] = useState<number | ''>('');
  const [gender, setGender] = useState('Male');
  const [heightCm, setHeightCm] = useState<number | ''>(170);
  const [location, setLocation] = useState('');
  const [lastSeenTime, setLastSeenTime] = useState(() => {
    const now = new Date();
    now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
    return now.toISOString().slice(0, 16);
  });
  const [contact, setContact] = useState('');
  const [description, setDescription] = useState('');
  // FIR fields
  const [firNumber, setFirNumber] = useState('');
  const [firPoliceStation, setFirPoliceStation] = useState('');
  const [firDate, setFirDate] = useState('');
  const [firDocument, setFirDocument] = useState<File | null>(null);
  
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFirDocChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const allowed = ['.pdf', '.jpg', '.jpeg', '.png'];
      const ext = '.' + file.name.split('.').pop()?.toLowerCase();
      if (!allowed.includes(ext)) {
        setError('FIR document must be PDF, JPEG, or PNG.');
        return;
      }
      if (file.size > 20 * 1024 * 1024) {
        setError('FIR document must be under 20 MB.');
        return;
      }
      setFirDocument(file);
      setError(null);
    }
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (photos.length === 0) { setError('Please attach at least one clear face photo of the missing person.'); return; }
    if (!fullName.trim() || !age || !location.trim() || !contact.trim()) { setError('Please fill in all mandatory fields marked with an asterisk (*).'); return; }
    if (!firNumber.trim()) { setError('FIR Number is required. Please provide your police FIR number.'); return; }
    if (!firPoliceStation.trim()) { setError('Police Station name is required.'); return; }

    setError(null);
    setIsSubmitting(true);
    try {
      const formData = new FormData();
      formData.append('report_data', JSON.stringify({
        full_name: fullName.trim(),
        age: Number(age),
        gender,
        height_cm: heightCm ? Number(heightCm) : undefined,
        description: description.trim() || undefined,
        last_seen_location: location.trim(),
        last_seen_time: new Date(lastSeenTime).toISOString(),
        contact_info: contact.trim(),
        fir_number: firNumber.trim(),
        fir_police_station: firPoliceStation.trim(),
        fir_date: firDate ? new Date(firDate).toISOString() : undefined,
      }));
      photos.forEach((item) => formData.append('photos', item.file));
      if (firDocument) {
        formData.append('fir_document', firDocument);
      }

      const created = await reportsApi.createAtomic(formData);
      if (created.status === 'REJECTED_NO_FACE') {
        addToast('Report submitted, but no clear face was detected in photos. Please upload a frontal photo.', 'warning');
      } else if (created.status === 'FIR_REJECTED') {
        addToast('FIR number format is invalid. Please check and resubmit with a valid FIR number.', 'error');
      } else if (created.status === 'PENDING_FIR_REVIEW') {
        addToast('Report submitted! FIR is pending verification by admin. You will be notified once approved.', 'info');
      } else {
        addToast('Missing person case registered! FIR verified, AI embeddings synced to CCTV network.', 'success');
      }
      navigate(`/reports/${created.id}`);
    } catch (submitError: unknown) {
      let msg = 'Failed to submit report. Please check your connection.';
      if (submitError instanceof Error) {
        if (submitError.message.toLowerCase().includes('timeout') || submitError.message.includes('30000ms')) {
          msg = 'AI face processing took longer than expected. Please check your network and try again.';
        } else {
          msg = submitError.message;
        }
      }
      setError(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="main-content">
      <button type="button" onClick={() => navigate(-1)} className="btn btn-secondary btn-sm page-back"><ArrowLeft size={16} aria-hidden="true" /> Back</button>
      <div className="glass-panel form-shell">
        <div className="page-intro">
          <h2 className="section-title"><span aria-hidden="true">➕</span> {t.form.title}</h2>
          <p className="section-subtitle">{t.form.subtitle}</p>
        </div>

        {error && (
          <div className="form-error-banner" role="alert">
            <AlertCircle size={19} aria-hidden="true" />
            <div><strong>Submission Issue</strong><span>{error}</span></div>
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <ImageDropzone photos={photos} onPhotosChange={setPhotos} maxPhotos={5} />
          <div className="form-grid">
            <FormField label={t.form.fullName} id="report-name" required>
              <input id="report-name" type="text" required className="form-control" placeholder={t.form.fullNamePlaceholder} value={fullName} onChange={(event) => setFullName(event.target.value)} />
            </FormField>
            <FormField label={t.form.age} id="report-age" required>
              <input id="report-age" type="number" min="1" max="120" required className="form-control" placeholder="24" value={age} onChange={(event) => setAge(event.target.value ? Number(event.target.value) : '')} />
            </FormField>
            <FormField label={t.form.gender} id="report-gender" required>
              <select id="report-gender" required className="form-control" value={gender} onChange={(event) => setGender(event.target.value)}>
                <option value="Male">{t.form.male}</option><option value="Female">{t.form.female}</option><option value="Other">{t.form.other}</option>
              </select>
            </FormField>
            <FormField label={t.form.height} id="report-height">
              <input id="report-height" type="number" min="30" max="250" className="form-control" placeholder="175" value={heightCm} onChange={(event) => setHeightCm(event.target.value ? Number(event.target.value) : '')} />
            </FormField>
            <div className="form-field-wide">
              <FormField label={t.form.lastSeenLocation} id="report-location" required>
                <input id="report-location" type="text" required className="form-control" placeholder={t.form.lastSeenLocationPlaceholder} value={location} onChange={(event) => setLocation(event.target.value)} />
              </FormField>
            </div>
            <FormField label={t.form.lastSeenTime} id="report-date" required>
              <input id="report-date" type="datetime-local" required className="form-control" value={lastSeenTime} onChange={(event) => setLastSeenTime(event.target.value)} />
            </FormField>
            <FormField label={t.form.contactPhone} id="report-contact" required>
              <input id="report-contact" type="text" required className="form-control" placeholder={t.form.contactPhonePlaceholder} value={contact} onChange={(event) => setContact(event.target.value)} />
            </FormField>
            <div className="form-field-wide">
              <FormField label={t.form.description} id="report-desc">
                <textarea id="report-desc" className="form-control" rows={3} placeholder={t.form.descriptionPlaceholder} value={description} onChange={(event) => setDescription(event.target.value)} />
              </FormField>
            </div>
          </div>

          {/* ── FIR Section ── */}
          <div className="form-section-divider">
            <Shield size={20} aria-hidden="true" />
            <h3>FIR (First Information Report) Details</h3>
            <p className="section-subtitle">Provide your police FIR details to verify this report. This is required for CCTV surveillance activation.</p>
          </div>
          <div className="form-grid">
            <FormField label="FIR Number" id="report-fir-number" required>
              <input
                id="report-fir-number"
                type="text"
                required
                className="form-control"
                placeholder="e.g. FIR/2026/1234 or 1234/2026"
                value={firNumber}
                onChange={(event) => setFirNumber(event.target.value)}
              />
              <small className="form-hint">Enter the FIR number as printed on your police complaint receipt</small>
            </FormField>
            <FormField label="Police Station" id="report-fir-station" required>
              <input
                id="report-fir-station"
                type="text"
                required
                className="form-control"
                placeholder="e.g. Saket Police Station"
                value={firPoliceStation}
                onChange={(event) => setFirPoliceStation(event.target.value)}
              />
            </FormField>
            <FormField label="FIR Filing Date" id="report-fir-date">
              <input
                id="report-fir-date"
                type="date"
                className="form-control"
                value={firDate}
                onChange={(event) => setFirDate(event.target.value)}
              />
            </FormField>
            <FormField label="FIR Document (Optional)" id="report-fir-doc">
              <input
                id="report-fir-doc"
                type="file"
                accept=".pdf,.jpg,.jpeg,.png"
                className="form-control"
                onChange={handleFirDocChange}
              />
              <small className="form-hint">Upload a scanned copy of your FIR (PDF, JPEG, or PNG, max 20 MB)</small>
              {firDocument && (
                <span className="form-file-name">📎 {firDocument.name}</span>
              )}
            </FormField>
          </div>

          <button type="submit" disabled={isSubmitting} className="btn btn-primary btn-lg form-submit"><Send size={18} aria-hidden="true" /> {isSubmitting ? t.form.submitting : t.form.submitButton}</button>
        </form>
      </div>
    </div>
  );
};
