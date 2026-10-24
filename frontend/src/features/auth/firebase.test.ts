import { describe, expect, it } from 'vitest';
import * as firebase from './firebase';

// Tests run without VITE_FIREBASE_* settings.
describe('firebase without settings', () => {
  it.each([
    ['signInWithProvider', () => firebase.signInWithProvider('github')],
    ['signInWithEmail', () => firebase.signInWithEmail('ada@example.edu', 'secret')],
    ['createAccount', () => firebase.createAccount('ada@example.edu', 'secret')],
    ['sendPasswordReset', () => firebase.sendPasswordReset('ada@example.edu')],
    ['signOutOfFirebase', () => firebase.signOutOfFirebase()],
    ['currentIdToken', () => firebase.currentIdToken()],
  ])('%s rejects (never throws) with a not-configured error', async (_name, call) => {
    await expect(call()).rejects.toMatchObject({ code: 'claimlens/firebase-not-configured' });
  });
});
