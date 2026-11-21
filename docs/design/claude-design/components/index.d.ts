/** Funzioni di supporto esposte da window.MeshLens (documentazione, non sono componenti React). */
declare namespace MeshLens {
  /** SVG a tratto di 1,75 px su griglia 24; `name` è uno di `iconNames`. */
  function icon(name: string, size?: number): string;
  const iconNames: string[];
  /** Numeri in formato italiano: num(3.59, 2) → "3,59". */
  function num(n: number, decimals?: number): string;
  /** Numero con segno tipografico: signed(-3.5, 1) → "−3,5". */
  function signed(n: number, decimals?: number): string;
  /** Età relativa: ago(12) → "12 min fa". */
  function ago(minutes: number): string;
  /** Monta una schermata di esempio in #root con i comandi Vista, Tema, Stato. */
  function mountScreen(id: "accesso" | "mappa" | "nodi" | "nodo" | "rete" | "chat" | "copertura" | "radio" | "configura" | "impostazioni"): void;
}
