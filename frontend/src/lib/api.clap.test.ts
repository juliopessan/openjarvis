import { afterEach, describe, expect, it, vi } from 'vitest';

const invoke = vi.fn();
vi.mock('@tauri-apps/api/core', () => ({ invoke }));

async function loadApi() {
  vi.resetModules();
  return await import('./api');
}

// The suite runs under node (no jsdom): stub the minimal `window` that
// `isTauri()` inspects.
function setDesktop(on: boolean) {
  const g = globalThis as unknown as { window?: { __TAURI_INTERNALS__?: object } };
  if (on) g.window = { __TAURI_INTERNALS__: {} };
  else delete g.window;
}

afterEach(() => {
  invoke.mockReset();
  setDesktop(false);
});

describe('clap listener bridge', () => {
  it('is off and inert outside the desktop app', async () => {
    const { getClapListener, setClapListener } = await loadApi();

    expect(await getClapListener()).toBe(false);
    await expect(setClapListener(true)).rejects.toThrow(/desktop app only/);
    expect(invoke).not.toHaveBeenCalled();
  });

  it('forwards the toggle to Tauri and returns the real running state', async () => {
    setDesktop(true);
    invoke.mockResolvedValueOnce(true).mockResolvedValueOnce(false);
    const { getClapListener, setClapListener } = await loadApi();

    expect(await setClapListener(true)).toBe(true);
    expect(invoke).toHaveBeenLastCalledWith('set_clap_listener', { enabled: true });
    expect(await getClapListener()).toBe(false);
    expect(invoke).toHaveBeenLastCalledWith('get_clap_listener');
  });

  it('surfaces the backend error message', async () => {
    setDesktop(true);
    invoke.mockRejectedValueOnce(new Error('OpenJarvis project folder not found.'));
    const { setClapListener } = await loadApi();

    await expect(setClapListener(true)).rejects.toThrow(/project folder not found/);
  });
});
