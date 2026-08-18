export interface ProjectRef {
  key: string;
  name: string | null;
}

export interface Overview {
  goal: string;
  now: string;
  next: string;
  later: string;
}

export interface Milestone {
  goal: string;
  status: "planned" | "active" | "done";
}

export interface Roadmap {
  key: string;
  name?: string;
  years: Record<string, { overview: Overview; milestones?: Record<string, Milestone> }>;
}

export interface MonthInfo {
  id: string;
  month: string;
  goal?: string;
  status: "planned" | "active" | "done";
}

export interface EpicInfo {
  id: string;
  goal: string;
  task_counts: Record<string, number>;
}

export interface PeriodStatus {
  goal: string | null;
  milestone_status: string | null;
  months: MonthInfo[];
  epics: EpicInfo[];
  task_counts: Record<string, number>;
  in_progress: string[];
}

export interface StatusResp {
  project: string;
  name: string | null;
  periods: Record<string, PeriodStatus>;
}

export interface TaskMeta {
  created_at: string;
  updated_at: string;
  started_at?: string;
  completed_at?: string;
}

export interface Task {
  period: string;
  id: string;
  title: string;
  epic: string;
  month: string;
  status: string;
  week?: number;
  content?: string;
  prd?: string;
  branch?: string;
  cancel_reason?: string;
  meta: TaskMeta;
}
