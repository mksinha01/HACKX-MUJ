import React, { useEffect, useState } from 'react';
import { PlusCircle, RefreshCw, Search, Users, UserX } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useLanguage } from '../context/LanguageContext';
import { reportsApi } from '../services/api';
import { MissingPerson } from '../types/report';
import { ReportCard } from '../components/reports/ReportCard';
import { LoadingSpinner } from '../components/common/LoadingSpinner';

export const MyReportsPage: React.FC = () => {
  const { t } = useLanguage();
  const navigate = useNavigate();
  const [reports, setReports] = useState<MissingPerson[]>([]);
  const [selectedStatus, setSelectedStatus] = useState('ALL');
  const [searchQuery, setSearchQuery] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const statusFilters = [
    { key: 'ALL', label: t.status.ALL },
    { key: 'ACTIVE', label: t.status.ACTIVE },
    { key: 'FOUND', label: t.status.FOUND },
    { key: 'PROCESSING', label: t.status.PROCESSING },
    { key: 'CLOSED', label: t.status.CLOSED },
  ];

  const fetchReports = async (silent = false) => {
    if (!silent) setIsLoading(true);
    else setIsRefreshing(true);

    try {
      const response = await reportsApi.getMyReports(selectedStatus, 1, 100);
      setReports(response.items || []);
    } catch (error) {
      console.warn('Could not fetch user reports, attempting global directory fetch', error);
      try {
        const fallbackResponse = await reportsApi.getAllReports(selectedStatus, 1, 100);
        setReports(fallbackResponse.items || []);
      } catch (fallbackError) {
        console.error('Failed to load reports', fallbackError);
      }
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  };

  useEffect(() => { void fetchReports(); }, [selectedStatus]);

  const filteredReports = reports.filter((item) => {
    if (!searchQuery.trim()) return true;
    const query = searchQuery.toLowerCase();
    return item.full_name?.toLowerCase().includes(query) || item.last_seen_location?.toLowerCase().includes(query);
  });

  return (
    <div className="main-content">
      <div className="section-header">
        <div>
          <h2 className="section-title"><Users size={20} className="section-title__icon" aria-hidden="true" /> {t.reports.title}</h2>
          <p className="section-subtitle">{t.reports.subtitle}</p>
        </div>
        <div className="page-actions">
          <button type="button" onClick={() => void fetchReports(true)} className="btn btn-secondary btn-sm" disabled={isRefreshing} aria-label="Refresh reports">
            <RefreshCw size={14} className={isRefreshing ? 'spin' : ''} aria-hidden="true" />
            <span className="sr-only">Refresh</span>
          </button>
          <button type="button" onClick={() => navigate('/reports/new')} className="btn btn-primary btn-sm">
            <PlusCircle size={16} aria-hidden="true" /> <span>{t.reports.fileNew}</span>
          </button>
        </div>
      </div>

      <div className="report-toolbar">
        <label className="search-control">
          <Search size={16} aria-hidden="true" />
          <span className="sr-only">{t.reports.searchPlaceholder}</span>
          <input type="search" className="form-control" placeholder={t.reports.searchPlaceholder} value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} />
        </label>
        <div className="filter-set" role="group" aria-label="Filter reports by status">
          {statusFilters.map((filter) => (
            <button key={filter.key} type="button" onClick={() => setSelectedStatus(filter.key)} className={`btn btn-sm ${selectedStatus === filter.key ? 'btn-primary' : 'btn-secondary'}`} aria-pressed={selectedStatus === filter.key}>
              {filter.label}
            </button>
          ))}
        </div>
      </div>

      {isLoading ? (
        <LoadingSpinner text="Loading Cases..." />
      ) : filteredReports.length === 0 ? (
        <div className="glass-panel empty-state">
          <UserX size={42} aria-hidden="true" />
          <h3>{t.reports.noReports}</h3>
          <p>{t.reports.fileFirstPrompt}</p>
          <button type="button" onClick={() => navigate('/reports/new')} className="btn btn-primary"><PlusCircle size={18} aria-hidden="true" /> {t.reports.fileNew}</button>
        </div>
      ) : (
        <div className="cases-grid">
          {filteredReports.map((person) => <ReportCard key={person.id} person={person} />)}
        </div>
      )}
    </div>
  );
};
