# ClearCut 🎬
> **Screenplay pre-clearance research desk and source evidence workspace with an immutable audit paper trail.**

ClearCut parses screenplays, detects clearance risks across ten protected categories, retrieves authoritative source evidence, coordinates team approvals, and compiles reproducible clearance dossiers.

---

## 🌐 Live Cloud Deployment

| Service | Endpoint |
|---|---|
| **Live Web Workspace** | **[https://clearcut-gvnistvvoq-uc.a.run.app](https://clearcut-gvnistvvoq-uc.a.run.app)** |
| **Interactive API Documentation** | **[https://clearcut-gvnistvvoq-uc.a.run.app/docs](https://clearcut-gvnistvvoq-uc.a.run.app/docs)** |
| **OpenAPI 3.1 Spec** | **[https://clearcut-gvnistvvoq-uc.a.run.app/openapi.json](https://clearcut-gvnistvvoq-uc.a.run.app/openapi.json)** |
| **System Health Probe** | **[https://clearcut-gvnistvvoq-uc.a.run.app/api/v1/healthz](https://clearcut-gvnistvvoq-uc.a.run.app/api/v1/healthz)** |

---

## 💰 Minimum Cost Architecture ($0.00 / Month)

ClearCut is engineered to operate on Google Cloud's **minimum cost tier** (zero idle cost, 100% eligible for GCP Free Tier):

| Component | Configuration | Free Tier / Pricing | Monthly Cost |
|---|---|---|---|
| **Google Cloud Run** | Scale-to-Zero (`min: 0`, `max: 2`, `512MB RAM`) | 2M requests & 360,000 GB-sec free | **$0.00** |
| **Cloud Build** | Multi-stage auto-build | 120 build-min / day free | **$0.00** |
| **Artifact Registry** | Container image storage (~150MB) | 0.5 GB free storage | **<$0.02** |
| **Database (Default)** | Serverless In-Container Embedded Storage | Scales to zero with Cloud Run | **$0.00** |
| **Database (Optional)** | Cloud SQL PostgreSQL 17 (`clearcut-pg17`) | Dedicated 24/7 instance | ~$7.67 – $25.00 |
| **Total (Minimum Tier)**| | | **$0.00 / mo** |

To check estimated costs anytime from your terminal:
```bash
./clearcut cost
```

---

## 🚀 Quickstart for Non-Technical Users

ClearCut includes an interactive, self-diagnosing CLI assistant that requires **zero technical setup**.

### Option 1: Run Locally (Free Studio)
Run one command (or double-click `start.sh`):
```bash
./start.sh
# or
./clearcut start
```
* **Checks Docker**: If not installed or closed, guides you in plain English.
* **Provisions PostgreSQL 17**: Boots database and seeds the *Borrowed Light* demo screenplay.
* **Auto-Launch**: Automatically opens `http://localhost:8000` in your web browser.

---

### Option 2: Deploy to Google Cloud
Deploy your own live instance with the interactive cloud wizard:
```bash
./clearcut deploy
```
* **Interactive Sign-in**: 1-click Google account login.
* **Project Selection**: Select or create a GCP project from a numbered menu.
* **Cost Advisory**: Displays minimum cost breakdown and options before deployment.
* **Zero-Touch Config**: Enables APIs, provisions storage, runs 7-step smoke tests, and opens your live URL.

---

## 🧰 CLI Command Reference

```bash
./clearcut <command>
```

| Command | Description |
|---|---|
| `./clearcut start` | Launch the local studio with PostgreSQL 17 (Docker) |
| `./clearcut stop` | Stop all local ClearCut containers |
| `./clearcut deploy` | Deploy to Google Cloud Run (guided interactive wizard) |
| `./clearcut cost` | Display detailed monthly cost breakdown matrix |
| `./clearcut smoke` | Execute the 7-step automated verification smoke gate |
| `./clearcut logs` | Stream live container logs |
| `./clearcut status` | Inspect local Docker and live Cloud Run service status |

---

## 🔒 Security & Provenance Boundaries
- **Strict Provenance**: Evidence claims require verifiable snapshots with publisher classification and source timestamps.
- **Transactional Governance**: Approvals, referrals, and dispositions require human triggers recorded to immutable audit receipts.
- **Tenancy Isolation**: Multi-tenant data scoped strictly by `org_id` and project path.
- **Legal Pre-Clearance Boundary**: ClearCut facilitates evidence collection and workflow risk detection, not final legal advice.

---

## 📄 License
Apache-2.0. Open-source with zero vendor lock-in.
