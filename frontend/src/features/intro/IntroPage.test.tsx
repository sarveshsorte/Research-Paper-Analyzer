import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { renderApp } from '@/test/render';

describe('IntroPage', () => {
  it('explains ClaimLens before sign-in', async () => {
    renderApp('/welcome', { signedIn: false });

    expect(
      await screen.findByRole('heading', {
        level: 1,
        name: 'Every claim, traced to the page it came from.',
      }),
    ).toBeInTheDocument();
    expect(document.title).toBe('Welcome · ClaimLens');
    expect(
      screen.getByText(/checks research claims against the scientific literature/),
    ).toBeVisible();
    expect(
      screen.getByRole('heading', { level: 2, name: /From a claim to its evidence/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { level: 2, name: 'Five ways to work with papers' }),
    ).toBeInTheDocument();
    for (const mode of ['Check', 'Library', 'Ask', 'Compare', 'Conflicts']) {
      expect(screen.getByRole('heading', { level: 3, name: mode })).toBeInTheDocument();
    }
    expect(screen.getByRole('figure', { name: 'Example check' })).toBeInTheDocument();
  });

  it('leads to sign-in from “Let’s get started” and the header', async () => {
    renderApp('/welcome', { signedIn: false });

    const getStarted = await screen.findAllByRole('link', { name: /Let’s get started/ });
    expect(getStarted).toHaveLength(2);
    for (const link of getStarted) expect(link).toHaveAttribute('href', '/login');
    expect(
      within(screen.getByRole('banner')).getByRole('link', { name: 'Sign in' }),
    ).toHaveAttribute('href', '/login');
    expect(screen.getByRole('link', { name: 'See how it works' })).toHaveAttribute(
      'href',
      '#how-it-works',
    );
  });

  it('opens the sign-in page when you get started', async () => {
    const user = userEvent.setup();
    const { router } = renderApp('/welcome', { signedIn: false });

    const [getStarted] = await screen.findAllByRole('link', { name: /Let’s get started/ });
    if (getStarted) await user.click(getStarted);

    expect(router.state.location.pathname).toBe('/login');
    expect(await screen.findByRole('button', { name: /Try the live demo/ })).toBeInTheDocument();
  });
});
