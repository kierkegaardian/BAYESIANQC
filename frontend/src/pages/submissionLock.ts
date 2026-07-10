import type { Ref } from "vue";

export type SubmissionRun<T> =
  | { started: false }
  | { started: true; value: T };

export async function runWithSubmissionLock<T>(
  lock: Ref<boolean>,
  work: () => Promise<T>
): Promise<SubmissionRun<T>> {
  if (lock.value) return { started: false };
  lock.value = true;
  try {
    return { started: true, value: await work() };
  } finally {
    lock.value = false;
  }
}
