import { jobText, type SfJob, type SfRouter } from './storeforward'

export const sf = $state({
  routers: [] as SfRouter[],
  jobs: {} as Record<string, SfJob>,
  /** Avviso di recupero concluso: sopravvive alla chiusura della finestra e lo mostra Radios. */
  notice: '',
})

const notified = new Set<string>()

export function applySfJob(job: SfJob): void {
  sf.jobs[job.id] = job
  if (job.status === 'done' && !notified.has(job.id)) {
    notified.add(job.id)
    sf.notice = jobText(job)
  }
}

export function setSfRouters(list: SfRouter[]): void {
  sf.routers = list
}

export function clearSfNotice(): void {
  sf.notice = ''
}

/** Carica i lavori noti al server (senza avvisi) e restituisce quello ancora attivo per la radio, se c'e'. */
export function adoptSfJobs(list: SfJob[], radioId: string): string | null {
  for (const j of list) sf.jobs[j.id] = j
  return activeJobFor(list, radioId)?.id ?? null
}

function activeJobFor(list: SfJob[], radioId: string): SfJob | null {
  return list.find((j) => j.radio_id === radioId && (j.status === 'waiting' || j.status === 'receiving')) ?? null
}
