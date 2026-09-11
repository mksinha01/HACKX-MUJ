import React, { useEffect, useRef, useState } from 'react';
import { Link, NavLink, useNavigate } from 'react-router-dom';
import {
  Bell,
  FileText,
  Globe,
  LayoutDashboard,
  LogOut,
  Menu,
  Shield,
  User as UserIcon,
  UserPlus,
  X,
  type LucideIcon,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useLanguage } from '../../context/LanguageContext';
import { notificationsApi } from '../../services/api';
import { sseService } from '../../services/sseService';

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  end?: boolean;
}

export const Navbar: React.FC = () => {
  const { user, isAuthenticated, signOut } = useAuth();
  const { language, setLanguage, t } = useLanguage();
  const navigate = useNavigate();
  const userMenuRef = useRef<HTMLDivElement>(null);
  const [unreadCount, setUnreadCount] = useState(0);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [userDropdownOpen, setUserDropdownOpen] = useState(false);

  useEffect(() => {
    if (!isAuthenticated) return;

    notificationsApi.getUnreadCount().then(setUnreadCount).catch(() => undefined);
    const unsubscribe = sseService.subscribe(() => setUnreadCount((previous) => previous + 1));
    sseService.connect();

    return () => unsubscribe();
  }, [isAuthenticated]);

  useEffect(() => {
    const handlePointerDown = (event: PointerEvent) => {
      if (userMenuRef.current && !userMenuRef.current.contains(event.target as Node)) {
        setUserDropdownOpen(false);
      }
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setUserDropdownOpen(false);
        setMobileMenuOpen(false);
      }
    };

    document.addEventListener('pointerdown', handlePointerDown);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('pointerdown', handlePointerDown);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, []);

  const navItems: NavItem[] = [
    { to: '/dashboard', label: t.nav.dashboard, icon: LayoutDashboard, end: true },
    { to: '/reports', label: t.nav.myReports, icon: FileText, end: true },
    { to: '/reports/new', label: t.nav.newReport, icon: UserPlus },
    { to: '/notifications', label: t.nav.alerts, icon: Bell },
    { to: '/profile', label: t.nav.profile, icon: UserIcon },
  ];

  const handleSignOut = async () => {
    await signOut();
    setUserDropdownOpen(false);
    navigate('/login');
  };

  if (!isAuthenticated) {
    return (
      <header className="public-topbar">
        <Link to="/login" className="public-brand" aria-label="FIND-MISSING-PEP home">
          <span className="public-brand__mark"><Shield size={19} strokeWidth={1.8} /></span>
          <span>
            <span className="public-brand__wordmark">FIND-MISSING-PEP</span>
            <span className="public-brand__sub">Command Center</span>
          </span>
        </Link>
        <div className="public-topbar__tools">
          <button
            type="button"
            onClick={() => setLanguage(language === 'en' ? 'hi' : 'en')}
            className="btn btn-secondary btn-sm"
            title="Toggle English / हिन्दी"
          >
            <Globe size={15} />
            <span>{language === 'en' ? 'हिन्दी' : 'EN'}</span>
          </button>
          <Link to="/login" className="btn btn-primary btn-sm">{t.nav.signIn}</Link>
        </div>
      </header>
    );
  }

  return (
    <header className="app-rail">
      <Link to="/dashboard" className="rail-brand" aria-label="FIND-MISSING-PEP dashboard">
        <span className="rail-brand__mark"><Shield size={19} strokeWidth={1.8} /></span>
        <span>
          <span className="rail-brand__wordmark">FIND-MISSING-PEP</span>
          <span className="rail-brand__sub">Command Center</span>
        </span>
      </Link>

      <button
        type="button"
        className="btn btn-secondary btn-sm mobile-menu-btn"
        onClick={() => setMobileMenuOpen((open) => !open)}
        aria-expanded={mobileMenuOpen}
        aria-controls="primary-navigation"
        aria-label="Toggle navigation menu"
      >
        {mobileMenuOpen ? <X size={18} /> : <Menu size={18} />}
      </button>

      <p className="rail-eyebrow">Operations</p>
      <nav id="primary-navigation" className={`rail-nav${mobileMenuOpen ? ' is-open' : ''}`} aria-label="Primary navigation">
        {navItems.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
            onClick={() => setMobileMenuOpen(false)}
          >
            <Icon aria-hidden="true" />
            <span className="nav-link__label">{label}</span>
            {to === '/notifications' && unreadCount > 0 && (
              <span className="nav-link__badge" aria-label={`${unreadCount} unread alerts`}>
                {unreadCount > 9 ? '9+' : unreadCount}
              </span>
            )}
          </NavLink>
        ))}
      </nav>

      <div className="rail-spacer" />
      <div className="rail-status"><span className="status-dot" /> Backend Online</div>
      <div className="rail-actions">
        <a href="/docs" target="_blank" rel="noopener noreferrer" className="rail-action">
          <FileText aria-hidden="true" />
          <span>FastAPI Docs</span>
        </a>
        <button
          type="button"
          onClick={() => setLanguage(language === 'en' ? 'hi' : 'en')}
          className="rail-action"
          title="Toggle English / हिन्दी"
        >
          <Globe aria-hidden="true" />
          <span>{language === 'en' ? 'हिन्दी' : 'English'}</span>
        </button>
      </div>

      <div ref={userMenuRef} className="rail-user">
        <button
          type="button"
          className="rail-user__button"
          onClick={() => setUserDropdownOpen((open) => !open)}
          aria-expanded={userDropdownOpen}
          aria-haspopup="menu"
        >
          <span className="user-avatar" aria-hidden="true">{user?.name?.charAt(0).toUpperCase() || 'U'}</span>
          <span className="rail-user__copy">
            <span className="rail-user__name">{user?.name || 'Authorized User'}</span>
            <span className="rail-user__email">{user?.email || 'Active session'}</span>
          </span>
          <span aria-hidden="true">⋯</span>
        </button>

        {userDropdownOpen && (
          <div className="user-menu" role="menu">
            <div className="user-menu__summary">
              <strong>{user?.name || 'Authorized User'}</strong>
              <span>{user?.email || 'Logged in via device session'}</span>
            </div>
            <Link to="/profile" className="dropdown-item" role="menuitem" onClick={() => setUserDropdownOpen(false)}>
              <UserIcon size={16} aria-hidden="true" />
              <span>{t.nav.profile}</span>
            </Link>
            <button type="button" className="dropdown-item dropdown-item--danger" role="menuitem" onClick={handleSignOut}>
              <LogOut size={16} aria-hidden="true" />
              <span>{t.nav.signOut}</span>
            </button>
          </div>
        )}
      </div>
    </header>
  );
};
