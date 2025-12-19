/**
 * React Query Hooks for Projects
 * 
 * TanStack Query hooks for fetching and mutating project data.
 * Uses Next.js API routes to proxy to the CVA backend.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { Project } from '../stores';

// Use Next.js API routes (server-side proxy to CVA backend)
const API_BASE = '';

// Query keys for cache management
export const projectKeys = {
  all: ['projects'] as const,
  lists: () => [...projectKeys.all, 'list'] as const,
  list: (filters: Record<string, unknown>) => [...projectKeys.lists(), filters] as const,
  details: () => [...projectKeys.all, 'detail'] as const,
  detail: (id: string) => [...projectKeys.details(), id] as const,
  runs: (id: string) => [...projectKeys.detail(id), 'runs'] as const,
};

// API functions - use Next.js API routes
async function fetchProjects(): Promise<Project[]> {
  // Try to fetch repo connections from CVA backend via proxy
  // Backend endpoint is /api/config/repo_connections
  const response = await fetch('/api/cva/api/config/repo_connections');
  if (!response.ok) {
    // If not available, return empty array (user hasn't connected repos yet)
    if (response.status === 404 || response.status === 502) {
      return [];
    }
    throw new Error('Failed to fetch projects');
  }
  
  // Transform repo connections to Project format
  const connections = await response.json();
  if (!Array.isArray(connections)) {
    return [];
  }
  
  return connections.map((conn: any) => ({
    id: conn.id || conn.repo_full_name,
    name: conn.repo_full_name?.split('/')[1] || 'Unknown',
    fullName: conn.repo_full_name || '',
    description: null,
    status: 'active' as const,
    lastRunAt: conn.created_at || null,
    runCount: 0,
    passRate: 0,
    lastVerdict: null,
    defaultBranch: conn.default_branch || 'main',
    language: null,
    isPrivate: false,
  }));
}

async function fetchProject(id: string): Promise<Project> {
  // For now, fetch all and find by ID
  const projects = await fetchProjects();
  const project = projects.find(p => p.id === id);
  if (!project) {
    throw new Error('Project not found');
  }
  return project;
}

async function createProject(data: {
  repositoryFullName: string;
  description?: string;
}): Promise<Project> {
  // Creating a project means importing a GitHub repo
  // This would be handled by the GitHub import flow
  // For now, return a mock that matches the expected shape
  return {
    id: data.repositoryFullName,
    name: data.repositoryFullName.split('/')[1] || 'Unknown',
    fullName: data.repositoryFullName,
    description: data.description || null,
    status: 'setup' as const,
    lastRunAt: null,
    runCount: 0,
    passRate: 0,
    lastVerdict: null,
    defaultBranch: 'main',
    language: null,
    isPrivate: false,
  };
}

async function updateProject(
  id: string,
  updates: Partial<Pick<Project, 'description' | 'status'>>
): Promise<Project> {
  // CVA backend doesn't support PATCH on repos_connections
  // For now, we fetch the project and return with updates applied locally
  const project = await fetchProject(id);
  return { ...project, ...updates };
}

async function deleteProject(id: string): Promise<void> {
  // CVA backend repos_connections endpoint handles deletion via GitHub App uninstall
  // This is a no-op for now - actual deletion happens through GitHub App settings
  console.log(`Delete requested for project ${id} - handle via GitHub App settings`);
}

// Hooks

/**
 * Fetch all projects
 */
export function useProjects() {
  return useQuery({
    queryKey: projectKeys.lists(),
    queryFn: fetchProjects,
    staleTime: 30 * 1000, // 30 seconds
    refetchOnWindowFocus: true,
  });
}

/**
 * Fetch a single project by ID
 */
export function useProject(id: string | null) {
  return useQuery({
    queryKey: projectKeys.detail(id || ''),
    queryFn: () => fetchProject(id!),
    enabled: !!id,
    staleTime: 10 * 1000, // 10 seconds
  });
}

/**
 * Create a new project
 */
export function useCreateProject() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: createProject,
    onSuccess: (newProject) => {
      // Add to cache
      queryClient.setQueryData<Project[]>(projectKeys.lists(), (old) =>
        old ? [...old, newProject] : [newProject]
      );
      // Invalidate to refetch
      queryClient.invalidateQueries({ queryKey: projectKeys.lists() });
    },
  });
}

/**
 * Update a project
 */
export function useUpdateProject() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: ({ id, updates }: { id: string; updates: Partial<Project> }) =>
      updateProject(id, updates),
    onSuccess: (updatedProject, { id }) => {
      // Update in cache
      queryClient.setQueryData(projectKeys.detail(id), updatedProject);
      queryClient.setQueryData<Project[]>(projectKeys.lists(), (old) =>
        old?.map((p) => (p.id === id ? updatedProject : p))
      );
    },
  });
}

/**
 * Delete a project
 */
export function useDeleteProject() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: deleteProject,
    onSuccess: (_, id) => {
      // Remove from cache
      queryClient.removeQueries({ queryKey: projectKeys.detail(id) });
      queryClient.setQueryData<Project[]>(projectKeys.lists(), (old) =>
        old?.filter((p) => p.id !== id)
      );
    },
  });
}
