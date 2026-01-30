# CaseLinker Architecture

## Overview

CaseLinker is designed as a system for ingesting, processing, clustering, and visualizing case data related, specifically cases related to CSEA. This means often cases will be a) scrapped from websites b) not cleanly formatted c) have sensitive components d) have offline or hybrid cases with digital components e) have partial details (think azicac vs fbi cases vs ncmec reports) 


## System Architecture

### High-Level Components

```
┌─────────────────────────────────────┐
│      Data Sources                   │
│   for now start with one source,    │  
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
│  - semantic clustering (?)          |
|  - assign cases values (for compare)|
└────────┬────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│      Data Storage Layer             │
│  - Case database [rawish]           │
│  - Graph database ( ? relationships)│
│  - requires quick retrieval,look-ups│
└────────┬────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│      Clustering & Analysis Layer    │
│  - Select cases to display together │
│  - Trend detection                  │
└────────┬────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│      Visualization Layer            │
│  - Interactive dashboards           │
│  - Graphs (!!)                      │
│  - Filtering                        │
│  - Expandable case/data detail views│
└─────────────────────────────────────┘
```

## Core Components

### 1. Data Ingestion Layer

**Purpose**: Handle diverse, messy data sources and normalize them into a consistent format for processing.

**Components**:
- **Keep it very simple**: parse file [I wanna start with text-based but we will see], simple pre-processing, nothing too fancy just take the info from the source to the data processing layer 



### 2. Data Processing Layer

**Case Entity Schema**:
```yaml
Case:
  - id: unique identifier
  - source: organization/jurisdiction (e.g., "AZICAC", "FBI", "NCMEC")
  - source_id: original identifier from source
  - date_range: {start, end} or single date
  - status: {investigation, prosecution, closed, etc.}
  
  # Victim Context (anonymized)
  - victim_demographics: {age_range, region, anonymized_id}
  - victim_count: number
  
  # Perpetrator Context (anonymized)
  - perpetrator_demographics: {age_range, region, anonymized_id}
  - perpetrator_count: number
  - relationship_to_victim: type
  
  # Technology & Methods
  - platforms_used: [platform names]
  - technologies: [tech identifiers]
  - communication_methods: [methods]
  - distribution_channels: [channels]
  
  # Law Enforcement
  - agencies_involved: [agency names]
  - investigation_methods: [methods]
  - prosecution_outcome: {status, charges, sentences}
  - jurisdiction: {country, state, region}
  
  # Content Classification
  - content_types: [categories]
  - severity_indicators: [indicators]
  - case_topics: [topic tags]
  
  # Raw/Original Data
  - raw_data: original case data (preserved for reference)
  - extracted_features: structured features extracted from raw data
  
  # Metadata
  - tags: [custom tags]
  - notes: sanitized notes
  - related_cases: [case_ids]
  - clustering_status: {pending, processed, needs_review}
  - created_at, updated_at
```

**Relationship Graph**:
- Cases connected by shared characteristics
- Weighted edges based on similarity strength
- Relationship types: shared_perpetrator, shared_victim, similar_methods, same_platform, etc.

### 3. Processing Layer

**Purpose**: Extract features, assign comparison values, and prepare cases for clustering and analysis.

**Components**:
- **Feature Extraction**: Extract structured data from unstructured case notes
  - Identify platforms, technologies, methods from text
  - Extract dates, locations, entities
  - Classify content types and severity indicators
- **Data Selection**: Determine which data to keep and prioritize
  - Filter relevant fields for clustering
  - Handle partial/missing data appropriately
  - Weight important vs. less important attributes
- **Value Assignment**: Assign cases values for comparison
  - Normalize categorical data to comparable values
  - Create feature vectors for similarity calculation
  - Weight different attributes (e.g., platform match vs. date proximity)
- **Semantic Clustering** (optional/experimental):
  - Use NLP to understand case semantics
  - Group cases by meaning/similarity, not just exact matches
  - Topic modeling for recurring themes

**Key Features**:
- Runs asynchronously after case ingestion
- Can be re-run when clustering criteria change
- Supports incremental processing (process new cases against existing)
- Handles both structured and unstructured data

**Workflow**:
1. Retrieve case from database
2. Extract features from raw data
3. Assign comparison values/weights
4. Update case record with processed features
5. Queue for clustering/comparison


### 4. Storage Layer

**Purpose**: Store cases and relationships with fast retrieval and lookup capabilities.

**Components**:
- **Case Database** (PostgreSQL/MySQL):
  - Store case entities in "rawish" format (preserve original structure + normalized fields)
  - Support complex queries and aggregations
  - Full-text search capabilities for case notes
  - Indexed for quick lookups (by date, source, status, etc.)
  - Fast retrieval for visualization and filtering
- **Graph Database** (Neo4j/ArangoDB):
  - Store case relationships and networks
  - Weighted edges based on similarity strength
  - Efficient traversal for link analysis
  - Support for community detection algorithms
  - Quick relationship queries (e.g., "show all cases connected to case X")
- **Analytics Cache** (Redis/Optional):
  - Cache frequently accessed statistics
  - Pre-computed aggregations for dashboards
  - Session data for interactive visualizations

**Key Features**:
- Quick retrieval: Optimized indexes for common queries
- Fast lookups: Direct access to cases by ID, source, date range
- Relationship queries: Efficient graph traversal for connected cases
- Scalable: Can handle growing dataset without performance degradation
- Backup and recovery: Regular backups of sensitive data

**Data Flow**:
- Cases stored immediately after ingestion (before processing)
- Relationships added/updated after clustering/comparison
- Both databases kept in sync


### 5. Analysis Layer (Clustering & Analysis)

**Purpose**: Compare cases, detect clusters, identify trends, and select cases to display together.

**Components**:
- **Case Comparison Engine**:
  - Compare new cases against existing cases in database
  - Calculate similarity scores using assigned values
  - Identify potential links and relationships
  - Support multiple similarity metrics (cosine, Jaccard, custom weighted)
- **Clustering Engine**:
  - Group cases based on shared characteristics
  - Multi-dimensional clustering (by platform, method, region, time, etc.)
  - Hierarchical clustering for nested groups
  - Dynamic clustering: allow custom clustering criteria
- **Link Detection**:
  - Entity matching: same perpetrators, victims, platforms across cases
  - Temporal linking: cases in sequence or overlapping time
  - Geographic linking: cases in same/nearby regions
  - Pattern-based linking: similar modus operandi
- **Trend Detection**:
  - Analyze evolution of exploitation methods over time
  - Technology/platform adoption trends
  - Geographic spread patterns
  - Recurring case topics identification
- **Case Selection**:
  - Select cases to display together based on clustering
  - Filter and group cases for visualization
  - Support user-defined grouping criteria

**Key Features**:
- Runs after cases are stored in database
- Can re-cluster when new cases added or criteria change
- Supports experimentation with different algorithms
- Background/async processing for performance
- Updates graph database with relationships

**Workflow**:
1. Retrieve new case from database
2. Compare against existing cases (find similar)
3. Update clusters (add to existing or create new)
4. Detect links and relationships
5. Update graph database with connections
6. Recalculate trends if needed
7. Mark case as processed


### 6. Visualization Layer

**Purpose**: Present case data, clusters, and trends in an interactive, tasteful, and informative way.

**Components**:
- **Interactive Dashboards**:
  - Case overview with summary statistics
  - Key metrics and KPIs
  - Recent cases and updates
- **Graph Visualizations** (!!):
  - Network graphs showing case relationships
  - Interactive node-link diagrams
  - Community/cluster visualization
  - Filterable and zoomable
- **Filtering System**:
  - Filter by date range, source, status, platform, region
  - Multi-criteria filtering
  - Save filter presets
  - Real-time filtering updates
- **Expandable Case/Data Detail Views**:
  - Click to expand case details
  - Show full case information
  - Display relationships to other cases
  - Show clustering information
- **Statistical Charts**:
  - Temporal trends (cases over time)
  - Technology/platform adoption
  - Geographic distribution (anonymized)
  - Outcome analysis (prosecution rates, etc.)
- **Cluster Explorer**:
  - Browse case clusters
  - Drill into specific clusters
  - Compare clusters side-by-side

**Key Features**:
- **Tasteful presentation**: Abstract representations, avoid graphic details
- **Privacy-first**: No PII, anonymized identifiers, aggregated views by default
- **Interactive**: Real-time filtering, drilling down, custom views
- **Fast**: Optimized queries, cached data, lazy loading
- **Exportable**: Generate reports, export filtered data (with proper permissions)

**Visualization Principles**:
- Use abstract/graphical representations rather than detailed case content
- Focus on patterns and relationships, not individual case details
- Provide context without exposing sensitive information
- Make it easy to explore and discover connections


