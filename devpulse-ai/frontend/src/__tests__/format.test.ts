import { fmtDate, fmtSeconds, statusTone } from "../format";

describe("format", () => {
  it("formats dates without timezone drift", () => {
    expect(fmtDate("2026-10-27")).toBe("27/10/2026");
    expect(fmtDate(null)).toBe("—");
  });
  it("formats durations", () => {
    expect(fmtSeconds(45)).toBe("45s");
    expect(fmtSeconds(75)).toBe("1min15s");
  });
  it("maps statuses to tones", () => {
    expect(statusTone("sent")).toBe("ok");
    expect(statusTone("failed_auth")).toBe("bad");
    expect(statusTone("needs_review")).toBe("warn");
  });
});
