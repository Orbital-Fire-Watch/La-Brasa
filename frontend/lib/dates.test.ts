import { describe, expect, it } from "vitest";
import { addDays, dateFromDayOfYear, dayOfYear, daysBetween, isIsoDate, shiftYears } from "./dates";

describe("dates", () => {
  it("shifts Feb 29 to Feb 28 in non-leap years", () => {
    expect(shiftYears("2024-02-29", -1)).toBe("2023-02-28");
    expect(shiftYears("2025-08-14", -10)).toBe("2015-08-14");
  });

  it("aligns calendar days across leap years", () => {
    expect(dayOfYear("2023-03-01")).toBe(60);
    expect(dayOfYear("2024-03-01")).toBe(60);
    expect(dayOfYear("2024-12-31")).toBe(365);
    expect(dateFromDayOfYear(2024, 60)).toBe("2024-03-01");
    expect(dateFromDayOfYear(2023, 1)).toBe("2023-01-01");
  });

  it("counts days in UTC", () => {
    expect(daysBetween("2025-08-08", "2025-08-14")).toBe(6);
    expect(addDays("2024-12-31", 1)).toBe("2025-01-01");
  });

  it("validates ISO dates", () => {
    expect(isIsoDate("2025-02-29")).toBe(false);
    expect(isIsoDate("2024-02-29")).toBe(true);
    expect(isIsoDate("14.08.2025")).toBe(false);
  });
});
