/**
 * Projects Store
 * 
 * Zustand store for managing the project list and selection state.
 */

import { create } from 'zustand';

export type ProjectStatus = 'active' | 'paused' | 'error' | 'setup';
export type VerdictStatus = 'pass' | 'fail' | 'partial' | 'pending' | 'veto';

export interface Project {
  id: string;
  name: string;
  fullName: string;
  description: string | null;
  status: ProjectStatus;
  lastRunAt: string | null;
  runCount: number;
  passRate: number;
  lastVerdict: VerdictStatus | null;
  defaultBranch: string;
  language: string | null;
  isPrivate: boolean;
}

export interface ProjectsState {
  // Project list
  projects: Project[];
  isLoading: boolean;
  error: string | null;
  
  // Selected project
  selectedProjectId: string | null;
  
  // Filters
  statusFilter: ProjectStatus | 'all';
  searchQuery: string;
  sortBy: 'name' | 'lastRunAt' | 'passRate';
  sortOrder: 'asc' | 'desc';
  
  // Actions
  setProjects: (projects: Project[]) => void;
  addProject: (project: Project) => void;
  updateProject: (id: string, updates: Partial<Project>) => void;
  removeProject: (id: string) => void;
  setSelectedProject: (id: string | null) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  setStatusFilter: (status: ProjectStatus | 'all') => void;
  setSearchQuery: (query: string) => void;
  setSortBy: (sortBy: 'name' | 'lastRunAt' | 'passRate') => void;
  toggleSortOrder: () => void;
  
  // Computed selectors
  getFilteredProjects: () => Project[];
  getSelectedProject: () => Project | undefined;
}

export const useProjectsStore = create<ProjectsState>((set, get) => ({
  // Initial state
  projects: [],
  isLoading: false,
  error: null,
  selectedProjectId: null,
  statusFilter: 'all',
  searchQuery: '',
  sortBy: 'lastRunAt',
  sortOrder: 'desc',

  // Actions
  setProjects: (projects) => set({ projects, error: null }),
  
  addProject: (project) => set((state) => ({
    projects: [...state.projects, project],
  })),
  
  updateProject: (id, updates) => set((state) => ({
    projects: state.projects.map((p) =>
      p.id === id ? { ...p, ...updates } : p
    ),
  })),
  
  removeProject: (id) => set((state) => ({
    projects: state.projects.filter((p) => p.id !== id),
    selectedProjectId: state.selectedProjectId === id ? null : state.selectedProjectId,
  })),
  
  setSelectedProject: (id) => set({ selectedProjectId: id }),
  
  setLoading: (loading) => set({ isLoading: loading }),
  
  setError: (error) => set({ error }),
  
  setStatusFilter: (status) => set({ statusFilter: status }),
  
  setSearchQuery: (query) => set({ searchQuery: query }),
  
  setSortBy: (sortBy) => set({ sortBy }),
  
  toggleSortOrder: () => set((state) => ({
    sortOrder: state.sortOrder === 'asc' ? 'desc' : 'asc',
  })),

  // Computed selectors
  getFilteredProjects: () => {
    const { projects, statusFilter, searchQuery, sortBy, sortOrder } = get();
    
    let filtered = projects;
    
    // Filter by status
    if (statusFilter !== 'all') {
      filtered = filtered.filter((p) => p.status === statusFilter);
    }
    
    // Filter by search query
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter(
        (p) =>
          p.name.toLowerCase().includes(query) ||
          p.fullName.toLowerCase().includes(query) ||
          (p.description && p.description.toLowerCase().includes(query))
      );
    }
    
    // Sort
    filtered = [...filtered].sort((a, b) => {
      let comparison = 0;
      
      switch (sortBy) {
        case 'name':
          comparison = a.name.localeCompare(b.name);
          break;
        case 'lastRunAt':
          comparison = (a.lastRunAt || '').localeCompare(b.lastRunAt || '');
          break;
        case 'passRate':
          comparison = a.passRate - b.passRate;
          break;
      }
      
      return sortOrder === 'asc' ? comparison : -comparison;
    });
    
    return filtered;
  },
  
  getSelectedProject: () => {
    const { projects, selectedProjectId } = get();
    return projects.find((p) => p.id === selectedProjectId);
  },
}));
