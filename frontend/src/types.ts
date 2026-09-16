export type ProjectStatus = "active" | "paused" | "archived";

export interface ProjectRef {
  key: string;
  name: string | null;
  description?: string | null;
  repo?: string | null;
  status?: ProjectStatus;
  meta?: { created_at: string; updated_at: string } | null;
}

export interface ChecklistItem {
  text: string;
  done: boolean;
}

/** v0.23.0: goal is the year in one line; now / target / checklist are the current
    year's focus blocks and may be missing (years written before then have none). */
export interface Overview {
  goal: string;
  now?: string;
  target?: string;
  checklist?: ChecklistItem[];
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

export interface OpenTask {
  id: string;
  title: string;
  status: string;
  tags?: string[];
  branch?: string;
  content?: string;
  waiting_on?: string[];
}

export interface PeriodStatus {
  goal: string | null;
  milestone_status: string | null;
  task_counts: Record<string, number>;
  closed: boolean;
  open_tasks: OpenTask[];
}

export interface StatusResp {
  project: string;
  name: string | null;
  overview: Overview | null;
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
  status: string;
  tags?: string[];
  follows?: string[];
  content?: string;
  branch?: string;
  cancel_reason?: string;
  meta: TaskMeta;
}

export interface ServerInfo {
  version: string;
  started_at: string;
  data_root: string;
  projects: number;
  open_periods: { project: string; period: string }[];
  api_keys: number | null;
  /** Absent on servers older than 0.5.2. */
  timezone?: ServerTimezone;
  /** "local" = serve --local: no credentials, loopback only. Absent on servers before 0.31. */
  auth?: "fauth" | "local";
}

export interface ServerTimezone {
  name: string | null;
  offset_minutes: number;
}

export interface KeyInfo {
  name: string;
  fingerprint: string | null;
  created_at: string;
}

/** Everything the shell loads up front and hands to the pages. */
export interface BoardData {
  projects: ProjectRef[];
  statuses: Record<string, StatusResp>;
  tasks: Record<string, Task[]>;
  roadmaps: Record<string, Roadmap>;
  server: ServerInfo;
}
