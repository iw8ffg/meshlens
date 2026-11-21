import type { SfJob, SfRouter } from './storeforward'

export const sf = $state({ routers: [] as SfRouter[], jobs: {} as Record<string, SfJob> })

export function applySfJob(job: SfJob): void {
  sf.jobs[job.id] = job
}

export function setSfRouters(list: SfRouter[]): void {
  sf.routers = list
}
