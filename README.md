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

The selected reduced-feature model has a median absolute percentage error of 13.1% and a mean absolute error of about £93,600. The nominal 80% interval covers 80.2% of test transactions overall. Coverage varies by market. The revised-data evaluation uses the observed target-month HPI and is not a real-time forecasting backtest.

Bedrooms, floor area, condition and parking are missing. Price estimates therefore describe broad location/type evidence. They are not bedroom-adjusted valuations. No predictive bargain flag is released. Linslade's source locality labels provide incomplete coverage, so unsupported local estimates are withheld. Leighton Buzzard context is labelled separately.

Household shortlists, feedback, mailbox records and recipient settings are excluded from this repository and website. The public exporter reads only official sales and their geographic classification. It has no access to household state during GitHub runs.

## Sources

- [Price Paid Data](https://www.gov.uk/government/statistical-data-sets/price-paid-data-downloads)
- [Official linked-data service](https://landregistry.data.gov.uk/)
- [UK House Price Index](https://www.gov.uk/government/collections/uk-house-price-index-reports)

Contains HM Land Registry data © Crown copyright and database right 2021. This data is licensed under the Open Government Licence v3.0.
