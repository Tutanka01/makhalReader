import apiClient from '../apiClient'
import type { ExpandResult, DiscoveryPack } from '../types'

export async function runExpand(thesisText: string, signal?: AbortSignal): Promise<ExpandResult> {
  return apiClient.post<ExpandResult>('/api/discovery/expand', { thesis_text: thesisText }, signal)
}

export async function runResolve(expandResult: ExpandResult, signal?: AbortSignal): Promise<DiscoveryPack> {
  return apiClient.post<DiscoveryPack>('/api/discovery/resolve', { expand_result: expandResult }, signal)
}
