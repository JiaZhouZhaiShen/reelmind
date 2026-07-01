import { request } from './base';
import type { TagInfo, AssetTagInfo } from './client';

export function listTags(category?: string, search?: string): Promise<TagInfo[]> {
  const params = new URLSearchParams();
  if (category) params.set('category', category);
  if (search) params.set('search', search);
  const qs = params.toString();
  return request(`/tags${qs ? `?${qs}` : ''}`);
}
export function getTag(id: string): Promise<TagInfo> {
  return request(`/tags/${id}`);
}
export function createTag(data: { name: string; category?: string; color?: string }): Promise<TagInfo> {
  return request('/tags', { method: 'POST', body: JSON.stringify(data) });
}
export function updateTag(id: string, data: Partial<TagInfo>): Promise<TagInfo> {
  return request(`/tags/${id}`, { method: 'PUT', body: JSON.stringify(data) });
}
export function deleteTag(id: string): Promise<{ status: string }> {
  return request(`/tags/${id}`, { method: 'DELETE' });
}
export function getAssetTags(assetId: string): Promise<AssetTagInfo[]> {
  return request(`/tags/assets/${assetId}`);
}
export function addTagsToAsset(assetId: string, tagIds: string[]): Promise<{ status: string; tags_added: number }> {
  return request(`/tags/assets/${assetId}`, { method: 'POST', body: JSON.stringify({ tag_ids: tagIds }) });
}
export function addTagByNameToAsset(assetId: string, tagName: string, category?: string): Promise<{ status: string; tags_added: number }> {
  return request(`/tags/assets/${assetId}`, { method: 'POST', body: JSON.stringify({ tag_name: tagName, category: category || 'general', source: 'manual' }) });
}
export function removeTagFromAsset(assetId: string, tagId: string): Promise<{ status: string }> {
  return request(`/tags/assets/${assetId}/tags/${tagId}`, { method: 'DELETE' });
}
export function autoGenerateTags(assetId?: string): Promise<{ results: Array<{ asset_id: string; tags_added: number; tags: string[] }>; total: number }> {
  return request('/tags/auto-generate', { method: 'POST', body: JSON.stringify({ asset_id: assetId }) });
}
export function suggestTagsForAsset(assetId: string): Promise<{ tags: Array<{ name: string; category: string; confidence: number }> }> {
  return request(`/tags/assets/${assetId}/suggest`);
}
export function batchDeleteTags(tagIds: string[]): Promise<{ status: string; count: number }> {
  return request('/tags/batch-delete', { method: 'POST', body: JSON.stringify({ tag_ids: tagIds }) });
}
export function getAutoTagIds(): Promise<{ auto_tag_ids: string[] }> {
  return request('/tags/auto-ids');
}
export function listTagCategories(): Promise<Array<{ category: string; count: number }>> {
  return request('/tags/categories');
}
