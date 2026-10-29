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

  it('sends visitors without a session to /welcome', async () => {
    const { router } = renderApp('/library', { signedIn: false });

    expect(
      await screen.findByRole('heading', { level: 1, name: /Every claim, traced to/ }),
    ).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/welcome');
    expect(screen.queryByRole('navigation', { name: 'Main' })).not.toBeInTheDocument();
  });

  it('opens sign-in modal from welcome and starts the demo session', async () => {
    const user = userEvent.setup();
    const { router } = renderApp('/library', { signedIn: false });

    const signInButtons = await screen.findAllByRole('button', { name: /Sign in/ });
    const firstButton = signInButtons[0];
    expect(firstButton).toBeDefined();
    await user.click(firstButton!);

    const demo = await screen.findByRole('button', { name: /Try the live demo/ });
    demo.focus();
    await user.keyboard('{Enter}');

    expect(await screen.findByRole('heading', { level: 1, name: 'Library' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/library');
  });

  it('answers the sign-in stub inline, not with an alert', async () => {
    const user = userEvent.setup();
    renderApp('/login', { signedIn: false });

    await user.click(await screen.findByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('status')).toHaveTextContent(
      'Accounts are coming soon — use the demo.',
    );
  });

  it('signs out from the account menu to /welcome', async () => {
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
