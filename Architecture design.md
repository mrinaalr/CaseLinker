# CaseLinker Architecture

## Overview

CaseLinker is designed as a system for ingesting, processing, clustering, and visualizing case related data, specifically cases related to CSEA. This means often cases will be a) scrapped from websites b) not cleanly formatted c) have sensitive components d) have varing levels of details (think azicac vs fbi cases vs ncmec reports) 


## System Architecture

### High-Level Components

```
┌─────────────────────────────────────┐
│      Data Sources                   │
│ for now start with one source,      │  
| azicac 2014 cases and arrests,      │
| modular so can upload website / pdf │
└────────┬────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│      Data Ingestion Layer           │
│  - Import                           │  
│  - Data validation & sanitization   │
│  - Basic cleaning, panda based      │
└────────┬────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│      Data Processing Layer          │
│  - select data to keep              │
│  - assign cases values (for compare)|
|  - fill in case schema for each case|
└────────┬────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│      Data Storage Layer             │
│  - Case database [rawish]           │
│  - Graph database ( weighting)      │
│  - requires quick retrieval,look-ups│
└────────┬────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│      Clustering & Analysis Layer    │
│  - Select cases to display together │
|  - Compares based on saved case data|
│  - Trend detection                  │
└────────┬────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│      Visualization Layer            │
│  - Interactive dashboards           │
│  - Graphs (!!)                      │
│  - Filtering                        │
│  - Expandable case/data  views      │
└─────────────────────────────────────┘
```

## Core Components


### 1. Data Ingestion Layer

**Purpose**: Handle diverse, messy data sources and normalize them into a consistent format for processing.

**Components**:
- **Keep it very simple**: parse file [I wanna start with text-based but we will see], simple pre-processing, nothing too fancy just take the info from the source to the data processing layer 



### 2. Data Processing Layer

**Purpose**: Extract features, assign comparison values, fill in basic schema, and prepare cases for clustering and analysis.


**Case Entity Schema**:

- select relevant, consistent case characteristics to be compared and analyzed

```yaml
Case:
  - id: unique identifier
  - source: organization/jurisdiction (e.g., "AZICAC", "FBI", "NCMEC")
  - date_range: {start, end} or single date
  
  # Victim Context (anonymized)
  - victim_count: number
  - victim_demographics: {age_range, region, anonymized_id}
  
  # Perpetrator Context (anonymized)
  - perpetrator_count: number
  - perpetrator_demographics: {age_range, region, anonymized_id}
  - relationship_to_victim: {relative, stranger, unknown}
  - previous_conviction: {crime, date, n/a}
  
  # Technology & Methods
  - platforms_used: [platform names, n/a]
  - technologies: [tech identifiers, n/a]
  - communication_methods: [methods, n/a]

  # Law Enforcement
  - investigation_methods_and_teams: [methods, teams]
  - prosecution_outcome: {status, charges, sentences}
  
  # Content Classification
  - severity_indicators: [internal scale]
  - case_topics: [topic tags]
  
  # Raw/Original Data
  - raw_data: original case data (preserved for reference)
  - extracted_features: structured features extracted from raw data
  
  # Metadata
  - tags: [custom tags]
  - notes: case summary (?)
  - created_at, updated_at
```



### 3. Storage Layer

**Purpose**: Store cases and relationships with fast retrieval and lookup capabilities.

**Components**:
- **Case Database** (PostgreSQL/MySQL):
  - keep it simple, store case data tables, ideally similar close together
  - ideally also store case entities in "rawish" format (preserve original structure + normalized fields)

- **Graph Database** (may actually make end job simpler):
  - Store case and relationships 
  - Weighted edges based on similarity strength
  - Efficient traversal for link analysis
  - Quick relationship queries (e.g., "show all cases connected to case X")



### 4. Clustering and Analysis Layer 

**Purpose**: Compare cases, detect clusters, identify trends, and select cases to display together.

**Components**:
- **Case Comparison**:
  - Compare cases against each other in database
  - Calculate similarity scores using assigned values
  - Identify potential links and relationships
  - Support multiple compare metrics 
- **Clustering**:
  - Group cases based on shared characteristics
  - Multi-dimensional clustering (by platform, method, victim, perpetrator, region, time, etc.)
- **Link Detection**:
  - Entity matching: same perpetrators, victims, platforms across cases
  - Pattern-based linking: deeper patterns in cases
- **Trend Detection**:
  - Analyze evolution of exploitation methods over time
  - Recurring case topics 
- **Case Selection**:
  - Select cases to display together based on clustering
  - Filter and group cases for visualization
  - Support user-defined grouping criteria


### 6. Visualization Layer

**Purpose**: Present case data, clusters, and trends in an interactive, tasteful, and informative way

Most important part of project, I want a) filtering so that you can analyze all cases based on what interests you b) clustering so visually grouping similar cases (or even filtered content like platforms) c) interactive components (think HCI and data visualization class)


