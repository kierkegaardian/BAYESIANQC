import { describe, expect, it, vi } from "vitest";
import { useChartPointSelection } from "./useChartPointSelection";

describe("chart point selection", () => {
  it("opens the point dialog only for interactive result series", () => {
    const interaction = vi.fn();
    const selection = useChartPointSelection(interaction);
    selection.handleChartClick({
      seriesName: "Result",
      data: { value: ["2026-01-01T00:00:00Z", 100], record_id: 7 },
    } as never);
    expect(selection.dialogOpen.value).toBe(true);
    expect(selection.selectedPoint.value?.record_id).toBe(7);
    expect(interaction).toHaveBeenCalledWith(true);
    selection.setDialogOpen(false);
    expect(interaction).toHaveBeenLastCalledWith(false);
  });
});
