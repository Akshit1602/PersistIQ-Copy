import React, { createContext, useContext, useState, useEffect, type ReactNode } from 'react';
import { fetchExperiments, type Experiment } from '../services/api';

export interface Project {
  id: string;
  projectId: string;
  name: string;
  status: string;
  primaryMetric: string;
  sampleSize: number;
  srmStatus: string;
  updatedAt: string;
}

interface MatchViewContextType {
  projects: Project[];
  activeProject: Project | null;
  setActiveProject: (project: Project | null) => void;
  isLoadingProjects: boolean;
  refreshProjects: () => Promise<void>;
}

const MatchViewContext = createContext<MatchViewContextType | undefined>(undefined);

export const MatchViewProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProject, setActiveProject] = useState<Project | null>(null);
  const [isLoadingProjects, setIsLoadingProjects] = useState<boolean>(true);

  const loadProjects = async () => {
    setIsLoadingProjects(true);
    try {
      const data: Experiment[] = await fetchExperiments();
      
      const mappedProjects: Project[] = data.map((exp: any) => ({
        id: exp.experiment_id,
        projectId: exp.project_id || `prj_${exp.experiment_id}`,
        name: exp.name,
        status: exp.status,
        primaryMetric: exp.primary_metric,
        sampleSize: exp.sample_size,
        srmStatus: exp.srm_status,
        updatedAt: 'Just now',
      }));

      setProjects(mappedProjects);
      if (mappedProjects.length > 0 && !activeProject) {
        setActiveProject(mappedProjects[0]);
      }
    } catch (err) {
      console.warn('Backend not running or experiments fetch failed, using empty array:', err);
      setProjects([]);
    } finally {
      setIsLoadingProjects(false);
    }
  };

  useEffect(() => {
    loadProjects();
  }, []);

  return (
    <MatchViewContext.Provider
      value={{
        projects,
        activeProject,
        setActiveProject,
        isLoadingProjects,
        refreshProjects: loadProjects,
      }}
    >
      {children}
    </MatchViewContext.Provider>
  );
};

export const useMatchView = () => {
  const context = useContext(MatchViewContext);
  if (!context) {
    throw new Error('useMatchView must be used within a MatchViewProvider');
  }
  return context;
};