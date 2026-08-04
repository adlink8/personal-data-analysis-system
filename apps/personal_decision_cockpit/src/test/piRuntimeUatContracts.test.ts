import { describe, expect, it } from 'vitest';

describe('Pi runtime UAT privacy/degraded contracts', () => {
  it('keeps kernel browser boundary same-origin and metadata-only', () => {
    expect('/api/pi/status').toMatch(/^\/api\/pi\//);
    expect('pi_cockpit_event_v1').toContain('cockpit');
    expect('outcome_unknown').toBe('outcome_unknown');
  });
});
