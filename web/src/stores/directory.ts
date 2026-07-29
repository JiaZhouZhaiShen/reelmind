import { create } from 'zustand'
import { api } from '../api/client'

import { logger } from '../utils/logger';


interface DirTreeNode {
  name: string
  depth: number
  children?: DirTreeNode[]
}

interface DirectoryState {
  dirTree: DirTreeNode[]
  dirTreeLoading: boolean
  dirSubdirs: string[]
  loadDirTree: (libraryId?: string) => Promise<void>
  setDirSubdirs: (paths: string[]) => void
}

export const useDirectoryStore = create<DirectoryState>((set) => ({
  dirTree: [],
  dirTreeLoading: false,
  dirSubdirs: [],

  loadDirTree: async (libraryId?: string) => {
    set({ dirTreeLoading: true })
    try {
      const data = await api.directoryTree(libraryId)
      set({ dirTree: data as DirTreeNode[] })
    } catch (e) {
      logger.error('Failed to load directory tree:', e)
      throw e
    } finally {
      set({ dirTreeLoading: false })
    }
  },

  setDirSubdirs: (paths) => {
    set({ dirSubdirs: paths })
  },
}))
