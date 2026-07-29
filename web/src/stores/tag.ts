import { create } from 'zustand'
import { api } from '../api/client'

import { logger } from '../utils/logger';


interface TagEntry {
  id: string
  name: string
  category: string
  color?: string
  usage_count: number
}

interface TagState {
  tagCategories: Array<{ category: string; count: number }>
  tagEntries: TagEntry[]
  tagAllEntries: TagEntry[]
  loadTagCategories: () => Promise<Array<{ category: string; count: number }>>
  loadTagAllEntries: () => Promise<void>
  loadTagEntries: (category: string) => Promise<void>
}

export const useTagStore = create<TagState>((set) => ({
  tagCategories: [],
  tagEntries: [],
  tagAllEntries: [],

  loadTagCategories: async () => {
    try {
      const data = await api.listTagCategories()
      set({ tagCategories: data })
      return data
    } catch (e) {
      logger.error('Failed to load tag categories:', e)
      throw e
    }
  },

  loadTagAllEntries: async () => {
    try {
      const [allTags, categories] = await Promise.all([
        api.listTags(),
        api.listTagCategories(),
      ])
      set({ tagAllEntries: allTags, tagCategories: categories })
    } catch (e) {
      logger.error('Failed to load all tags:', e)
      throw e
    }
  },

  loadTagEntries: async (category: string) => {
    try {
      const data = await api.listTags(category)
      set({ tagEntries: data })
    } catch (e) {
      logger.error('Failed to load tags:', e)
      throw e
    }
  },
}))
