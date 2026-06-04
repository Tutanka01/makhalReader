import apiClient from '../apiClient'
import type { Source } from '../types'

export async function fetchSources(): Promise<Source[]> {
  return apiClient.get<Source[]>('/api/sources')
}

export async function subscribeSource(id: number): Promise<void> {
  await apiClient.post(`/api/sources/${id}/subscribe`)
}

export async function unsubscribeSource(id: number): Promise<void> {
  await apiClient.del(`/api/sources/${id}/subscribe`)
}
