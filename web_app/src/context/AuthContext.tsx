import React, { createContext, useContext, useEffect, useState } from 'react';
import { UserProfile, AuthState } from '../types/auth';
import { authService } from '../services/authService';

interface AuthContextType extends AuthState {
  loginWithEmail: (email: string, pass: string) => Promise<UserProfile>;
  registerWithEmail: (email: string, pass: string, name: string) => Promise<UserProfile>;
  loginWithGoogle: () => Promise<UserProfile>;
  loginWithGoogleRedirect: () => Promise<void>;
  loginWithMock: (role?: string) => Promise<UserProfile>;
  signOut: () => Promise<void>;
  resetPassword: (email: string) => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<UserProfile | null>(authService.getCurrentProfile());
  const [token, setToken] = useState<string | null>(localStorage.getItem('fmp_auth_token'));
  const [isLoading, setIsLoading] = useState<boolean>(true);

  useEffect(() => {
    // Initial token check
    authService.getIdToken().then((t) => {
      setToken(t);
      setIsLoading(false);
    });

    const unsubscribe = authService.subscribe((profile) => {
      setUser(profile);
      setToken(localStorage.getItem('fmp_auth_token'));
      setIsLoading(false);
    });

    return () => unsubscribe();
  }, []);

  const loginWithEmail = async (email: string, pass: string) => {
    setIsLoading(true);
    try {
      const p = await authService.loginWithEmail(email, pass);
      setUser(p);
      setToken(localStorage.getItem('fmp_auth_token'));
      return p;
    } finally {
      setIsLoading(false);
    }
  };

  const registerWithEmail = async (email: string, pass: string, name: string) => {
    setIsLoading(true);
    try {
      const p = await authService.registerWithEmail(email, pass, name);
      setUser(p);
      setToken(localStorage.getItem('fmp_auth_token'));
      return p;
    } finally {
      setIsLoading(false);
    }
  };

  const loginWithGoogle = async () => {
    setIsLoading(true);
    try {
      const p = await authService.loginWithGoogle();
      setUser(p);
      setToken(localStorage.getItem('fmp_auth_token'));
      return p;
    } finally {
      setIsLoading(false);
    }
  };

  const loginWithGoogleRedirect = async () => {
    setIsLoading(true);
    try {
      await authService.loginWithGoogleRedirect();
    } finally {
      setIsLoading(false);
    }
  };

  const loginWithMock = async (role = "admin") => {
    setIsLoading(true);
    try {
      const p = await authService.loginWithMock(role);
      setUser(p);
      setToken(localStorage.getItem('fmp_auth_token'));
      return p;
    } finally {
      setIsLoading(false);
    }
  };

  const signOut = async () => {
    await authService.signOut();
    setUser(null);
    setToken(null);
  };

  const resetPassword = async (email: string) => {
    await authService.resetPassword(email);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isLoading,
        isAuthenticated: !!token && !!user,
        loginWithEmail,
        registerWithEmail,
        loginWithGoogle,
        loginWithGoogleRedirect,
        loginWithMock,
        signOut,
        resetPassword,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
