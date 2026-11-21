import { formatMeters } from './geo'
import type { CoverageCheck, CoverageMode, CoverageSession } from './types'

export interface ChecklistItem {
  key: 'radio' | 'mobile' | 'gps' | 'precision' | 'rangetest'
  ok: boolean | null
  label: string
  hint: string
}

/** Passi guidati della preparazione, con stato: true ok, false problema, null non ancora noto. */
export function checklist(check: CoverageCheck | null, mode: CoverageMode): ChecklistItem[] {
  const c = check
  const items: ChecklistItem[] = [
    {
      key: 'radio',
      ok: c ? c.radio_connected : null,
      label: 'Radio di base collegata',
      hint: c && !c.radio_connected ? 'Collega la radio di base dalla scheda Radio.' : '',
    },
    {
      key: 'mobile',
      ok: c ? c.mobile_known : null,
      label: 'Nodo mobile sentito',
      hint: c && !c.mobile_known ? 'Accendi il nodo mobile e attendi che la base lo senta.' : '',
    },
    {
      key: 'gps',
      ok: c ? c.gps_ok : null,
      label: 'Posizione GPS recente (≤ 10 min)',
      hint: c && !c.gps_ok ? 'Serve il GPS acceso e la posizione attiva sul nodo mobile.' : '',
    },
  ]
  let precOk: boolean | null = null
  let precLabel = 'Precisione della posizione'
  let precHint = ''
  if (c) {
    if (c.precision_m !== null) {
      precOk = false
      precLabel += `: circa ± ${formatMeters(c.precision_m)}`
      precHint = 'Per una mappa precisa usa un canale privato con precisione piena.'
    } else if (c.precision_bits !== null) {
      precOk = true
      precLabel += ': esatta'
    }
  }
  items.push({ key: 'precision', ok: precOk, label: precLabel, hint: precHint })
  if (mode === 'rangetest') {
    items.push({
      key: 'rangetest',
      ok: c ? c.rangetest_age_s !== null : null,
      label: 'Pacchetti Range Test ricevuti',
      hint:
        c && c.rangetest_age_s === null
          ? 'Attiva il modulo Range Test sul nodo mobile (mittente ogni 30 s) e sulla base (ricevitore).'
          : '',
    })
  }
  return items
}

/** Intervallo ammesso dal server: intero tra 10 e 600 secondi. */
export function validInterval(n: unknown): n is number {
  return typeof n === 'number' && Number.isInteger(n) && n >= 10 && n <= 600
}

/** Perdita pacchetti in percentuale ("6,7%"), "—" se non disponibile. */
export function formatLoss(s: CoverageSession | number | null): string {
  const v = s !== null && typeof s === 'object' ? s.loss_pct : s
  if (v === null || v === undefined || !Number.isFinite(v)) return '—'
  return `${v.toFixed(1).replace('.', ',')}%`
}
