# Our insights and the research behind them

Overview of the MODIS → VIIRS harmonisation in `harmonisation/`: what we found and which research papers support it.

We found the insights in our own data (`harmonisation/data_analysis/`). The papers show the same effect elsewhere or
justify the method. Each description starts with how well the paper fits:

- **Confirms:** the paper reports the same effect, often with a similar number.
- **Consistent:** the paper points the same way but measures something slightly different.
- **Method:** the paper is the standard source for a method we use.
- **Own finding:** no paper found. Here the evidence is our own validation (KPIs in `data/harmonised/kpi_report.json`).

All numbers are for Iberia, vegetation fires only (`type` = 0), calibration window 02/2012–12/2021.
Bibliographic data of all papers was checked against Crossref. Papers marked † were only read as an abstract or summary; read the full text before relying on details.

The same overview as PDF: `insights_and_sources.pdf` (source `insights_and_sources.tex`, `references.bib`).

---

## 1. Sensors: why MODIS and VIIRS differ

| Our insight | Supporting paper | Short description |
|---|---|---|
| VIIRS SNPP reports 6.0× as many detections as Aqua, ≈ 3.0× as many as Aqua + Terra (by day 4.1×, at night 11×). | Vadrevu & Lasko 2018 | **Confirms:** VIIRS detected 6.5× as many fires as Aqua MODIS in an agricultural region of India. |
| VIIRS sees many more small fires because of its 375 m pixels. | Schroeder et al. 2014 | **Confirms:** describes the VIIRS 375 m algorithm; it detects far more fire pixels than the coarser 750 m product, especially at night. |
| The difference is *which* fires are detected: Aqua detects a VIIRS fire cluster with 50 % probability only from ≈ 34 MW (day) / 21 MW (night). Aqua sees 24 % of the clusters but 83 % of the FRP. | Giglio, Schroeder & Justice 2016; Schroeder et al. 2008; Sofiev & Kouznetsov 2026 † | **Consistent:** MODIS detection probability depends mainly on fire size; detection limit 3.7 MW (night, nadir) up to 40 MW (day, off-nadir). Our 50 % point in MW is our own fit. |
| The daily FRP sum is comparable between sensors (SNPP/Aqua ≈ 1.04); the factor does not transfer worldwide (0.9–3.3). | Li, Zhang, Kondragunta & Csiszar 2018; Li et al. 2020 † | **Confirms:** FRP of fire clusters is very comparable, differences ≈ 20 % on a 1° grid and they vary by region; in Africa MODIS daily FRP is ≥ 42.8 % too low. |
| Single-pixel FRP is not comparable (a VIIRS pixel is 0.45× as strong as a MODIS pixel of the same fire). Only sums are. | Li et al. 2018; Zheng et al. 2026 † | **Consistent:** per-pixel FRP differs between sensors, MODIS FRP depends strongly on the view angle. Zheng et al. build a view-angle correction for MODIS FRP. |
| `brightness` is not comparable: the VIIRS channel saturates at 367 K (14 % of day detections sit exactly on this value). Dropped. | Schroeder et al. 2014 | **Confirms:** names saturation of the middle-infrared channel as a known limitation of VIIRS. |
| VIIRS confidence "h" only means "saturated" (all h rows are at 367 K); MODIS confidence rises with brightness. Classes are not comparable. | – | **Own finding.** Fits the saturation note in Schroeder et al. 2014, but no paper says it directly. |
| Overpass time matters: fires burn strongest in the afternoon, so Aqua/SNPP (≈ 13:30) and Terra (≈ 10:30) see different amounts. FRP before 2012 therefore comes from Aqua alone (H1). | Giglio, Csiszar & Justice 2006; Freeborn, Wooster & Roberts 2011; Andela et al. 2015 | **Confirms:** strong diurnal fire cycle; polar orbiters see only snapshots of it, and the overpass time changes what is measured. |
| Orbit drift: Aqua flies over at ≈ 14:53 instead of 13:05 local time in 2026 (+108 min), Terra 9:21 instead of 11:01 (−101 min). SNPP stable. Therefore no MODIS after 2021. | Giglio 2025 (NASA LANCE slides) | **Consistent:** confirms the dates (Terra's last manoeuvre 2022, Aqua's 2021) and the effect on diurnal sampling. The impact on fire products is "under active investigation". **Our measured drift in minutes is our own number.** |
| Two identical VIIRS instruments (NOAA-20 vs. SNPP) differ by × 1.18–1.27 per 1° cell and month. The mean of all active VIIRS satellites hits a held-out satellite better than any single one (N3). | Csiszar 2018 (NOAA/NESDIS slides) †; Zhou et al. 2023 † | **Consistent:** overpasses ≈ 50 min apart, no perfect agreement expected; FRP of SNPP and NOAA-20 consistent overall. The size of the noise floor and the benefit of the mean are our own result. |

## 2. Data cleaning

| Our insight | Supporting paper | Short description |
|---|---|---|
| Static sources (industry, flares) are 32 % of SNPP night detections but only 4 % for Aqua. They distort the sensor comparison and are removed via `type`. | Giglio, Schroeder & Justice 2016; FIRMS `type` documentation | **Method:** `type` separates vegetation fires from static land sources and offshore sources. The 32 % vs. 4 % is our own number. |
| In the NRT data `type` is missing. A location mask learned from the archive replaces it (recall ≈ 93 %, 1.5 % real fires removed). | FIRMS 2025 (Static Thermal Anomalies); Ma et al. 2020 †; Gao, Sun & Miao 2026 † | **Consistent:** static sources are found through persistence at the same place over years (FIRMS: 400 m grid, ≥ 5 detections in one year). Our thresholds and quality numbers are our own. |

## 3. Calibration (MODIS → VIIRS equivalent)

| Our insight | Supporting paper | Short description |
|---|---|---|
| The factor is the sum of VIIRS divided by the sum of MODIS over the whole window, not the mean of daily ratios. | Cochran 1977 †; Gregoire & Salas 2009 | **Method:** the ratio of sums (ratio estimator) is much less biased than the mean of ratios, and days with 0 MODIS detections cause no division by 0. |
| The factor differs by region (2.5–5.1 against Aqua + Terra) but is stable over the years, because the typical fire size differs by region. | Li et al. 2018 | **Consistent:** the MODIS–VIIRS relationship varies between regions and spatial scales. |
| Simple beats complex: of 17 conversions tested (factors per month, day/night, Poisson models, gradient boosting, quantile mapping, FRP-class weights), one factor per region hit the VIIRS class best (64 %). | Hand 2006 † | **Consistent:** general argument that simple models often do as well as complex ones on new data. **The comparison itself is our own.** |
| A sensor change must not show up as a jump in the series (without conversion the mean would seem to jump 2.2× in 2012). | Venema et al. 2012 | **Method:** homogenisation of climate time series after instrument changes; the established framework for our problem. |
| Related approach from the literature. | Zheng et al. 2026 † | **Consistent:** fuses Aqua MODIS and SNPP VIIRS FRP (2012–2024) with corrections. FRP only, no detection counts, no Iberian region factors. Closest competitor to compare against. |

## 4. Error model and aggregation

| Our insight | Supporting paper | Short description |
|---|---|---|
| The 0.25° grid is too fine for comparison: R² (log) 0.37 per cell and month, 0.73 per NUTS-2 and month, 0.89 per year. The error shrinks with area and time step (day × 2.08, month × 1.5, year × 1.12). | Openshaw 1984 †; Li et al. 2018 | **Consistent:** results depend on the size of the aggregation unit (modifiable areal unit problem); the MODIS–VIIRS relationship changes with spatial scale. Our error per scale is our own measurement. |
| The error depends on the size of the number: × 3.0 at 0, × 2.3 at 1–5, × 1.14 above 500. A fixed factor (× 1.46) would be far too optimistic for small numbers. | Gehrels 1986 † | **Method:** counting statistics; random counts scatter by about √n, so the relative error is large for small counts. |
| Before 2012, MODIS reports nothing on ≈ 60 % of region days on which VIIRS sees fire. A 0 before 2012 often only means "MODIS saw nothing". | Li et al. 2020 † | **Consistent:** MODIS misses many low-intensity fires. The 60 % is our own number. |
| Big fire days (FRP sum ≥ 100 MW per region and day): MODIS finds 62–67 %; the extreme class (≥ 500 MW) is right in 72–76 %. Medium days are poor. | Sofiev & Kouznetsov 2026 †; Giglio et al. 2016 | **Consistent:** MODIS detects powerful fires with ≈ 78 % probability worldwide; detection rises with fire size. |
| Climatology: the converted MODIS seasonal profile matches VIIRS with R² 0.94 after smoothing over ±7 days, only 0.75 without. | Giglio, Csiszar & Justice 2006; Zhang et al. 2005 † | **Consistent:** Terra and Aqua agree well on peak month and season length; a window around each calendar day is the standard way to stabilise day-of-year statistics. The ±7 days is our own choice from the test. |

## 5. Evaluation methods

| Our insight | Supporting paper | Short description |
|---|---|---|
| Leave-one-year-out cross-validation; bands fitted on one half of the years and checked on the other. | Roberts et al. 2017 | **Method:** with time-dependent data, random cross-validation is too optimistic; blocking by time (here: by year) is the right choice. |
| Error given as a factor, exp(\|log(prediction / measurement)\|) (e.g. D1 "× 2.08"). | Morley, Brito & Welling 2018 | **Method:** log accuracy ratio and median symmetric accuracy, a symmetric error measure for data that spans orders of magnitude. |
| Bands must hold their promise: the 50 % band contains the measurement in ≈ 50 % of cases, the 90 % band in ≈ 90 % (U1, U2). | Gneiting, Balabdaoui & Raftery 2007; Lei et al. 2018 † | **Method:** calibration of probabilistic predictions; empirical quantiles on held-out data correspond to split conformal prediction. |
| Agreement of classes (month class, big fire day) measured with Cohen's kappa. | Cohen 1960 †; Pontius & Millones 2011 | **Method, with caveat:** kappa is standard but contested in remote sensing; Pontius & Millones recommend also reporting quantity and allocation disagreement. |

---

## References

- Andela, N., Kaiser, J. W., van der Werf, G. R., Wooster, M. J. (2015). New fire diurnal cycle characterizations to improve fire radiative energy assessments made from MODIS observations. *Atmospheric Chemistry and Physics* 15:8831–8846. https://doi.org/10.5194/acp-15-8831-2015
- Cochran, W. G. (1977). *Sampling Techniques*, 3rd ed., ch. 6 (ratio estimators). Wiley.
- Cohen, J. (1960). A coefficient of agreement for nominal scales. *Educational and Psychological Measurement* 20:37–46. https://doi.org/10.1177/001316446002000104
- Csiszar, I. (2018). VIIRS active fire products, NOAA/NESDIS presentation slides (exact title not checked). https://satelliteaqpg.psu.edu/files/2018/10/Csiszar-1ce9uxi.pdf
- FIRMS / NASA Earthdata (2025). FIRMS Releases New Features to Identify Active Fires by Type. https://www.earthdata.nasa.gov/news/blog/firms-releases-new-features-identify-active-fires-type
- Freeborn, P. H., Wooster, M. J., Roberts, G. (2011). Addressing the spatiotemporal sampling design of MODIS to provide estimates of the fire radiative energy emitted from Africa. *Remote Sensing of Environment* 115:475–489. https://doi.org/10.1016/j.rse.2010.09.017
- Gao, H., Sun, L., Miao, R. (2026). A PFM/SHM-aware spatiotemporal contextual fire detection and adaptive thresholding framework for VIIRS 375 m data. *Remote Sensing* 18:904. https://doi.org/10.3390/rs18060904
- Gehrels, N. (1986). Confidence limits for small numbers of events in astrophysical data. *The Astrophysical Journal* 303:336. https://doi.org/10.1086/164079
- Giglio, L. (2025). Terra/Aqua orbit-drift update. NASA LANCE User Working Group, May 2025. https://landweb.modaps.eosdis.nasa.gov/data/filePost/LANCE_UWG_Orbit_Drift_Giglio_202505.pdf
- Giglio, L., Csiszar, I., Justice, C. O. (2006). Global distribution and seasonality of active fires as observed with the Terra and Aqua MODIS sensors. *JGR: Biogeosciences* 111:G02016. https://doi.org/10.1029/2005JG000142
- Giglio, L., Schroeder, W., Justice, C. O. (2016). The collection 6 MODIS active fire detection algorithm and fire products. *Remote Sensing of Environment* 178:31–41. https://doi.org/10.1016/j.rse.2016.02.054
- Gneiting, T., Balabdaoui, F., Raftery, A. E. (2007). Probabilistic forecasts, calibration and sharpness. *Journal of the Royal Statistical Society B* 69:243–268. https://doi.org/10.1111/j.1467-9868.2007.00587.x
- Gregoire, T. G., Salas, C. (2009). Ratio estimation with measurement error in the auxiliary variate. *Biometrics* 65:590–598. https://doi.org/10.1111/j.1541-0420.2008.01110.x
- Hand, D. J. (2006). Classifier technology and the illusion of progress. *Statistical Science* 21:1–14. https://doi.org/10.1214/088342306000000060
- Lei, J., G'Sell, M., Rinaldo, A., Tibshirani, R. J., Wasserman, L. (2018). Distribution-free predictive inference for regression. *JASA* 113:1094–1111. https://doi.org/10.1080/01621459.2017.1307116
- Li, F., Zhang, X., Kondragunta, S., Csiszar, I. (2018). Comparison of fire radiative power estimates from VIIRS and MODIS observations. *JGR: Atmospheres* 123:4545–4563. https://doi.org/10.1029/2017JD027823
- Li, F., Zhang, X., Kondragunta, S. (2020). Biomass burning in Africa: an investigation of fire radiative power missed by MODIS using the 375 m VIIRS active fire product. *Remote Sensing* 12:1561. https://doi.org/10.3390/rs12101561
- Ma, Y. et al. (2020). Spatial-temporal distribution analysis of industrial heat sources in the US with geocoded, tree-based, large-scale clustering. *Remote Sensing* 12:3069. https://doi.org/10.3390/rs12183069
- Morley, S. K., Brito, T. V., Welling, D. T. (2018). Measures of model performance based on the log accuracy ratio. *Space Weather* 16:69–88. https://doi.org/10.1002/2017SW001669
- Openshaw, S. (1984). *The Modifiable Areal Unit Problem*. CATMOG 38, Geo Books, Norwich.
- Pontius, R. G., Millones, M. (2011). Death to Kappa: birth of quantity disagreement and allocation disagreement for accuracy assessment. *International Journal of Remote Sensing* 32:4407–4429. https://doi.org/10.1080/01431161.2011.552923
- Roberts, D. R. et al. (2017). Cross-validation strategies for data with temporal, spatial, hierarchical, or phylogenetic structure. *Ecography* 40:913–929. https://doi.org/10.1111/ecog.02881
- Schroeder, W. et al. (2008). Validation of GOES and MODIS active fire detection products using ASTER and ETM+ data. *Remote Sensing of Environment* 112:2711–2726. https://doi.org/10.1016/j.rse.2008.01.005
- Schroeder, W., Oliva, P., Giglio, L., Csiszar, I. A. (2014). The new VIIRS 375 m active fire detection data product: algorithm description and initial assessment. *Remote Sensing of Environment* 143:85–96. https://doi.org/10.1016/j.rse.2013.12.008
- Sofiev, M., Kouznetsov, R. (2026). Observation operator and detection limits for MODIS and VIIRS fire radiative power products. *Geoscientific Model Development* 19:10123–10142. https://doi.org/10.5194/gmd-19-10123-2026
- Vadrevu, K., Lasko, K. (2018). Intercomparison of MODIS AQUA and VIIRS I-band fires and emissions in an agricultural landscape. *Remote Sensing* 10:978. https://doi.org/10.3390/rs10070978
- Venema, V. K. C. et al. (2012). Benchmarking homogenization algorithms for monthly data. *Climate of the Past* 8:89–115. https://doi.org/10.5194/cp-8-89-2012
- Wooster, M. J. et al. (2021). Satellite remote sensing of active fires: history and current status, applications and future requirements. *Remote Sensing of Environment* 267:112694. https://doi.org/10.1016/j.rse.2021.112694
- Zhang, X., Hegerl, G., Zwiers, F. W., Kenyon, J. (2005). Avoiding inhomogeneity in percentile-based indices of temperature extremes. *Journal of Climate* 18:1641–1651. https://doi.org/10.1175/JCLI3366.1
- Zheng, Y. et al. (2026). Fire radiative power correction and spatiotemporal fusion based on MYD14 and VNP14IMG. *Remote Sensing* 18:1650. https://doi.org/10.3390/rs18101650
- Zhou, M. et al. (2023). Enhancement of nighttime fire detection and combustion efficiency characterization using Suomi-NPP and NOAA-20 VIIRS instruments. *IEEE TGRS* 61:1–20. https://doi.org/10.1109/TGRS.2023.3261664
