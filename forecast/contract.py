"""Output contract with the frontend (must match forecast/README.md, section 4)."""

DAILY_COLUMNS = ["region_id", "issue_date", "target_date", "lead_days", "p_big_fire_day", "p_fire_day",
                 "p_clim_big_fire_day", "p_clim_fire_day", "risk_ratio", "risk_class", "p_big_fire_day_lo",
                 "p_big_fire_day_hi", "source", "model_version"]

WEEKLY_COLUMNS = ["region_id", "issue_date", "week_start", "week_ahead", "p_below", "p_normal", "p_above",
                  "expected_big_fire_days", "clim_big_fire_days", "source", "model_version"]

SKILL_COLUMNS = ["product", "target", "lead", "region_id", "bss_vs_climatology", "ci_lo", "ci_hi", "auc", "pr_auc",
                 "ece", "hit_rate", "false_alarm_ratio", "n_events", "use_model", "skill_basis"]

RISK_CLASSES = ["low", "normal", "elevated", "high", "very_high"]
SOURCES = ["model", "climatology"]


def risk_class(p, ratio, cfg: dict):
    """Risk class from probability p and ratio p / p_clim (vectorised, numpy arrays).

    Rules (config risk_class): by ratio low < r_low <= normal < r_elevated <= elevated < r_high <= high < r_very_high
    <= very_high; p >= p_high gives at least high, p >= p_very_high very_high; p < p_floor caps the class at normal
    (a tiny probability is never shown as elevated just because it is several times the seasonal value).
    """
    import numpy as np
    p, ratio = np.asarray(p, float), np.asarray(ratio, float)
    lvl = np.select([ratio >= cfg["ratio_very_high"], ratio >= cfg["ratio_high"], ratio >= cfg["ratio_elevated"],
                     ratio >= cfg["ratio_low"]], [4, 3, 2, 1], default=0)
    lvl = np.where(p >= cfg["p_high"], np.maximum(lvl, 3), lvl)
    lvl = np.where(p >= cfg["p_very_high"], 4, lvl)
    lvl = np.where(p < cfg["p_floor"], np.minimum(lvl, 1), lvl)
    return np.array(RISK_CLASSES, dtype=object)[lvl]
