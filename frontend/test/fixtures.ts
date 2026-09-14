/** Hand-built BoardData for component tests — one project (DLY) on an open 2026Q3. */

import type { BoardData, ServerInfo, StatusResp, Task } from "../src/types";

export function makeTask(over: Partial<Task> = {}): Task {
  return {
    period: "2026Q3",
    id: "DLY-001",
    title: "core loop",
    status: "todo",
    meta: { created_at: "2026-07-01 09:00:00", updated_at: "2026-07-01 09:00:00" },
    ...over,
  };
}

export const server: ServerInfo = {
  version: "0.16.1",
  started_at: "2026-08-31 00:00:00",
  data_root: "C:/data/fronyboard",
  projects: 1,
  open_periods: [{ project: "DLY", period: "2026Q3" }],
  api_keys: 1,
  timezone: { name: "KST", offset_minutes: 540 },
};

export function makeBoard(tasks: Task[] = []): BoardData {
  const status: StatusResp = {
    project: "DLY",
    name: "Dailying",
    overview: null,
    periods: {
      "2026Q3": {
        goal: "MVP",
        milestone_status: "active",
        task_counts: {},
        closed: false,
        open_tasks: [],
      },
    },
  };
  return {
    projects: [
      {
        key: "DLY",
        name: "Dailying",
        description: "습관 트래커",
        repo: "flash/dailying",
        status: "active",
        meta: { created_at: "2026-07-01 00:00:00", updated_at: "2026-07-01 00:00:00" },
      },
    ],
    statuses: { DLY: status },
    tasks: { DLY: tasks },
    roadmaps: {
      DLY: {
        key: "DLY",
        years: {
          "2026": {
            overview: { goal: "ship it", now: "build core", target: "validate habit" },
            milestones: { Q3: { goal: "MVP", status: "active" } },
          },
        },
      },
    },
    server,
  };
}
