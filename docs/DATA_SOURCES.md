# Data Sources Register

Every external data source the application uses, or that operators are directed to consult manually. The same register is seeded into the database and shown in the app (**دليل المصادر العامة**).

General rule: the application performs **no automated scraping**. Information from public websites is recorded manually by the operator with the URL and the date it was viewed. Operators must respect each site's terms of service, `robots.txt`, and Egyptian Personal Data Protection Law No. 151 of 2020.

| # | Source | Official URL | Information available | Usage limitations | Update frequency | License / attribution | Access |
|---|---|---|---|---|---|---|---|
| 1 | Google libphonenumber (Python `phonenumbers`) | https://github.com/google/libphonenumber | Number validity, type, E.164 format, original operator of the number range, landline area code region, time zone | Numbering-plan metadata only. No subscriber name, address, status or location. Operator shown is the **original range allocation**; Egypt has Mobile Number Portability, so the current operator may differ. | With library releases (several per year); update by upgrading the package | Apache-2.0; no in-app attribution required | Bundled, offline |
| 2 | National Telecom Regulatory Authority (NTRA), Egypt | https://www.tra.gov.eg/ | Licensed operators, national numbering plan, regulatory announcements | No subscriber lookup. Manual reference only; no automated collection by the app. | Not stated – as published by NTRA | Government website; no open-data licence stated. Cite as source; check the site's terms. | Manual |
| 3 | OpenStreetMap standard tile layer | https://operations.osmfoundation.org/policies/tiles/ | Map background images | Light use only; bulk/offline download prohibited; valid identification required; visible attribution required. Provider is configurable in Settings. | Continuous (community-edited data) | Data ODbL 1.0 – attribution "© OpenStreetMap contributors" (https://www.openstreetmap.org/copyright), shown on the map | Online API |
| 4 | OpenStreetMap Nominatim (optional, off by default) | https://operations.osmfoundation.org/policies/nominatim/ | Approximate address for a consented location point | Max 1 request/second, no bulk use, identifying User-Agent; the app calls it only on explicit operator request and caches the result | Continuous | ODbL 1.0 – "© OpenStreetMap contributors" | Online API |
| 5 | Location shared by the device owner (W3C Geolocation API) | https://www.w3.org/TR/geolocation/ | Coordinates and accuracy at the moment of sharing | Requires HTTPS and explicit permission from the device owner; single snapshot; accuracy depends on the device | Only when a new invitation is accepted | Personal data – Law 151/2020 and the app's retention policy apply | Customer browser |
| 6 | Public websites (manual review) | Per source | Any public information the operator views (company site, business directory, published advert) | Recorded manually with URL and viewing date; respect each site's terms and `robots.txt`; no automated collection | Per source | Per site terms; URL kept as attribution | Manual |

## Explicitly excluded sources
* Paid number-intelligence / HLR / caller-ID APIs.
* Telecom network data of any kind (cell-tower location, subscriber registers).
* Any source requiring an account with payment details.
* Social-media scraping or unofficial APIs.

These cannot be implemented legally and technically within the zero-cost, consent-only constraints, so they are not offered.
