import { describe, expect, it } from "vitest";
import { cloudAt, cloudDays, isCloudy, probablyHiddenFire } from "./clouds";

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

  it("marks a fire seen the day before and after, cloudy in between, as probably hidden", () => {
    const fire = { days_since_last: 1, cloud: { day: 0.9, night: 0.6 }, seenNextDay: true };
    expect(probablyHiddenFire(fire, 0.5)).toBe(true);
    expect(probablyHiddenFire(fire, 0.7)).toBe(false);                               // night not cloudy enough
    expect(probablyHiddenFire({ ...fire, seenNextDay: false }, 0.5)).toBe(false);    // not seen again
    expect(probablyHiddenFire({ ...fire, seenNextDay: null }, 0.5)).toBe(false);     // newest day: no day after yet
    expect(probablyHiddenFire({ ...fire, days_since_last: 0 }, 0.5)).toBe(false);    // seen today
  });

  it("lists the cloud cover of every day of a range", () => {
    const days = cloudDays(series, "2025-08-01", "2025-08-04", 0.2);
    expect(days.map((d) => d?.cover ?? null)).toEqual([0.8, 0.2, 0.1, null]);
    expect(days.map((d) => d?.cloudy ?? null)).toEqual([true, true, false, null]);
    const withFires = cloudDays(series, "2025-08-01", "2025-08-03", 0.5, [null, 0.6, 0.4]);
    expect(withFires.map((d) => d?.hiddenFire)).toEqual([false, true, false]);   // a fire hidden only where cloudy enough
    expect(days[3]).toBeNull();                                       // no cloud data that day
  });
});
