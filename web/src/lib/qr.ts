// Codici QR generati nel browser (unico punto che importa 'uqr', MIT, derivato dal generatore
// di Project Nayuki). Nessun dato lascia la pagina: il link dei canali non va a servizi esterni.
import { encode } from 'uqr'

export interface QrMatrix {
  size: number
  cells: boolean[][] // true = modulo scuro; senza bordo
}

/** Matrice del QR per il testo (correzione d'errore predefinita M). */
export function qrMatrix(text: string, ecc: 'L' | 'M' | 'Q' | 'H' = 'M'): QrMatrix {
  const r = encode(text, { ecc, border: 0 })
  return { size: r.size, cells: r.data.map((row) => row.slice()) }
}

/** Un solo path SVG: un rettangolo per ogni tratto orizzontale di moduli scuri. */
export function qrPath(m: QrMatrix, border = 4): { d: string; viewBox: string } {
  let d = ''
  for (let y = 0; y < m.size; y++) {
    const row = m.cells[y]
    let x = 0
    while (x < m.size) {
      if (!row[x]) {
        x++
        continue
      }
      let len = 1
      while (x + len < m.size && row[x + len]) len++
      d += `M${x + border} ${y + border}h${len}v1h-${len}z`
      x += len
    }
  }
  const side = m.size + 2 * border
  return { d, viewBox: `0 0 ${side} ${side}` }
}
