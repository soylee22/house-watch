# House Watch price model specification

11 November 2026. Status: specified, not fitted.

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
