import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { mockSettings } from '@/mocks/settings';
import { renderApp } from '@/test/render';

describe('CheckPage', () => {
  it('starts with an empty claim and no verdict', async () => {
    renderApp('/');

    const textarea = await screen.findByRole('textbox', { name: 'Claim' });
    expect(textarea).toHaveValue('');
    expect(screen.getByPlaceholderText('Paste a research claim…')).toBe(textarea);
    expect(
      screen.getByRole('heading', { name: 'Check a claim against the literature' }),
    ).toBeVisible();
  });

  it('checks a claim and shows the verdict, evidence and verified trace', async () => {
    const user = userEvent.setup();
    const { router } = renderApp('/');

    const textarea = await screen.findByRole('textbox', { name: 'Claim' });
    await user.type(textarea, 'LoRA matches full fine-tuning on math and coding benchmarks.');
    await user.click(screen.getByRole('button', { name: 'Check claim →' }));

    expect(await screen.findByText('Contested.')).toBeInTheDocument();
    expect(router.state.location.search).toBe('?job=job_0042');
    expect(screen.getByText('Check #0042')).toBeInTheDocument();
    expect(
      screen.getByRole('img', { name: 'Evidence balance: 3 support, 1 partial, 2 contradict' }),
    ).toBeVisible();
    expect(screen.getByRole('heading', { name: 'Supports · 3' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Contradicts · 2' })).toBeInTheDocument();
    expect(screen.getByText('6 papers read in full')).toBeInTheDocument();
    expect(screen.getByText('Semantic Embeddings · 14')).toBeInTheDocument();
    expect(screen.getByText(/31 \/ 31 quotes verified on page\./)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Re-check claim →' })).toBeInTheDocument();
    // The recent-checks row appears once there is another check to switch to.
    expect(screen.queryByRole('navigation', { name: 'Recent checks' })).not.toBeInTheDocument();
  });

  it('keeps the error and offers a retry when the check fails', async () => {
    mockSettings.failJobs = true;
    const user = userEvent.setup();
    renderApp('/');

    const textarea = await screen.findByRole('textbox', { name: 'Claim' });
    await user.type(textarea, 'LoRA matches full fine-tuning on math and coding benchmarks.');
    await user.click(screen.getByRole('button', { name: 'Check claim →' }));
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('The check stopped · UPSTREAM_ERROR');

    mockSettings.failJobs = false;
    await user.click(within(alert).getByRole('button', { name: 'Run the check again' }));
    expect(await screen.findByText('Contested.')).toBeInTheDocument();
  });

  it('opens the cited page in the evidence drawer and returns focus on Esc', async () => {
    const user = userEvent.setup();
    const { router } = renderApp('/');

    const textarea = await screen.findByRole('textbox', { name: 'Claim' });
    await user.type(textarea, 'LoRA matches full fine-tuning on math and coding benchmarks.');
    await user.click(screen.getByRole('button', { name: 'Check claim →' }));
    await screen.findByText('Contested.');

    const open = screen.getByRole('button', {
      name: 'Open page 8 of Quantized Adapters for Open Models',
    });
    await user.click(open);

    const drawer = await screen.findByRole('dialog', { name: 'Evidence viewer · [2]' });
    expect(within(drawer).getByText('Quantized Adapters for Open Models')).toBeInTheDocument();
    expect(router.state.location.search).toContain('doc=DOC002');
    expect(router.state.location.search).toContain('chunk=DOC002_CH058');

    await user.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    await waitFor(() => expect(open).toHaveFocus());
  });

  it('asks for a claim before checking', async () => {
    const user = userEvent.setup();
    renderApp('/');

    await user.click(await screen.findByRole('button', { name: 'Check claim →' }));
    expect(screen.getByRole('textbox', { name: 'Claim' })).toHaveAccessibleDescription(
      'Enter a claim to check.',
    );
  });
});
