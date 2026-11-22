# Platform launch years

`afh_manifest/config/platform_launch_years.csv` records the first public launch year of each platform in the capability registry (`capability_sources/*.yaml`). One row per registry id, in the registry's own spelling.

| Column | Meaning |
|---|---|
| `platform_id` | The platform name as the capability sources write it |
| `launch_year` | The year the platform itself was first opened to the public. Blank when no fetched source states that year |
| `source_url` | The page that states the year. Empty when the year is blank |
| `note` | A rebrand, an earlier name, or why the year is blank |

The year is the platform's own first public launch. A later feature, a later client, or a rename does not move it. Renames are in the note (Twitter to X, SkyDrive to OneDrive, Square Cash to Cash App, Yellow to Yubo).

`launch_years.py` reads the table. It is not imported by observation, resolution, or release.

```python
from ontology.platform_affordance_evidence.launch_years import generation, load, unknowns

generation(2003)   # "<=2003"
generation(2004)   # "2004-2010"
generation(2010)   # "2004-2010"
generation(2011)   # "2011-2016"
generation(2016)   # "2011-2016"
generation(2017)   # ">=2017"
generation(None)   # None
unknowns(load())   # platform ids with a blank year
```

A blank year is unknown. It is not placed in a generation.
