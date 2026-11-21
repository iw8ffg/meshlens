import { listPredictions, type PredictionJob, type PredictionMeta } from './prediction'

export const prediction = $state({
  list: [] as PredictionMeta[],
  job: null as PredictionJob | null,
  shown: null as { id: string; url: string; coords: number[][] } | null,
})

export async function reloadPredictions(): Promise<void> {
  try {
    prediction.list = await listPredictions()
  } catch {
    /* elenco non aggiornato: resta quello precedente */
  }
}

/** Aggiorna il lavoro in corso; a `done` ricarica l'elenco delle previsioni salvate. */
export function applyPredictionJob(job: PredictionJob): void {
  prediction.job = job
  if (job.status === 'done') void reloadPredictions()
}
