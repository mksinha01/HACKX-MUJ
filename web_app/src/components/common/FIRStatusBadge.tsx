import React from 'react';
import { Shield, ShieldCheck, ShieldX, ShieldOff } from 'lucide-react';
import type { FIRStatus } from '../../types/report';

interface FIRStatusBadgeProps {
  status?: FIRStatus | null;
  rejectionReason?: string | null;
  compact?: boolean;
}

const STATUS_CONFIG: Record<string, { label: string; className: string; icon: React.ReactNode; description: string }> = {
  PENDING: {
    label: 'FIR Pending',
    className: 'fir-badge fir-badge--pending',
    icon: <Shield size={14} />,
    description: 'Awaiting FIR verification by admin',
  },
  VERIFIED: {
    label: 'FIR Verified',
    className: 'fir-badge fir-badge--verified',
    icon: <ShieldCheck size={14} />,
    description: 'FIR confirmed — active on CCTV network',
  },
  REJECTED: {
    label: 'FIR Rejected',
    className: 'fir-badge fir-badge--rejected',
    icon: <ShieldX size={14} />,
    description: 'FIR invalid — please resubmit',
  },
  WAIVED: {
    label: 'FIR Waived',
    className: 'fir-badge fir-badge--waived',
    icon: <ShieldOff size={14} />,
    description: 'FIR requirement waived (emergency)',
  },
};

export const FIRStatusBadge: React.FC<FIRStatusBadgeProps> = ({ status, rejectionReason, compact = false }) => {
  const config = STATUS_CONFIG[status || 'PENDING'] || STATUS_CONFIG.PENDING;

  return (
    <div className={config.className} title={config.description}>
      {config.icon}
      <span className="fir-badge__label">{config.label}</span>
      {!compact && status === 'REJECTED' && rejectionReason && (
        <span className="fir-badge__reason">— {rejectionReason}</span>
      )}
    </div>
  );
};
