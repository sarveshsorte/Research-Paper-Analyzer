import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { renderApp } from '@/test/render';

describe('app routes', () => {
  it.each([
    ['/', 'Check', 'Check a claim'],
    ['/library', 'Library', 'Library'],
    ['/ask', 'Ask', 'What do you want to know?'],
    ['/compare', 'Compare', 'Compare'],
    ['/conflicts', 'Conflicts', 'Where the papers disagree'],
  ])('renders %s inside the app layout with its nav item active', async (path, nav, heading) => {
    renderApp(path);

    expect(await screen.findByRole('heading', { level: 1, name: heading })).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: 'Main' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: nav })).toHaveAttribute('aria-current', 'page');
    expect(document.title).toBe(`${nav} · ClaimLens`);
  });

  it('sends visitors without a session to the intro page first', async () => {
    const { router } = renderApp('/library', { signedIn: false });

    expect(
      await screen.findByRole('heading', {
        level: 1,
        name: 'Every claim, traced to the page it came from.',
      }),
    ).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/welcome');
    expect(screen.queryByRole('navigation', { name: 'Main' })).not.toBeInTheDocument();
  });

  it('goes intro → login → demo and returns to the page asked for, by keyboard', async () => {
    const user = userEvent.setup();
    const { router } = renderApp('/library', { signedIn: false });

    const [getStarted] = await screen.findAllByRole('link', { name: /Let’s get started/ });
    getStarted?.focus();
    await user.keyboard('{Enter}');
    expect(
      await screen.findByRole('heading', { level: 2, name: 'Open your evidence desk' }),
    ).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/login');

    screen.getByRole('button', { name: /Try the live demo/ }).focus();
    await user.keyboard('{Enter}');

    expect(await screen.findByRole('heading', { level: 1, name: 'Library' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/library');
  });

  it('answers the sign-in stub inline, not with an alert', async () => {
    const user = userEvent.setup();
    renderApp('/login', { signedIn: false });

    await user.click(await screen.findByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('status')).toHaveTextContent(
      'Use Google sign-in or the live demo.',
    );
  });

  it('signs out from the account menu', async () => {
    const user = userEvent.setup();
    const { router } = renderApp('/library');

    await user.click(await screen.findByRole('button', { name: 'Account' }));
    await user.click(screen.getByRole('button', { name: 'Sign out' }));
    expect(router.state.location.pathname).toBe('/welcome');
  });

  it('moves the active nav state when navigating', async () => {
    const user = userEvent.setup();
    const { router } = renderApp('/');

    await user.click(await screen.findByRole('link', { name: 'Library' }));

    expect(await screen.findByRole('heading', { level: 1, name: 'Library' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/library');
    expect(screen.getByRole('link', { name: 'Library' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('link', { name: 'Check' })).not.toHaveAttribute('aria-current');
  });

  it('serves the dev-only component kit at /_kit', async () => {
    renderApp('/_kit');

    // The lazy route pulls in every component; the first import can take over the default 1s.
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Component kit' }, { timeout: 5000 }),
    ).toBeInTheDocument();
  });

  it('shows a not-found page for unknown paths', async () => {
    renderApp('/nope');

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Page not found' }),
    ).toBeInTheDocument();
  });
});
