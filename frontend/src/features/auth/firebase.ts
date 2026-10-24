import { initializeApp } from 'firebase/app';
import {
  GithubAuthProvider,
  GoogleAuthProvider,
  browserPopupRedirectResolver,
  browserSessionPersistence,
  createUserWithEmailAndPassword,
  initializeAuth,
  sendPasswordResetEmail,
  signInWithEmailAndPassword,
  signInWithPopup,
  signOut,
  type Auth,
  type User,
} from 'firebase/auth';
import { env } from '@/lib/env';

/*
 * Firebase Authentication. Import this module lazily (`await import('./firebase')`) so the demo
 * never downloads the SDK. Sign-ins last for the browser tab, like the app session.
 */

/** Thrown when the VITE_FIREBASE_* settings are missing. */
export class FirebaseNotConfiguredError extends Error {
  readonly code = 'claimlens/firebase-not-configured';

  constructor() {
    super('Firebase is not configured.');
  }
}

let auth: Auth | undefined;

function firebaseAuth(): Auth {
  if (!env.firebase) throw new FirebaseNotConfiguredError();
  auth ??= initializeAuth(initializeApp(env.firebase), {
    persistence: browserSessionPersistence,
    popupRedirectResolver: browserPopupRedirectResolver,
  });
  return auth;
}

export async function signInWithProvider(provider: 'google' | 'github'): Promise<User> {
  const authProvider = provider === 'google' ? new GoogleAuthProvider() : new GithubAuthProvider();
  return (await signInWithPopup(firebaseAuth(), authProvider)).user;
}

export async function signInWithEmail(email: string, password: string): Promise<User> {
  return (await signInWithEmailAndPassword(firebaseAuth(), email, password)).user;
}

export async function createAccount(email: string, password: string): Promise<User> {
  return (await createUserWithEmailAndPassword(firebaseAuth(), email, password)).user;
}

// Every export is async, so a missing configuration rejects instead of throwing.

export async function sendPasswordReset(email: string): Promise<void> {
  await sendPasswordResetEmail(firebaseAuth(), email);
}

export async function signOutOfFirebase(): Promise<void> {
  await signOut(firebaseAuth());
}

/** An ID token for the signed-in user (Firebase refreshes it as needed), or null if signed out. */
export async function currentIdToken(): Promise<string | null> {
  const instance = firebaseAuth();
  await instance.authStateReady();
  return instance.currentUser ? instance.currentUser.getIdToken() : null;
}
