// Global test setup: jest-dom matchers + cleanup between tests.
import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

// Node 22+ exposes globalThis.localStorage as undefined without --localstorage-file.
// Ensure window.localStorage always points to a working Storage mock in tests.
if (typeof window !== 'undefined') {
  let store = {};
  if (typeof Storage !== 'undefined') {
    Storage.prototype.getItem = function (key) { return (key in store ? store[key] : null); };
    Storage.prototype.setItem = function (key, value) { store[key] = String(value); };
    Storage.prototype.removeItem = function (key) { delete store[key]; };
    Storage.prototype.clear = function () { store = {}; };
    Object.defineProperty(Storage.prototype, 'length', {
      get() { return Object.keys(store).length; },
      configurable: true,
    });
    Storage.prototype.key = function (index) { return Object.keys(store)[index] || null; };
  }
  const storageInstance = typeof Storage !== 'undefined'
    ? Object.create(Storage.prototype)
    : {};
  try {
    if (!window.localStorage || typeof window.localStorage.clear !== 'function') {
      Object.defineProperty(window, 'localStorage', {
        value: storageInstance,
        configurable: true,
        writable: true,
      });
    }
  } catch {
    window.localStorage = storageInstance;
  }
  if (typeof globalThis.localStorage === 'undefined') {
    try {
      Object.defineProperty(globalThis, 'localStorage', {
        value: window.localStorage,
        configurable: true,
        writable: true,
      });
    } catch { /* ignore */ }
  }
}

afterEach(() => {
  cleanup()
  try {
    window.localStorage?.clear?.()
  } catch {
    /* jsdom teardown edge — nothing to clear */
  }
})
