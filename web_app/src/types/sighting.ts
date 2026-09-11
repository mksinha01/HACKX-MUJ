export type SightingStatus = 'PENDING' | 'CONFIRMED' | 'REJECTED';
export type ConfidenceLevel = 'CONFIRMED' | 'POSSIBLE' | 'REJECTED';

export interface Sighting {
  id: string;
  person_id: string;
  person_name?: string | null;
  camera_id: string;
  agent_id: string;
  similarity_score: number;
  confidence_level: ConfidenceLevel | string;
  num_frames_matched?: number | null;
  camera_location?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  detected_at: string;
  face_crop_path: string;
  full_frame_path: string;
  video_clip_path?: string | null;
  status: SightingStatus;
  reviewed_by?: string | null;
  reviewed_at?: string | null;
  review_notes?: string | null;
  created_at: string;
}

export interface TimelineBreadcrumb {
  sighting_id: string;
  camera_name: string;
  camera_location?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  detected_at: string;
  similarity_score: number;
  status: string;
}

export interface PersonTimeline {
  person_id: string;
  person_name: string;
  entries: TimelineBreadcrumb[];
  last_seen_camera?: string | null;
  last_seen_time?: string | null;
}
