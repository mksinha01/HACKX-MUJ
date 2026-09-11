import React, { useEffect, useState } from 'react';
import { Bell, Camera, Check, CheckCheck, Clock, FileText } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useLanguage } from '../context/LanguageContext';
import { useToast } from '../context/ToastContext';
import { notificationsApi } from '../services/api';
import { sseService } from '../services/sseService';
import { NotificationItem } from '../types/notification';
import { LoadingSpinner } from '../components/common/LoadingSpinner';

export const NotificationsPage: React.FC = () => {
  const { t } = useLanguage();
  const { addToast } = useToast();
  const navigate = useNavigate();
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  const fetchNotifications = async (silent = false) => {
    if (!silent) setIsLoading(true);
    try {
      const response = await notificationsApi.list(unreadOnly);
      setNotifications(response.items || []);
    } catch (error) {
      console.error('Failed to load notifications', error);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void fetchNotifications();
    const unsubscribe = sseService.subscribe(() => {
      void fetchNotifications(true);
    });
    sseService.connect();
    return () => unsubscribe();
  }, [unreadOnly]);

  const handleMarkAllRead = async () => {
    try {
      await notificationsApi.markAllRead();
      setNotifications((previous) => previous.map((item) => ({ ...item, is_read: true })));
      addToast('All notifications marked as read.', 'success');
    } catch {
      addToast('Failed to mark notifications read', 'error');
    }
  };

  const handleItemClick = async (notification: NotificationItem) => {
    if (!notification.is_read) {
      notificationsApi.markRead(notification.id).catch(() => undefined);
      setNotifications((previous) => previous.map((item) => item.id === notification.id ? { ...item, is_read: true } : item));
    }
    if (notification.sighting_id) navigate(`/sightings/${notification.sighting_id}`);
    else if (notification.data?.person_id) navigate(`/reports/${notification.data.person_id}`);
  };

  const unreadCount = notifications.filter((item) => !item.is_read).length;

  return (
    <div className="main-content">
      <div className="section-header">
        <div>
          <h2 className="section-title"><Bell size={20} aria-hidden="true" /> {t.notifications.title}</h2>
          <p className="section-subtitle">{t.notifications.subtitle}</p>
        </div>
        {unreadCount > 0 && <button type="button" onClick={() => void handleMarkAllRead()} className="btn btn-secondary btn-sm"><CheckCheck size={16} aria-hidden="true" /> {t.notifications.markAllRead}</button>}
      </div>

      <div className="filter-set notification-filters" role="group" aria-label="Notification filter">
        <button type="button" onClick={() => setUnreadOnly(false)} className={`btn btn-sm ${!unreadOnly ? 'btn-primary' : 'btn-secondary'}`} aria-pressed={!unreadOnly}>{t.notifications.all}</button>
        <button type="button" onClick={() => setUnreadOnly(true)} className={`btn btn-sm ${unreadOnly ? 'btn-primary' : 'btn-secondary'}`} aria-pressed={unreadOnly}>{t.notifications.unread} {unreadCount > 0 && `(${unreadCount})`}</button>
      </div>

      {isLoading ? <LoadingSpinner text="Loading notifications..." /> : notifications.length === 0 ? (
        <div className="glass-panel empty-state"><Check size={42} aria-hidden="true" /><h3>All Caught Up!</h3><p>{t.notifications.noNotifications}</p></div>
      ) : (
        <div className="notification-list">
          {notifications.map((item) => (
            <button key={item.id} type="button" onClick={() => void handleItemClick(item)} className={`glass-panel notification-item${item.is_read ? '' : ' is-unread'}`}>
              <span className={`notification-item__icon${item.sighting_id ? ' is-sighting' : ''}`}>{item.sighting_id ? <Camera size={19} aria-hidden="true" /> : <FileText size={19} aria-hidden="true" />}</span>
              <span className="notification-item__body">
                <span className="notification-item__heading"><strong>{item.title}</strong><span><Clock size={12} aria-hidden="true" /> {new Date(item.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span></span>
                <span className="notification-item__copy">{item.body}</span>
              </span>
              {!item.is_read && <span className="notification-item__dot" aria-label="Unread" />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};
