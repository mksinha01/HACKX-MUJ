import { 
  signInWithEmailAndPassword, 
  createUserWithEmailAndPassword, 
  signInWithPopup, 
  signInWithRedirect,
  getRedirectResult,
  GoogleAuthProvider, 
  signOut as fbSignOut, 
  sendPasswordResetEmail,
  onAuthStateChanged,
  User as FirebaseUser
} from 'firebase/auth';
import { auth } from '../config/firebase';
import { usersApi } from './api';
import { UserProfile } from '../types/auth';

type AuthListener = (user: UserProfile | null) => void;

export function formatAuthError(error: any): string {
  if (!error) return 'An unknown authentication error occurred.';
  const code = error.code || '';
  const message = error.message || '';

  if (code === 'auth/operation-not-allowed' || message.includes('OPERATION_NOT_ALLOWED')) {
    return 'Google Sign-In is not enabled in your Firebase Console. Please go to Firebase Console > Authentication > Sign-in method > Enable Google provider (or use Email Login / 1-Click Dev Mock Login).';
  }
  if (code === 'auth/unauthorized-domain' || message.includes('unauthorized-domain')) {
    return 'This domain (localhost) is not authorized in Firebase Console. Add localhost under Authentication > Settings > Authorized Domains.';
  }
  if (code === 'auth/popup-closed-by-user') {
    return 'The sign-in popup was closed before completing login. If the popup closed automatically within seconds, Google Sign-In is not enabled in your Firebase Console.';
  }
  if (code === 'auth/popup-blocked') {
    return 'Sign-in popup was blocked by your browser. Please allow popups for localhost or try again.';
  }
  if (code === 'auth/cancelled-popup-request') {
    return 'Another sign-in popup is already open. Please complete or close it.';
  }
  if (code === 'auth/user-not-found' || code === 'auth/wrong-password' || code === 'auth/invalid-credential') {
    return 'Invalid email or password.';
  }
  if (code === 'auth/email-already-in-use') {
    return 'An account with this email address already exists. Please sign in instead.';
  }
  if (code === 'auth/weak-password') {
    return 'Password is too weak. Please use at least 6 characters.';
  }
  if (code === 'auth/network-request-failed') {
    return 'Network connection error. Please check your internet connection and try again.';
  }
  if (code === 'auth/account-exists-with-different-credential') {
    return 'An account already exists with the same email address but different sign-in credentials.';
  }
  return error.message || 'Authentication failed. Please try again.';
}

export class AuthService {
  private currentUser: FirebaseUser | null = null;
  private listeners: AuthListener[] = [];
  private currentProfile: UserProfile | null = null;

  constructor() {
    // Restore cached profile immediately if available
    const cachedProfile = localStorage.getItem('fmp_user_profile');
    if (cachedProfile) {
      try {
        this.currentProfile = JSON.parse(cachedProfile);
      } catch (e) {
        // ignore malformed cache
      }
    }

    if (auth) {
      // Check for redirect result on app initialization
      getRedirectResult(auth)
        .then(async (cred) => {
          if (cred && cred.user) {
            this.currentUser = cred.user;
            const token = await cred.user.getIdToken();
            localStorage.setItem('fmp_auth_token', token);
            await this.syncAndSetProfile(cred.user);
          }
        })
        .catch((err) => {
          console.warn('Firebase getRedirectResult error:', err);
        });

      onAuthStateChanged(auth, async (user) => {
        this.currentUser = user;
        if (user) {
          try {
            const token = await user.getIdToken();
            localStorage.setItem('fmp_auth_token', token);
            await this.syncAndSetProfile(user);
          } catch (err) {
            console.error('Failed to sync authenticated user profile', err);
            this.notifyListeners(this.currentProfile);
          }
        } else {
          // If no Firebase user, check if we have a mock token
          const mockToken = localStorage.getItem('fmp_auth_token');
          if (mockToken && mockToken.startsWith('mock-token')) {
            this.notifyListeners(this.currentProfile);
          } else {
            this.currentProfile = null;
            localStorage.removeItem('fmp_auth_token');
            localStorage.removeItem('fmp_user_profile');
            this.notifyListeners(null);
          }
        }
      });
    }
  }

  private async syncAndSetProfile(user: FirebaseUser): Promise<UserProfile> {
    let profile: UserProfile;
    try {
      // First try to get existing profile
      profile = await usersApi.getProfile();
    } catch {
      try {
        // If profile doesn't exist yet, sync/register with backend
        profile = await usersApi.sync(
          user.uid,
          user.displayName || user.email?.split('@')[0] || 'User',
          user.email || undefined
        );
      } catch (syncErr) {
        console.warn('Backend sync failed, using fallback profile:', syncErr);
        profile = {
          id: user.uid,
          firebase_uid: user.uid,
          name: user.displayName || user.email?.split('@')[0] || 'User',
          email: user.email || null,
          phone: user.phoneNumber || null,
          avatar_url: user.photoURL || null,
          language: 'en',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        };
      }
    }
    this.currentProfile = profile;
    localStorage.setItem('fmp_user_profile', JSON.stringify(profile));
    this.notifyListeners(profile);
    return profile;
  }

  subscribe(listener: AuthListener): () => void {
    this.listeners.push(listener);
    listener(this.currentProfile);
    return () => {
      this.listeners = this.listeners.filter(l => l !== listener);
    };
  }

  private notifyListeners(user: UserProfile | null) {
    this.listeners.forEach(l => l(user));
  }

  async getIdToken(forceRefresh = false): Promise<string | null> {
    if (this.currentUser) {
      return await this.currentUser.getIdToken(forceRefresh);
    }
    return localStorage.getItem('fmp_auth_token');
  }

  getCurrentProfile(): UserProfile | null {
    return this.currentProfile;
  }

  async loginWithEmail(email: string, pass: string): Promise<UserProfile> {
    if (!auth) {
      throw new Error("Firebase Authentication is not configured. Please use 1-Click Dev Mock Login.");
    }
    try {
      const cred = await signInWithEmailAndPassword(auth, email.trim(), pass);
      this.currentUser = cred.user;
      const token = await cred.user.getIdToken();
      localStorage.setItem('fmp_auth_token', token);
      return await this.syncAndSetProfile(cred.user);
    } catch (error: any) {
      throw new Error(formatAuthError(error));
    }
  }

  async registerWithEmail(email: string, pass: string, name: string): Promise<UserProfile> {
    if (!auth) {
      throw new Error("Firebase Authentication is not configured. Please use 1-Click Dev Mock Login.");
    }
    try {
      const cred = await createUserWithEmailAndPassword(auth, email.trim(), pass);
      this.currentUser = cred.user;
      const token = await cred.user.getIdToken();
      localStorage.setItem('fmp_auth_token', token);

      let profile: UserProfile;
      try {
        profile = await usersApi.sync(cred.user.uid, name.trim(), email.trim());
      } catch {
        profile = {
          id: cred.user.uid,
          firebase_uid: cred.user.uid,
          name: name.trim(),
          email: email.trim(),
          language: 'en',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        };
      }
      this.currentProfile = profile;
      localStorage.setItem('fmp_user_profile', JSON.stringify(profile));
      this.notifyListeners(profile);
      return profile;
    } catch (error: any) {
      throw new Error(formatAuthError(error));
    }
  }

  async loginWithGoogle(): Promise<UserProfile> {
    if (!auth) {
      throw new Error("Firebase Authentication is not configured. Please use 1-Click Dev Mock Login.");
    }
    const provider = new GoogleAuthProvider();
    provider.setCustomParameters({
      prompt: 'select_account'
    });

    try {
      const cred = await signInWithPopup(auth, provider);
      this.currentUser = cred.user;
      const token = await cred.user.getIdToken();
      localStorage.setItem('fmp_auth_token', token);
      return await this.syncAndSetProfile(cred.user);
    } catch (error: any) {
      console.error("Google login error:", error);
      throw new Error(formatAuthError(error));
    }
  }

  async loginWithGoogleRedirect(): Promise<void> {
    if (!auth) {
      throw new Error("Firebase Authentication is not configured. Please use 1-Click Dev Mock Login.");
    }
    const provider = new GoogleAuthProvider();
    provider.setCustomParameters({
      prompt: 'select_account'
    });
    try {
      await signInWithRedirect(auth, provider);
    } catch (error: any) {
      console.error("Google sign-in redirect error:", error);
      throw new Error(formatAuthError(error));
    }
  }

  async loginWithMock(role = "admin"): Promise<UserProfile> {
    const token = `mock-token-${role}`;
    localStorage.setItem('fmp_auth_token', token);
    
    // Call /auth/verify or /users/me which supports mock token auto-provisioning
    try {
      const profile = await usersApi.getProfile();
      this.currentProfile = profile;
      localStorage.setItem('fmp_user_profile', JSON.stringify(profile));
      this.notifyListeners(profile);
      return profile;
    } catch (e) {
      const fallback: UserProfile = {
        id: "00000000-0000-0000-0000-000000000001",
        firebase_uid: `uid_${token}`,
        name: `Dev ${role.charAt(0).toUpperCase() + role.slice(1)}`,
        email: `${role}@dev.local`,
        language: "en",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      this.currentProfile = fallback;
      localStorage.setItem('fmp_user_profile', JSON.stringify(fallback));
      this.notifyListeners(fallback);
      return fallback;
    }
  }

  async signOut(): Promise<void> {
    if (auth) {
      await fbSignOut(auth).catch(() => {});
    }
    this.currentUser = null;
    this.currentProfile = null;
    localStorage.removeItem('fmp_auth_token');
    localStorage.removeItem('fmp_user_profile');
    this.notifyListeners(null);
  }

  async resetPassword(email: string): Promise<void> {
    if (!auth) {
      throw new Error("Firebase Authentication is not configured.");
    }
    try {
      await sendPasswordResetEmail(auth, email.trim());
    } catch (error: any) {
      throw new Error(formatAuthError(error));
    }
  }
}

export const authService = new AuthService();
