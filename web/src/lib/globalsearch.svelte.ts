// Stato della finestra di ricerca globale (WP1): aperta/chiusa.
export const searchUi = $state({ open: false })

export function openGlobalSearch(): void {
  searchUi.open = true
}

export function closeGlobalSearch(): void {
  searchUi.open = false
}

export function toggleGlobalSearch(): void {
  searchUi.open = !searchUi.open
}
