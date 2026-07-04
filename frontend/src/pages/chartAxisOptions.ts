import type * as echarts from "echarts";

export type BrokenAxisRange = {
  min: number;
  max: number;
};

export function buildOutlierAxis(values: number[]): BrokenAxisRange | null {
  if (!values.length) {
    return null;
  }
  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);
  const fallbackSpan = Math.max(Math.abs(maxValue), Math.abs(minValue), 1) * 0.02;
  const span = Math.max(Math.abs(maxValue - minValue), fallbackSpan);
  const pad = span * 0.1;
  return { min: minValue - pad, max: maxValue + pad };
}

export function formatBrokenAxisTick(value: string | number): string {
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) {
    return String(value);
  }
  return numericValue.toLocaleString(undefined, {
    maximumFractionDigits: Math.abs(numericValue) >= 100 ? 1 : 2,
  });
}

export function buildBrokenOutlierYAxis(
  range: BrokenAxisRange | null | undefined,
  isKiosk: boolean
): echarts.YAXisComponentOption {
  return {
    type: "value",
    name: "",
    min: range?.min,
    max: range?.max,
    splitNumber: isKiosk ? 2 : 3,
    axisLabel: {
      hideOverlap: true,
      margin: 6,
      formatter: formatBrokenAxisTick,
    },
  };
}

export function buildBrokenMainYAxis(
  yAxis: echarts.YAXisComponentOption,
  isKiosk: boolean
): echarts.YAXisComponentOption {
  return {
    ...yAxis,
    name: "",
    splitNumber: isKiosk ? 3 : 4,
    axisLabel: {
      hideOverlap: true,
      margin: 6,
      formatter: formatBrokenAxisTick,
    },
  };
}
