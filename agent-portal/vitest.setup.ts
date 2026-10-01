import "@testing-library/jest-dom/vitest";

// jsdom não implementa window.matchMedia; sem o mock componentes que usam
// matchMedia (Modal, DataTable) lançam TypeError no useEffect e o listener
// de ESC/clique-fora nunca é registrado.
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});
