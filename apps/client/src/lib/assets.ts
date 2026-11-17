export function asset(path: string): string {
  // Vite's base includes the repository name on GitHub Pages.
  return `${import.meta.env.BASE_URL || '/'}static/${path.replace(/^\//, '')}`
}
