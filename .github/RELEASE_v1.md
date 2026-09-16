## CaseLinker: Cross-Case Analysis for ICAC Investigations

**CaseLinker** is an open-source system for ingesting, processing, clustering, and visualizing case data from Internet Crimes Against Children (ICAC) investigations.

### This Release Includes

- **Technical Report (PDF):** Full 23-page paper covering motivation, system architecture, deterministic feature extraction, two-stage clustering methodology, evaluation on 47 AZICAC cases (2011–2014), and analyst well-being considerations
- **Source Code:** Modular Python implementation (ingestion, processing, storage, clustering, visualization layers)
- **Live Demo:** Interactive web interface for case analysis

### Key Features

- **Interpretable Analysis:**  Regex-based parsing for deterministic, reproducible feature extraction
- **Cross-Case Pattern Detection:** Weighted Jaccard similarity clustering across platforms, demographics, severity indicators
- **Psychological Safety:** Visualization design prioritizing analyst well-being through structured data presentation and gradual disclosure
- **Minimal Infrastructure:** SQLite, standard hardware, no cloud dependencies

### Citation

>Ramachandran, M. (2026). *CaseLinker: An Open-Source System for Cross-Case Analysis of Internet Crimes Against Children Investigations.* Technical Report. University of Massachusetts Amherst.

### Links

- **Live Demo:** https://web-production-13a2.up.railway.app/
- **Documentation:** See `README.md` in repository 
- **Technical report:** [CaseLinker.pdf](https://github.com/user-attachments/files/25492309/CaseLinker.pdf)

---

**Note:** This research uses publicly available, redacted case summaries from Arizona ICAC annual reports (2011–2014). No private victim data or graphic content is included.
