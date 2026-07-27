import { beforeEach, describe, expect, it } from 'vitest';
import { render } from '@testing-library/react';
import { AppProviders } from '../app/providers';

describe('browser privacy boundary', () => {
  beforeEach(() => localStorage.clear());

  it('persists only the two documented UI preference keys', () => {
    render(<AppProviders><div>fixture</div></AppProviders>);
    const keys = Object.keys(localStorage).sort();
    expect(keys).toEqual(['cockpit.density', 'cockpit.theme']);
    expect(keys.some((key) => /actor|preview|hmac|message|payload|session|authority/i.test(key))).toBe(false);
  });
});
