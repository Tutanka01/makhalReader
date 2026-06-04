import apiClient from '../apiClient'
import type { Source, DiscoveredItem } from '../types'

export async function fetchSources(): Promise<Source[]> {
  return apiClient.get<Source[]>('/api/sources')
}

export async function createSource(item: DiscoveredItem): Promise<Source> {
  return apiClient.post<Source>('/api/sources', {
    name: item.name,
    provider: item.provider,
    query_json: JSON.stringify(item.query_json),
    label: item.label || null,
    category: 'Discovery',
  })
}

export async function subscribeSource(id: number): Promise<void> {
  await apiClient.post(`/api/sources/${id}/subscribe`)
}

export async function unsubscribeSource(id: number): Promise<void> {
  await apiClient.del(`/api/sources/${id}/subscribe`)
}
