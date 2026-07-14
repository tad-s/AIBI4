import { useEffect, useRef } from "react";
import * as echarts from "echarts";
import type { EChartsOption } from "echarts";

export function EChart({
  option, height = 260, onClick,
}: {
  option: EChartsOption;
  height?: number;
  onClick?: (params: any) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null);
  const clickRef = useRef(onClick);
  clickRef.current = onClick;

  useEffect(() => {
    if (!ref.current) return;
    chart.current = echarts.init(ref.current, undefined, { renderer: "canvas" });
    chart.current.on("click", (p: any) => clickRef.current?.(p));
    const ro = new ResizeObserver(() => chart.current?.resize());
    ro.observe(ref.current);
    return () => { ro.disconnect(); chart.current?.dispose(); };
  }, []);

  useEffect(() => {
    chart.current?.setOption(option, true);
  }, [option]);

  return <div ref={ref} style={{ width: "100%", height, cursor: onClick ? "pointer" : "default" }} />;
}
