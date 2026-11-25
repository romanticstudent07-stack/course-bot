// Тесты отправителя очереди пауз (miniapp-pause-c1, T5-C1): client.ts подменён через vi.mock.

import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

import { beforeEach, describe, expect, it, vi } from 'vitest';

import * as client from '../api/client.ts';
import { buildPauseQueueDeps, sendPauseOp } from './pauseSend.ts';
import type { PauseQueueStore, PauseSlot } from './pauseQueueStore.ts';

vi.mock('../api/client.ts', async (importOriginal) => {
  const orig = await importOriginal<typeof import('../api/client.ts')>();
  return {
    ...orig,
    postPauseRequest: vi.fn(async () => ({ pause: { id: 1 } })),
    postPauseCancel: vi.fn(async () => ({ status: 'accepted' })),
    postPauseResume: vi.fn(async () => ({ status: 'accepted' })),
    readTgUserId: vi.fn(() => null),
  };
});

const slot = (kind: PauseSlot['kind'], args: PauseSlot['args'], opId: string): PauseSlot => ({
  ownerId: '42', kind, args, opId, phase: 'uncertain', attempt: 0, notBefore: 0, savedAt: 0,
});

describe('pauseSend', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('три вида операций → нужный postPause* с opId и args слота', async () => {
    const reqArgs = { days: 3, start_date: '2026-12-01' };
    await sendPauseOp(slot('request', reqArgs, 'op-r'));
    await sendPauseOp(slot('cancel', { pause_id: 7 }, 'op-c'));
    await sendPauseOp(slot('resume', { pause_id: 8 }, 'op-s'));
    expect(vi.mocked(client.postPauseRequest).mock.calls).toEqual([[reqArgs, 'op-r']]);
    expect(vi.mocked(client.postPauseCancel).mock.calls).toEqual([[{ pause_id: 7 }, 'op-c']]);
    expect(vi.mocked(client.postPauseResume).mock.calls).toEqual([[{ pause_id: 8 }, 'op-s']]);
  });

  it('по исходнику: postPause* есть только в client.ts и pauseSend.ts', () => {
    const src = fileURLToPath(new URL('..', import.meta.url));
    const files: string[] = [];
    const walk = (dir: string): void => {
      for (const name of readdirSync(dir)) {
        const p = join(dir, name);
        if (statSync(p).isDirectory()) walk(p);
        else if (/\.(ts|tsx)$/.test(name) && !/\.test\.(ts|tsx)$/.test(name)) files.push(p);
      }
    };
    walk(src);
    const found = files
      .filter((p) => /postPause(Request|Cancel|Resume)/.test(readFileSync(p, 'utf8')))
      .map((p) => relative(src, p).split('\\').join('/'))
      .sort();
    expect(found).toEqual(['api/client.ts', 'components/pauseSend.ts']);
  });

  it('getOwnerId: null → null, число → строка', () => {
    const deps = buildPauseQueueDeps({ store: {} as PauseQueueStore, onOutcome: () => undefined });
    vi.mocked(client.readTgUserId).mockReturnValueOnce(null);
    expect(deps.getOwnerId()).toBeNull();
    vi.mocked(client.readTgUserId).mockReturnValueOnce(123456);
    expect(deps.getOwnerId()).toBe('123456');
  });
});
