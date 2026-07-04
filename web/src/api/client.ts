import { request, getToken, setToken, clearToken } from './base';
import * as authApi from './auth';
import * as assetsApi from './assets';
import * as systemApi from './system';
import * as tagsApi from './tags'
import * as aiApi from './ai';
export type { UserInfo, AuthResponse } from './auth';
export type { Asset, SearchResult } from './assets';
export type { Library, LibrarySettings, SystemStats, MetadataFieldDef, MetadataFieldListResponse, ScanStatus } from './system';
export type { TagInfo, AssetTagInfo } from './tags';
export type { ScanJobInfo, AdminSettingValue, SystemStatus, AdminDashboard, AdminUser, AdminJob } from './logs';
 

export { getToken, setToken, clearToken, request };
export const api = {
  ...authApi,
  ...assetsApi,
  ...systemApi,
  ...tagsApi,
  ...aiApi,
};
