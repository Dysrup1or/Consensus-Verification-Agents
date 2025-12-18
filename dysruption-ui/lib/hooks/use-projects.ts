/**
 * React Query Hooks for Projects
 * 
 * TanStack Query hooks for fetching and mutating project data.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { Project } from '../stores';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// Query keys for cache management
export const projectKeys = {
  all: ['projects'] as const,
  lists: () => [...projectKeys.all, 'list'] as const,
  list: (filters: Record<string, unknown>) => [...projectKeys.lists(), filters] as const,
  details: () => [...projectKeys.all, 'detail'] as const,
  detail: (id: string) => [...projectKeys.details(), id] as const,
  runs: (id: string) => [...projectKeys.detail(id), 'runs'] as const,
};

// API functions
async function fetchProjects(): Promise<Project[]> {
  const response = await fetch(`${API_BASE}/api/projects`);
  if (!response.ok) {
    throw new Error('Failed to fetch projects');
  }
  return response.json();
}

async function fetchProject(id: string): Promise<Project> {
  const response = await fetch(`${API_BASE}/api/projects/${id}`);
  if (!response.ok) {
    throw new Error('Failed to fetch project');
  }
  return response.json();
}

async function createProject(data: {
  repositoryFullName: string;
  description?: string;
}): Promise<Project> {
  const response = await fetch(`${API_BASE}/api/projects`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    throw new Error('Failed to create project');
  }
  return response.json();
}

async function updateProject(
  id: string,
  updates: Partial<Pick<Project, 'description' | 'status'>>
): Promise<Project> {
  const response = await fetch(`${API_BASE}/api/projects/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  });
  if (!response.ok) {
    throw new Error('Failed to update project');
  }
  return response.json();
}

async function deleteProject(id: string): Promise<void> {
  const response = await fetch(`${API_BASE}/api/projects/${id}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    throw new Error('Failed to delete project');
  }
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
