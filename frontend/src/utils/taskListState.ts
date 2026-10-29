export function shouldShowTaskListEmpty(
  loading: boolean,
  error: string,
  taskCount: number,
): boolean {
  return !loading && !error && taskCount === 0;
}

export function taskById<T extends { task_id: string }>(tasks: T[], taskId: string): T | null {
  return tasks.find((task) => task.task_id === taskId) ?? null;
}
