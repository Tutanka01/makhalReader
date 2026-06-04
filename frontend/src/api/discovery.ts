import apiClient from '../apiClient'
import type { ExpandResult, DiscoveryPack, DiscoveredItem } from '../types'

export interface ExistingSubscriptions {
  source_canonical_ids: string[]
  venue_names: string[]
  author_openalex_ids: string[]
  author_names: string[]
}

export async function runExpand(thesisText: string, signal?: AbortSignal): Promise<ExpandResult> {
  return apiClient.post<ExpandResult>('/api/discovery/expand', { thesis_text: thesisText }, signal)
}

export async function runResolve(expandResult: ExpandResult, signal?: AbortSignal): Promise<DiscoveryPack> {
  return apiClient.post<DiscoveryPack>('/api/discovery/resolve', { expand_result: expandResult }, signal)
}

export interface ApplyRequest {
  sources: DiscoveredItem[]
  venues: DiscoveredItem[]
  authors: DiscoveredItem[]
}

export interface ApplyResponse {
  applied: boolean
  counts: Record<string, number>
}

export async function applyDiscoveryPack(pack: ApplyRequest): Promise<ApplyResponse> {
  return apiClient.post<ApplyResponse>('/api/discovery/apply', pack)
}

export async function getExistingSubscriptions(): Promise<ExistingSubscriptions> {
  return apiClient.get<ExistingSubscriptions>('/api/discovery/existing')
}
