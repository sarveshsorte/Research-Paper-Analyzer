import { screen, waitFor } from '@testing-library/react';
import userEvent, { type UserEvent } from '@testing-library/user-event';
import type { User } from 'firebase/auth';
import { HttpResponse, http } from 'msw';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { apiUrl } from '@/api/client';
import { MOCK_USER } from '@/mocks/handlers';
import { server } from '@/mocks/node';
import { renderApp } from '@/test/render';
import * as firebase from './firebase';
import { readSession } from './session';

vi.mock('./firebase', () => ({
  signInWithEmail: vi.fn(),
  createAccount: vi.fn(),
  signInWithProvider: vi.fn(),
  sendPasswordReset: vi.fn(),
  signOutOfFirebase: vi.fn(),
  currentIdToken: vi.fn(),
}));

const account = { getIdToken: () => Promise.resolve('id-token') } as unknown as User;
const firebaseError = (code: string) => Object.assign(new Error(code), { code });

async function fillCredentials(user: UserEvent) {
  await user.type(await screen.findByLabelText('Email'), 'ada@example.edu');
  await user.type(screen.getByLabelText('Password'), 'correct-horse');
}

describe('LoginPage with Firebase', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(firebase.signOutOfFirebase).mockResolvedValue();
  });

  it('signs in with email and password once the API accepts the ID token', async () => {
    let authorization: string | null = null;
    server.use(
      http.get(apiUrl('/auth/me'), ({ request }) => {
        authorization = request.headers.get('Authorization');
        return HttpResponse.json({ user: MOCK_USER });
      }),
    );
    vi.mocked(firebase.signInWithEmail).mockResolvedValue(account);
    const user = userEvent.setup();
    const { router } = renderApp('/login', { signedIn: false });

    await fillCredentials(user);
    await user.click(screen.getByRole('button', { name: 'Sign in' }));

    await waitFor(() => expect(router.state.location.pathname).toBe('/'));
    expect(firebase.signInWithEmail).toHaveBeenCalledWith('ada@example.edu', 'correct-horse');
    expect(authorization).toBe('Bearer id-token');
    expect(readSession()).toEqual({ mode: 'firebase', user: MOCK_USER });
  });

  it('creates an account from the same form', async () => {
    vi.mocked(firebase.createAccount).mockResolvedValue(account);
    const user = userEvent.setup();
    const { router } = renderApp('/login', { signedIn: false });

    await user.click(await screen.findByRole('button', { name: 'Create an account' }));
    await fillCredentials(user);
    await user.click(screen.getByRole('button', { name: 'Create account' }));

    await waitFor(() => expect(router.state.location.pathname).toBe('/'));
    expect(firebase.createAccount).toHaveBeenCalledWith('ada@example.edu', 'correct-horse');
    expect(firebase.signInWithEmail).not.toHaveBeenCalled();
  });

  it.each([
    ['GitHub', 'github'],
    ['Google', 'google'],
  ])('continues with %s', async (label, provider) => {
    vi.mocked(firebase.signInWithProvider).mockResolvedValue(account);
    const user = userEvent.setup();
    const { router } = renderApp('/login', { signedIn: false });

    await user.click(await screen.findByRole('button', { name: `Continue with ${label}` }));

    await waitFor(() => expect(router.state.location.pathname).toBe('/'));
    expect(firebase.signInWithProvider).toHaveBeenCalledWith(provider);
    expect(readSession()).toEqual({ mode: 'firebase', user: MOCK_USER });
  });

  it.each([
    ['auth/invalid-credential', 'That email and password don’t match an account.'],
    ['auth/popup-closed-by-user', 'Sign-in was cancelled.'],
    ['claimlens/firebase-not-configured', 'Accounts aren’t set up here yet — use the live demo.'],
  ])('explains %s inline', async (code, message) => {
    vi.mocked(firebase.signInWithProvider).mockRejectedValue(firebaseError(code));
    const user = userEvent.setup();
    const { router } = renderApp('/login', { signedIn: false });

    await user.click(await screen.findByRole('button', { name: 'Continue with GitHub' }));

    expect(await screen.findByRole('status')).toHaveTextContent(message);
    expect(router.state.location.pathname).toBe('/login');
    expect(readSession()).toBeNull();
  });

  it('signs out of Firebase when the API rejects the token', async () => {
    server.use(
      http.get(apiUrl('/auth/me'), () =>
        HttpResponse.json(
          { detail: 'Firebase sign-in is not configured on the server.' },
          { status: 503 },
        ),
      ),
    );
    vi.mocked(firebase.signInWithEmail).mockResolvedValue(account);
    const user = userEvent.setup();
    renderApp('/login', { signedIn: false });

    await fillCredentials(user);
    await user.click(screen.getByRole('button', { name: 'Sign in' }));

    expect(await screen.findByRole('status')).toHaveTextContent(
      'Firebase sign-in is not configured on the server.',
    );
    expect(firebase.signOutOfFirebase).toHaveBeenCalled();
    expect(readSession()).toBeNull();
  });

  it('sends a password reset to the email typed in', async () => {
    vi.mocked(firebase.sendPasswordReset).mockResolvedValue();
    const user = userEvent.setup();
    renderApp('/login', { signedIn: false });

    await user.click(await screen.findByRole('button', { name: 'Forgot?' }));
    expect(screen.getByRole('status')).toHaveTextContent('Enter your email above');
    expect(firebase.sendPasswordReset).not.toHaveBeenCalled();

    await user.type(screen.getByLabelText('Email'), 'ada@example.edu');
    await user.click(screen.getByRole('button', { name: 'Forgot?' }));

    expect(await screen.findByRole('status')).toHaveTextContent(
      'If ada@example.edu has an account, a reset link is on its way.',
    );
    expect(firebase.sendPasswordReset).toHaveBeenCalledWith('ada@example.edu');
  });
});
