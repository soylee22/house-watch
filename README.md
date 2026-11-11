# House Watch public research

Public historical house-price research for Didcot, Fleet, Flitwick, Hitchin and Linslade, with separately labelled surrounding markets.

The website explores official completed sales from 1995 onwards. Its experimental model compares location, postcode-sector and road effects with simpler baselines. Local house-type HPI data supply the time adjustment. The evaluation includes a residual quarter-effect candidate, which was not selected on the declared validation period.

## Run

The public repository uses `app/` for the reviewed application and `research-inputs/` for reproducible official snapshots.

```sh
python -m pip install -r app/requirements-research.txt
python -m unittest discover -s app -p 'test_research.py' -v
python app/research_pipeline.py --inputs research-inputs --docs docs
python -m http.server 8784 --directory docs
```

Use `--refresh` on the pipeline to acquire current official snapshots. The GitHub workflow refreshes sources and the website each Monday at 07:37 Europe/London. GitHub can delay scheduled starts. Manual runs can rebuild the saved snapshot without downloading again.

## Evidence and limits

The first snapshot contains 119,986 D/S/T transactions, including additional transaction categories. Standard transactions with a supported HPI value enter model research. The final test contains 3,634 sales from 2025. Model choice uses early 2024, and interval calibration uses late 2024. The test period does not choose the specification.

The selected reduced-feature model has a median absolute percentage error of 13.1% and a mean absolute error of about £93,600. The nominal 80% interval covers 80.3% of test transactions overall. Coverage varies by market. The revised-data evaluation uses the observed target-month HPI and is not a real-time forecasting backtest.

Bedrooms, floor area, condition and parking are missing. Price estimates therefore describe broad location/type evidence. They are not bedroom-adjusted valuations. No predictive bargain flag is released. Linslade uses explicit locality labels plus a frozen list of 201 postcodes in Leighton-Linslade West ward. The current postcode centroid defines this geographic proxy. Other Leighton Buzzard records remain separately labelled context. Unresolved and newly created postcodes need review.

Household shortlists, feedback, mailbox records and recipient settings are excluded from this repository and website. The public exporter reads only official sales and their geographic classification. It has no access to household state during GitHub runs.

## Sources

- [Price Paid Data](https://www.gov.uk/government/statistical-data-sets/price-paid-data-downloads)
- [Official linked-data service](https://landregistry.data.gov.uk/)
- [UK House Price Index](https://www.gov.uk/government/collections/uk-house-price-index-reports)
- [Postcodes.io data definitions](https://postcodes.io/docs/overview/)
- [ONS postcode licensing](https://www.ons.gov.uk/methodology/geography/licences/)

Contains HM Land Registry data © Crown copyright and database right 2021. This data is licensed under the Open Government Licence v3.0.

Contains National Statistics data and OS data © Crown copyright and database right 2026.


## Address predictor

In the price predictor, enter a postcode, house number or street, then select the exact recorded property. The calculator shows the previous achieved sale, local market movement, recorded-factor adjustment, independent area/road estimate and the learned blend. A previous sale at least one year old is required. Conflicting records and material physical changes withhold that adjustment.

The address method had 7.0% median absolute percentage error on 2,351 supported later sales. The base model on those same houses had 12.9%. This is a matched subset, not an accuracy claim for every house. Nominal 80% age-specific intervals covered 79.0% overall, with weaker local coverage reported on screen. Bedrooms and floor area still have no separately estimated effect.

Address search and the alteration checkbox remain in the browser. They are not submitted to a backend or added to public data. The existing weekly workflow refits and exports the address component alongside the base model.
