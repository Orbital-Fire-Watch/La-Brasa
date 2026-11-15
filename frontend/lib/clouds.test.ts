import { describe, expect, it } from "vitest";
import { cloudAt, cloudDays, isCloudy, probablyHidden } from "./clouds";

const series = {
  start: "2025-08-01",
  cloud_day: [0.9, 0.9, 0.1, null, 0.8],
  cloud_night: [0.8, 0.2, 0.1, null, null],
};

describe("clouds", () => {
  it("reads the cloud cover of a day", () => {
    expect(cloudAt(series, "2025-08-01")).toEqual({ day: 0.9, night: 0.8 });
    expect(cloudAt(series, "2025-08-04")).toBeNull();            // no cloud data
    expect(cloudAt(series, "2025-09-01")).toBeNull();            // outside the series
    expect(cloudAt({ start: "2025-08-01" }, "2025-08-01")).toBeNull();   // backend without cloud data
  });

  it("is cloudy only when both passes are covered", () => {
    expect(isCloudy(cloudAt(series, "2025-08-01"), 0.7)).toBe(true);
    expect(isCloudy(cloudAt(series, "2025-08-02"), 0.7)).toBe(false);   // clear at night
    expect(isCloudy(cloudAt(series, "2025-08-05"), 0.7)).toBe(false);   // night unknown
    expect(isCloudy(cloudAt(series, "2025-08-02"), 0.2)).toBe(true);    // the threshold is a parameter
  });

  it("marks a cloudy empty day between two fire days as probably hidden", () => {
    const daily = { ...series, fires: [2, 0, 3, 0, 1] };
    expect(probablyHidden(daily, "2025-08-02", 0.2)).toBe(true);
    expect(probablyHidden(daily, "2025-08-02", 0.7)).toBe(false);    // not cloudy enough at night
    expect(probablyHidden({ ...daily, fires: [0, 0, 3, 0, 1] }, "2025-08-02", 0.2)).toBe(false);   // no fire the day before
    expect(probablyHidden(daily, "2025-08-05", 0.2)).toBe(false);    // last day: no day after yet
  });

  it("lists the cloud cover of every day of a range", () => {
    const days = cloudDays({ ...series, fires: [2, 0, 3, 0, 1] }, "2025-08-01", "2025-08-04", 0.2);
    expect(days.map((d) => d?.cover ?? null)).toEqual([0.8, 0.2, 0.1, null]);
    expect(days.map((d) => d?.hidden ?? null)).toEqual([false, true, false, null]);
    expect(days[3]).toBeNull();                                       // no cloud data that day
  });
});
