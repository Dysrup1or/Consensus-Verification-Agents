/**
 * Project Card Grid Component
 * 
 * Displays projects in a responsive grid layout.
 */

'use client';

import { useProjectsStore, type Project } from '@/lib/stores';
import { ProjectCard } from './ProjectCard';

export function ProjectCardGrid() {
  const filteredProjects = useProjectsStore((state) => state.getFilteredProjects());
  
  if (filteredProjects.length === 0) {
    return (
      <div className="text-center py-12">
        <p className="text-[var(--color-text-muted)]">
          No projects match your filters
        </p>
      </div>
    );
  }
  
  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
      {filteredProjects.map((project) => (
        <ProjectCard key={project.id} project={project} />
      ))}
    </div>
  );
}
