import { ref } from "vue";
import { describe, expect, it, vi } from "vitest";
import { runWithSubmissionLock } from "./submissionLock";

describe("runWithSubmissionLock", () => {
  it("does not start a second submission while the first is pending", async () => {
    const lock = ref(false);
    let release!: () => void;
    const pending = new Promise<void>((resolve) => { release = resolve; });
    const work = vi.fn(async () => pending);
    const first = runWithSubmissionLock(lock, work);
    const second = await runWithSubmissionLock(lock, work);
    expect(second).toEqual({ started: false });
    expect(work).toHaveBeenCalledTimes(1);
    release();
    await first;
    expect(lock.value).toBe(false);
  });

  it("releases the lock when submission fails", async () => {
    const lock = ref(false);
    await expect(runWithSubmissionLock(lock, async () => { throw new Error("network"); })).rejects.toThrow("network");
    expect(lock.value).toBe(false);
  });
});
