import { APP_CONSTANTS } from '../config/constants';
import { authService } from './authService';

export interface SightingAlertEvent {
  sighting_id: string;
  notification_id?: string;
  person_id?: string;
  person_name?: string;
  similarity: number | string;
  confidence_level?: string;
  camera_id?: string;
  camera_location?: string;
  detected_at?: string;
  face_crop_path?: string;
  full_frame_path?: string;
  video_clip_path?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  num_frames_matched?: number | null;
  title: string;
  body: string;
}

type SightingListener = (event: SightingAlertEvent) => void;

export class SseService {
  private eventSource: EventSource | null = null;
  private listeners: SightingListener[] = [];
  private audioCtx: AudioContext | null = null;
  private currentToken: string | null = null;

  constructor() {
    // Lazy AudioContext setup
  }

  private playSyntheticChime() {
    try {
      const AudioContextClass = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      if (!this.audioCtx) {
        this.audioCtx = new AudioContextClass();
      }
      if (this.audioCtx.state === 'suspended') {
        this.audioCtx.resume();
      }

      const now = this.audioCtx.currentTime;
      // High-pitched pleasant dual-tone chime
      const osc1 = this.audioCtx.createOscillator();
      const osc2 = this.audioCtx.createOscillator();
      const gain = this.audioCtx.createGain();

      osc1.type = 'sine';
      osc1.frequency.setValueAtTime(587.33, now); // D5
      osc1.frequency.exponentialRampToValueAtTime(880.00, now + 0.15); // A5

      osc2.type = 'sine';
      osc2.frequency.setValueAtTime(880.00, now + 0.15);
      osc2.frequency.exponentialRampToValueAtTime(1174.66, now + 0.35); // D6

      gain.gain.setValueAtTime(0.2, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.5);

      osc1.connect(gain);
      osc2.connect(gain);
      gain.connect(this.audioCtx.destination);

      osc1.start(now);
      osc1.stop(now + 0.2);
      osc2.start(now + 0.15);
      osc2.stop(now + 0.5);
    } catch (e) {
      // Audio context might be restricted before interaction
    }
  }

  async connect(): Promise<void> {
    const token = await authService.getIdToken();
    if (!token) return;

    if (this.eventSource && this.currentToken === token) {
      return; // Already connected with active token
    }

    if (this.eventSource) {
      this.eventSource.close();
    }

    this.currentToken = token;
    const url = `${APP_CONSTANTS.API_BASE_URL}/events/stream?token=${encodeURIComponent(token)}`;
    this.eventSource = new EventSource(url);

    this.eventSource.addEventListener('sighting', (e: MessageEvent) => {
      try {
        const data: SightingAlertEvent = JSON.parse(e.data);
        this.playSyntheticChime();
        this.listeners.forEach(fn => fn(data));
      } catch (err) {
        console.error("Failed to parse SSE sighting event", err);
      }
    });

    this.eventSource.onerror = () => {
      // Browser EventSource automatically reconnects
    };
  }

  subscribe(listener: SightingListener): () => void {
    this.listeners.push(listener);
    return () => {
      this.listeners = this.listeners.filter(l => l !== listener);
    };
  }

  disconnect(): void {
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
  }
}

export const sseService = new SseService();
