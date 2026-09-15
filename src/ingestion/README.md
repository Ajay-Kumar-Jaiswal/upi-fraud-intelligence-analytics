# src/ingestion/

Raw-file reading is handled directly by each src/cleaning/*.py module
(pd.read_csv / json.load) and by src/analytics/loaders.py for the
cleaned Parquet output — both are simple enough that a separate
ingestion abstraction layer was not needed for this dataset's scale
(~66K rows across 4 files). Reserved in the original architecture;
left in place with this note rather than silently deleted.
