# House Watch price model specification

11 November 2026. Status: reduced-feature, exact-address and dated floor-area models fitted and tested. Bedroom enrichment remains incomplete.

Owning plan: `Plans/2026-11-08-house-watch.md`. Thread: `wiki/projects/house-watch.md`.

## Question and estimand

Estimate a plausible achieved sale price for a specified house, place and valuation date. Compare that distribution with an asking price. Keep a future-market scenario distinct from a valuation at a supported historical or current date.

The core buying markets are Linslade, all of Didcot, Flitwick, Hitchin and Fleet. Training may include neighbouring markets, all supported bedroom counts and prices above the listing ceiling. An asking price is not the achieved-price outcome. A listing becoming SSTC is not a completed transaction.

## Data contract

Retain one corrected record per transaction ID, with original address components, postal town, locality, type, tenure, new-build status and source vintage. Preserve the original evidence separately from a model-ready table.

Use checked postcodes and locality evidence to assign markets. The current importer excludes Flitwick because its postal town is BEDFORD. Do not replace every BEDFORD sale with Flitwick or every LEIGHTON BUZZARD sale with Linslade. Separate core markets from comparison geography.

Collect available official history from 1995. Test recent estimation windows and time weights using training folds. EPC-era enriched models will have different coverage from the longer PPD baseline. Compare candidates on the same supported test cases as well as reporting total coverage.

Every enriched feature needs a source, observation date, measurement basis and matching confidence. Floor area, bedrooms, habitable rooms, bathrooms, parking and condition are separate variables. Missingness is evidence, not a licence to invent attributes. Current advert features cannot be assigned to earlier sales without historical support.

Prefer reliable property identifiers. The new public transaction-to-UPRN lookup has no retrospective coverage. Multiple UPRNs per sale require review. An EPC join must use a permitted identity route and respect the dated state of the building. Audit extensions, subdivided properties and repeated certificates.

## Candidate specifications

Fit a simple comparable-sale baseline and an indexed previous-sale baseline where a supported repeat-sale link exists. These establish the practical value of adding a regression.

The reduced PPD-only model uses log achieved price, supported house characteristics, place effects and time effects. It can estimate a type/location/time relationship. It cannot claim a four-bedroom-specific valuation when bedroom measurements are absent.

The enriched model is a hedonic regression of this form:

```text
log(sale price) = location effect + period effect
                + f(log floor area) + bedroom category
                + property type + tenure + new-build status
                + supported additional attributes and interactions
                + error
```

Begin with quarter effects and compare monthly effects where support permits. Choose timing granularity from training data and held-out performance. Do not select it from the locked final test.

Compare neighbourhood or postcode-sector effects with a hierarchical location model. Road effects use town, postcode and street identity together. Common street names in different towns must remain distinct. Sparse roads shrink towards their neighbourhood. Unseen roads fall back to a supported broader market and display that fallback.

Treat fully nested location effects with reference constraints or an explicit hierarchy. Do not include unrestricted redundant town, postcode and road dummy sets and interpret unstable coefficients. A property fixed effect is useful for repeat-sales research but cannot independently value an unseen property.

Consider type-by-size and local time interactions only with enough evidence and validation. Keep condition and parking adjustments unavailable when unsupported. These are predictive associations. Do not describe a coefficient as a causal renovation return or the causal value of an extra bedroom.

Use the residual distribution to estimate prediction intervals. Distinguish conditional median price from mean price. If estimating means after a log regression, fit the retransformation correction inside each training fold.

## Valuation date and forecasting

Period fixed effects describe supported periods. An unseen future quarter has no fitted fixed effect. Do not map it to a reference category or silently carry forward a price.

For recent valuations beyond mature sales evidence, test an explicit local HPI adjustment using the latest release available at the valuation date. Display the index vintage and lag. Treat the remaining unsupported period as a stated scenario or an independently evaluated forecasting component.

A user-selected future date must show the assumed market path and wider uncertainty. A conditional future scenario is not an observed future market price. Reusing HPI-adjusted prices and time effects requires a declared model target to avoid double-counting market movement.

## Evaluation

Freeze a mature recent sale period as the final test. Use earlier rolling time folds for feature choice and regularisation. Report mature-period selection and registration lag explicitly.

Use two complementary tests. Test temporal performance across properties with supported prior evidence. Also test previously unseen properties by grouping all transactions for each property. Add geographic holdouts to evaluate fallback behaviour for unseen roads and pockets. Deduplicate linked adverts before evaluating discovery or price comparisons.

Fit preprocessing, imputations, location encodings, shrinkage and retransformation within training folds. A feature, certificate, index release or comparable observed after a prediction cutoff must not enter that prediction. If historical publication vintages cannot be recovered, label revised-snapshot testing retrospective and start a saved forward test.

Report MAE in pounds, median absolute percentage error, bias, interval coverage and interval width. Break down results by town, type, size, period, feature availability and location fallback. Report sample sizes and excluded cases. Compare both errors and coverage against simple baselines. In-sample R-squared is descriptive, not release evidence.

Retain the existing plan's stricter gate for predictive bargain flags. A research estimate may be visible before that gate passes if its status, actual validation and missing features are explicit. Do not postpone every regression experiment until all attributes are complete.

## Website output

Expose the chosen model version, training cutoff, data vintage and supported geography. Show the estimated price range, asking-price difference, comparable sales and principal missing evidence. The input form must use only features the selected model actually consumes.

Provide historical sale exploration, road and market comparisons, model evaluation and source health. Keep household feedback, mailbox records and personal settings out of public exports. Decide authenticated hosting versus a public research projection before deployment.

Store fitted models, manifests, metrics and held-out predictions under `private/house-watch/models/`. Put reusable code under `tools/house-watch/`. Publish a reviewed results summary under a dated `outputs/` directory. This document does not certify that any model has been fitted or validated.


## First fitted result, 11 November 2026

The current linked-data snapshot contains 119,986 house transactions from 1995 to 2026. Standard transactions with a supported local type-specific index supply 117,822 model-supported records across all dates. The estimation window starts in 2010. Additional category B transactions and unsupported index months are excluded from modelling and retained in the research inventory.

Model choice used 1,385 January to June 2024 sales. The selected postcode-sector and road model had a selection MAE of £89,250. The quarter-effect alternative had £89,257. Selection therefore retained the simpler road model with HPI time adjustment. The quarter-effect model remains a reported candidate rather than being presented as the deployed specification.

The locked 2025 test contains 3,634 sales. The selected model had MAE £93,576, median absolute percentage error 13.1%, and mean prediction error of minus £15,608. The simple indexed market/type median had MAE £106,885. The improvement was 12.4% overall. These are revised-snapshot conditional valuations using the observed target-month HPI, not real-time forecasts.

The nominal 80% prediction interval covered 80.3% of test sales overall, with median width about £249,600. Coverage was 75.0% in Hitchin and 72.5% in its surrounding comparison area. Local calibration remains inadequate for confident house-specific claims. The reserved-property subset contained 561 sales, with MAE £93,818 and coverage 78.1%.

The final website fit uses 2010 to 2025 sales. The calculator stops at August 2026, the latest published index month. It withholds combinations with fewer than 30 training sales of the selected house type or fewer than 100 training sales across that market. Linslade combines explicit locality labels with 201 current postcodes in Leighton-Linslade West ward. This supplies 7,307 sales. It is a labelled ward proxy, with other Leighton Buzzard records retained as broader comparison context.

Results: `outputs/2026-11-11-house-watch-research/`. Reusable model and refresh code: `tools/house-watch/price_model.py`, `research_data.py`, `research_pipeline.py` and `build_research_site.py`. The public export reads only official transaction tables. Canary tests confirm that feedback, message and settings markers remain excluded. No historical bedroom model or predictive bargain flag is released.

The initial locality-only run preceded the west-ward correction. Its evaluation and held-out predictions are retained under `outputs/2026-11-11-house-watch-research/initial-locality-model/`. The correction uses postcode geography rather than test-price performance. Candidate specifications and time folds remain unchanged. The revised Linslade test has 178 sales, with MAE £65,630, median percentage error 11.4% and interval coverage 84.3%.


## Exact-address prior-sale model, 11 November 2026

The first calculator did not use a particular house's previous sale. The address extension matches postcode, street, primary address and sub-unit exactly. Similar street names and neighbouring house numbers do not merge. Unmatched addresses retain the broader area/road estimate.

For a supported earlier sale, the reference is:

```text
prior-sale reference = previous achieved price
                     × fitted current-date price / fitted previous-date price

address estimate = geometric blend of the area/road estimate
                   and this house's prior-sale reference
```

The ratio incorporates local type-specific HPI movement and supported recorded changes such as removal of an original new-build indicator. It does not add a guessed bedroom or extension premium. The previous price can retain information about the house's unmeasured size and layout at that sale. Later physical changes remain unknown.

An earlier sale must precede the target by at least 365 days. The method rejects conflicting prices on the same day, changed type/tenure and current new-build status. It uses the latest earlier sale. It does not bypass a recent flip to choose a more convenient older price. The calculator withholds this adjustment when the user flags a material alteration.

The base fit still ends in 2023 for evaluation. The prior-sale blend weight is selected from 0%, 25%, 50%, 75% and 100% using early 2024 sales. Separate age bands use their own selection data when at least 100 observations exist. Late 2024 calibrates age-specific ranges. Final test prices do not select the weights or ranges.

On 2,351 supported 2025 repeated sales, median absolute percentage error was 7.0% and MAE £53,232. The area/road model on those same houses had median error 12.9% and MAE £88,348. These subset results must not be presented as performance for every house. Age-specific nominal 80% ranges covered 79.0% overall. Hitchin coverage was only 66.4%, which the active calculator reports for that market.

Selected prior-sale weights are 75% for sales one to five years old, 100% for five to ten, and 75% for both older bands. These are predictive validation choices. They are not causal valuations of an additional room. The live model uses the production refit through 2025, while the declared errors refer to the earlier evaluation fit. All results remain retrospective revised-snapshot assessments with observed HPI inputs.

The richer model still needs dated bedrooms and floor area. A fourth-bedroom effect must control for floor area and location rather than adding a uniform cash bonus. User-entered bedroom counts alone cannot identify that coefficient. Address queries and alteration choices stay in the browser. No household preference data enter the public build.


## Dated floor-area model, 11 November 2026

Lee signed into the official EPC bulk service for a filtered domestic extract. Its 393,308 records cover five local authorities from September 2008 through October 2026. Exact address matching links 58,567 valid certificates to 43,294 distinct PPD house identities. The source CSV stays private. Published inputs retain only PPD-derived identity hashes and selected non-address certificate fields. Source addresses, contacts and account/download links are excluded.

Certificate inspection and lodgement must both precede each sale. The latest available certificate must be at most five years old and compatible with the recorded house type. Conflicting same-date measurements are rejected. Later certificates are not assigned retrospectively. This yields 39,056 dated matched sales across all supported dates. Estimation still begins in 2010.

The two declared candidates use place, tenure, build status, postcode-sector and road effects. One adds log(internal m² / 100). The other uses the same matched sample without area. Training ends in 2023 and reserves 15% of property identities. Early 2024 selects the size candidate. Late 2024 calibrates the range. There are 27,492 training sales, 936 selection sales, 1,179 calibration sales and 2,337 final 2025 test sales.

The size model has MAE £54,571 and median absolute percentage error 7.7%. The original full-sample area/road model on those same test houses has MAE £94,084 and median error 12.8%. The nominal 80% range covers 80.1%, with a median width of £149,911. The 350 reserved-property test cases have MAE £51,328, median error 7.3% and 82.0% coverage. Hitchin range coverage is only 69.5%. Results remain conditional retrospective estimates with observed target-month HPI.

The production area coefficient is 0.633 after refitting through 2025. This is a predictive size association, not a causal return to an extension. The browser withholds size estimates outside the production sample's first/99th percentile area bounds, 44 to 265 m², or with fewer than 30 matched training sales for the local/type combination. It identifies user-entered measurements separately from dated EPC evidence. The previous-sale method remains a separate comparison, rather than receiving an unvalidated additional size multiplier.

EPC habitable rooms never become bedrooms. The bedroom reference field stays in the browser and does not affect price. No historical bedroom coefficient or bathroom/condition/parking premium is fitted. A dated bedroom source remains required. The EPC snapshot is fixed at this extract until another permitted refresh is acquired. Weekly public sales/HPI refreshes can reuse this dated snapshot without account credentials.

Implementation: `property_attributes.py`, `area_model.py`, the optional attribute stage of `research_pipeline.py`, and the research website. Private full evidence: `private/house-watch/attributes-2026-11-11/`. Report: `outputs/2026-11-11-house-watch-attributes/delivery.md`.
