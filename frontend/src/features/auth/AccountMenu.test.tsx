import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { MOCK_USER } from '@/mocks/handlers';
import { renderApp } from '@/test/render';
import { signOutOfFirebase } from './firebase';
import { readSession, startFirebaseSession } from './session';

vi.mock('./firebase', () => ({
  currentIdToken: vi.fn(() => Promise.resolve('id-token')),
  signOutOfFirebase: vi.fn(() => Promise.resolve()),
}));

describe('AccountMenu', () => {
  it('shows the Firebase account and signs out of Firebase too', async () => {
    startFirebaseSession(MOCK_USER);
    const user = userEvent.setup();
    const { router } = renderApp('/library', { signedIn: false });

    await user.click(await screen.findByRole('button', { name: 'Account' }));
    expect(screen.getByText('Mock Reader')).toBeInTheDocument();
    expect(screen.getByText('reader@claimlens.test')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Sign out' }));

    expect(router.state.location.pathname).toBe('/welcome');
    expect(readSession()).toBeNull();
    await waitFor(() => expect(signOutOfFirebase).toHaveBeenCalled());
  });
});
