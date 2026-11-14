import { describe, expect, it } from "vitest";
import { addDays, daysBetween } from "./dates";
import {
  movingAverage, periodCells, periodRange, seasonPhase, windowAnomaly, windowSum, yearSeries, type DailySeries,
} from "./analysis";

/** Series from 2015-01-01 to 2025-12-31 with 1 per day, and 10 per day in 2025-08-08..14. */
function makeDaily(): DailySeries {
  const start = "2015-01-01";
  const end = "2025-12-31";
  const n = daysBetween(start, end) + 1;
  const fires = Array.from({ length: n }, (_, i) => {
    const d = addDays(start, i);
    return d >= "2025-08-08" && d <= "2025-08-14" ? 10 : 1;
  });
  return { start, end, fires, hotspots: fires, frp_sum: fires };
}

describe("windowSum", () => {
  it("returns null when a day is missing or outside", () => {
    expect(windowSum([1, 2, null, 4], "2025-01-01", "2025-01-01", "2025-01-02")).toBe(3);
    expect(windowSum([1, 2, null, 4], "2025-01-01", "2025-01-01", "2025-01-03")).toBeNull();
    expect(windowSum([1, 2], "2025-01-01", "2024-12-31", "2025-01-01")).toBeNull();
  });
});

describe("windowAnomaly", () => {
  it("compares the window with the same window in other years", () => {
    const a = windowAnomaly(makeDaily(), "fires", "2025-08-08", "2025-08-14");
    expect(a?.value).toBe(70);
    expect(a?.median).toBe(7);
    expect(a?.factor).toBe(10);
    expect(a?.rank).toBe(1);
    expect(a?.rank_of).toBe(11);
  });

  it("limits to the N most recent years before the window", () => {
    const a = windowAnomaly(makeDaily(), "fires", "2025-08-08", "2025-08-14", 3);
    expect(a?.history.map((h) => h.year)).toEqual([2022, 2023, 2024]);
  });

  it("gives no factor when the median is 0", () => {
    const d = makeDaily();
    d.fires = d.fires.map((v) => (v === 10 ? 10 : 0));
    const a = windowAnomaly(d, "fires", "2025-08-08", "2025-08-14");
    expect(a?.factor).toBeNull();
    expect(a?.diff).toBe(70);
  });
});

describe("seasonPhase", () => {
  const curve = Array.from({ length: 365 }, (_, i) => Math.exp(-((i + 1 - 220) ** 2) / (2 * 20 ** 2)));

  it("finds the phases around the peak", () => {
    expect(seasonPhase(curve, "2025-01-15").phase).toBe("pre_season");
    expect(seasonPhase(curve, "2025-07-25").phase).toBe("rising");
    expect(seasonPhase(curve, "2025-08-08").phase).toBe("peak");
    expect(seasonPhase(curve, "2025-09-01").phase).toBe("declining");
    expect(seasonPhase(curve, "2025-12-01").phase).toBe("post_season");
    expect(seasonPhase(curve, "2025-07-25").daysToPeak).toBe(14);
  });

  it("detects a secondary spring season", () => {
    const twoPeaks = curve.map((v, i) => v + 0.6 * Math.exp(-((i + 1 - 75) ** 2) / (2 * 15 ** 2)));
    expect(seasonPhase(twoPeaks, "2025-03-01").secondaryPeakDoy).toBe(75);
    expect(seasonPhase(curve, "2025-03-01").secondaryPeakDoy).toBeNull();
  });

  it("handles areas without fires", () => {
    expect(seasonPhase(new Array(365).fill(0), "2025-08-01").phase).toBe("no_season");
  });
});

describe("year helpers", () => {
  it("drops Feb 29 in yearSeries", () => {
    const s = yearSeries(makeDaily(), "fires", 2024);
    expect(s).toHaveLength(365);
    expect(s.every((v) => v === 1)).toBe(true);
  });

  it("keeps gaps in the moving average", () => {
    expect(movingAverage([1, 2, null, 4, 5], 3)).toEqual([1.5, 1.5, null, 4.5, 4.5]);
  });

  it("uses fixed day-of-year weeks", () => {
    expect(periodRange(2025, 0, "week")).toEqual(["2025-01-01", "2025-01-07"]);
    expect(periodRange(2024, 51, "week")).toEqual(["2024-12-23", "2024-12-31"]);
    expect(periodRange(2025, 1, "month")).toEqual(["2025-02-01", "2025-02-28"]);
  });

  it("marks running and incomplete cells", () => {
    const d = makeDaily();
    d.end = "2025-08-14";
    d.fires = d.fires.slice(0, daysBetween(d.start, d.end) + 1);
    d.fires[daysBetween(d.start, "2025-03-15")] = null;
    const cells = periodCells(d, "fires", "month").filter((c) => c.year === 2025);
    expect(cells[2].status).toBe("incomplete");
    expect(cells[7].status).toBe("running");
    expect(cells[8].status).toBe("nodata");
    expect(cells[0].value).toBe(31);
  });
});
