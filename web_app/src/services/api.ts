import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios';
import { APP_CONSTANTS } from '../config/constants';
import { authService } from './authService';
import { 
  MissingPersonResponse, 
  MissingPersonListResponse, 
  SightingResponse, 
  PersonTimeline, 
  NotificationListResponse,
  UserResponse 
} from '../types/api';

export const apiClient = axios.create({
  baseURL: APP_CONSTANTS.API_BASE_URL,
  timeout: 30000,
  headers: {
    'Accept': 'application/json',
  },
});

// ── Bearer Token & Refresh Interceptor ──
apiClient.interceptors.request.use(
  async (config: InternalAxiosRequestConfig) => {
    const token = await authService.getIdToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean };
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;
      try {
        const freshToken = await authService.getIdToken(true);
        if (freshToken) {
          originalRequest.headers.Authorization = `Bearer ${freshToken}`;
          return apiClient(originalRequest);
        }
      } catch (refreshErr) {
        authService.signOut();
      }
    }
    return Promise.reject(error);
  }
);

// ── Reports API ──
export const reportsApi = {
  createAtomic: async (formData: FormData): Promise<MissingPersonResponse> => {
    const res = await apiClient.post<MissingPersonResponse>('/api/reports/', formData, {
      timeout: 90000, // 90s timeout for multipart upload + AI face analysis
      headers: {
        'Content-Type': undefined, // Let browser set multipart boundary
      },
    });
    return res.data;
  },
  getMyReports: async (status?: string, page = 1, limit = 50): Promise<MissingPersonListResponse> => {
    const res = await apiClient.get<MissingPersonListResponse>('/api/reports/', {
      params: { status: status === 'ALL' ? undefined : status, page, limit }
    });
    return res.data;
  },
  getAllReports: async (status?: string, page = 1, limit = 50): Promise<MissingPersonListResponse> => {
    const res = await apiClient.get<MissingPersonListResponse>('/api/reports/all', {
      params: { status: status === 'ALL' ? undefined : status, page, limit }
    });
    return res.data;
  },
  getById: async (id: string): Promise<MissingPersonResponse> => {
    const res = await apiClient.get<MissingPersonResponse>(`/api/reports/${id}`);
    return res.data;
  },
  update: async (id: string, data: Record<string, unknown>): Promise<MissingPersonResponse> => {
    const res = await apiClient.put<MissingPersonResponse>(`/api/reports/${id}`, data);
    return res.data;
  },
  close: async (id: string): Promise<void> => {
    await apiClient.delete(`/api/reports/${id}`);
  },
  uploadPhoto: async (id: string, formData: FormData): Promise<unknown> => {
    const res = await apiClient.post(`/api/reports/${id}/photos`, formData, {
      timeout: 60000, // 60s timeout for single photo upload + AI face analysis
      headers: {
        'Content-Type': undefined,
      },
    });
    return res.data;
  },
  getSightings: async (id: string): Promise<SightingResponse[]> => {
    const res = await apiClient.get<SightingResponse[]>(`/api/reports/${id}/sightings`);
    return res.data;
  },
  getTimeline: async (id: string): Promise<PersonTimeline> => {
    const res = await apiClient.get<PersonTimeline>(`/api/reports/${id}/timeline`);
    return res.data;
  },
};

// ── Sightings API ──
export const sightingsApi = {
  listRecent: async (limit = 50, status?: string): Promise<SightingResponse[]> => {
    const res = await apiClient.get<SightingResponse[]>('/api/sightings/', {
      params: { limit, status_filter: status }
    });
    return res.data;
  },
  getById: async (id: string): Promise<SightingResponse> => {
    const res = await apiClient.get<SightingResponse>(`/api/sightings/${id}`);
    return res.data;
  },
  confirm: async (id: string, notes?: string): Promise<SightingResponse> => {
    const res = await apiClient.put<SightingResponse>(`/api/sightings/${id}/confirm`, {
      review_notes: notes
    });
    return res.data;
  },
  reject: async (id: string, notes?: string): Promise<SightingResponse> => {
    const res = await apiClient.put<SightingResponse>(`/api/sightings/${id}/reject`, {
      review_notes: notes
    });
    return res.data;
  },
};

// ── Notifications API ──
export const notificationsApi = {
  list: async (unreadOnly = false, limit = 50): Promise<NotificationListResponse> => {
    const res = await apiClient.get<NotificationListResponse>('/api/notifications/', {
      params: { unread_only: unreadOnly, limit }
    });
    return res.data;
  },
  getUnreadCount: async (): Promise<number> => {
    const res = await apiClient.get<{ unread_count: number }>('/api/notifications/unread-count');
    return res.data.unread_count;
  },
  markRead: async (id: string): Promise<void> => {
    await apiClient.put(`/api/notifications/${id}/read`);
  },
  markAllRead: async (): Promise<void> => {
    await apiClient.put('/api/notifications/read-all');
  },
};

// ── User API ──
export const usersApi = {
  getProfile: async (): Promise<UserResponse> => {
    const res = await apiClient.get<UserResponse>('/api/users/me');
    return res.data;
  },
  updateProfile: async (data: { name?: string; phone?: string; language?: string }): Promise<UserResponse> => {
    const res = await apiClient.put<UserResponse>('/api/users/me', data);
    return res.data;
  },
  sync: async (firebaseUid: string, name: string, email?: string): Promise<UserResponse> => {
    const res = await apiClient.post<UserResponse>('/api/users/', {
      firebase_uid: firebaseUid,
      name,
      email,
    });
    return res.data;
  },
};
