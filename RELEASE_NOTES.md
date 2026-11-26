## [v.0.1.4 - Live-Only ERPNext Dropdowns, GCP Staging Sync & HCP App MedRep Parity] - 2026-11-26

### Key Enhancements & Fixes Applied
- **Top Header Bar Versioning (`v.0.1.4`)**: Updated the top navigation version badge (`#headerPortalVersionBadge`) and `VERSION` tracker to `v.0.1.4`.
- **Zero Hardcoded Fallback Rosters or Temporary JSON State (`app.py`, `index.html`)**:
  - Removed `PROGRAM_SALES_PERSON_ROSTER`, `LIVE_DATA`, `BASELINE_*`, `ERP_TERRITORY_USER_MAP`, and `localStorage` fallback pollution from Territory Manager, Parent Sales Person, Employee, and User dropdowns so empty ERPNext DocTypes cleanly display `No data available`.
  - Disabled temporary `shared_territory_state.json` persistence/re-injection so ERPNext DocTypes are the sole source of truth on GCP VMs.
- **GCP Staging Territory & Sales Person Creation Fixes (`app.py`, `deploy/gcp/update.sh`)**:
  - Added automatic Frappe `X-Frappe-CSRF-Token` attachment + retry, dynamic root node bootstrapping (`Sales Team` / `All Territories`) on empty Staging DocTypes, `frappe.desk.treeview.add_node` & `frappe.client.insert` fallbacks, and real ERPNext error reporting.
  - Updated `deploy/gcp/update.sh` to pull the active branch (`staging`) and clean up legacy `shared_territory_state.json`.
- **HCP App <-> Territory Web App MedRep Availability Sync (`app.py`, `index.html`)**:
  - Auto-resolves `Territory.custom_user_id` from `Sales Person -> Employee -> User` on assignment/handover/reactivation and clears both `territory_manager` and `custom_user_id` whenever a territory is vacated, deactivated, or archived.

---

## [v.0.1.3 - Authoritative Live ERPNext Deletion Sync & Shared State Auto-Pruning] - 2026-11-20

### Key Enhancements & Fixes Applied
- **Top Header Bar Versioning (`v.0.1.3`)**: Updated the top navigation version badge (`#headerPortalVersionBadge`) and `VERSION` tracker to `v.0.1.3`.
- **Authoritative Live ERPNext Territory Deletion Sync (`app.py`)**:
  - Updated `merge_shared_territories_into_list(..., is_live_erpnext=False)` and `fetch_live_territories()` so live ERPNext responses are authoritative for territory existence.
  - Automatically prunes territories deleted directly in ERPNext from `shared_territory_state.json` on refresh instead of re-appending them, while retaining `Vacant` / `Inactive` status overlays on active territories and `pending_erp_sync=True` resilience for offline creations.

---

## [v.0.1.2 - UX Enhancements, Tree/Grid Sync, Sales Person Code Sync & Intelligent Bulk Operation] - 2026-11-20

### Key Enhancements & Fixes Applied
- **Top Header Bar Versioning (`v.0.1.2`)**: Displayed the active portal version badge (`v.0.1.2` via `#headerPortalVersionBadge`) directly beside `HCP Profiling • Territory Reconfiguration Portal` in the top navigation bar.
- **Animated Sidebar Toggle**: Added smooth CSS transitions on the hamburger icon (`#sidebarToggleBtn`) reflecting open/closed menu states.
- **Sales Person Code Synchronization on Territory Rename**: Single and bulk territory renames automatically update parenthesized territory codes `(CODE)` on matching Sales Person records in both the portal dropdown/tree and ERPNext backend (`_sync_sales_person_code_on_territory_rename`).
- **Parent-Subtree Search Preservation**: Filtering the Territory Tree retains matching parent territories together with their child subtrees.
- **Bidirectional Table Grid & Territory Tree Sync**: Status updates, edits, renames, child additions, and doctor transfers from Table Grid synchronize live with Territory Tree View and ERPNext persistence.
- **Streamlined Action Menus, Modals, Audit Trail & Bulk Operation**:
  - Dynamically hides `Set Active` for `Active` rows and simplifies row action labels to `Vacant`, `Inactive`, and `Transfer Doctor`.
  - Streamlined operational status confirmation modal (removed redundant policy banner and status dropdown while keeping `Territory Code`, `Current MedRep`, and `Affiliated Doctors`).
  - Upgraded Audit Trail with structured summary cards, decoded text formatting, clear action badges, and performer fallback (`SFE Lead`).
  - Removed decorative icons/emojis across portal windows, renamed Bulk Edit to `Bulk Operation` (`Assigned MedRep`, `Assigned District`), added an editable per-row + global helper Bulk Rename workbench with collision checks, and simplified the Archive tab.

---

## [v.0.1.1 - Hotfix: MedRep Tagging Status Validation, Table Grid Alignment, ERPNext Direct Deletion Sync & Theme Refinement] - 2026-11-10

### 🎯 Key Bug Fixes & Architectural Enhancements Applied

#### 1. Tagging MedRep / Territory Status Error Resolution (`app.py` & `secure_frappe_gateway.py`)
- **Resolved Disallowed Action Error**: Added `territory_toggle_status`, `territory_deactivate`, `doctor_transfer`, `resignation_handover`, `bulk_decommission`, `bulk_archive`, `inst_create`, and `inst_propose` to `allowed_actions` in `TerritoryActionSchema`.
- **Flexible Field Identification**: Updated payload validation to accept `territory`, `territory_name`, `name`, and `code`, preventing schema rejection.
- **Strict Invariant: Error Toasts Shown ONLY on Genuine Failures**: When tagging a MedRep or updating operational status succeeds, the gateway returns a clean `"success"` response. Error banners and toasts are strictly silenced on successful operations.

#### 2. Table Grid Row Actions & Column Alignment Optimization across Laptop Screens
- **Eliminated Header Collision (`LATEST PREVIOUS CODEACTIVE CODE`)**:
  - Assigned explicit, non-overlapping column widths and `min-width` constraints:
    - `col-prev`: `width: 180px !important; min-width: 180px !important;` (Generous space for `Latest Previous Code` with zero truncation or text collision).
    - `col-active`: `width: 150px !important; min-width: 150px !important;` (`Active Code`).
    - `col-area`: `width: 165px !important; min-width: 165px !important;` (`Area / District`).
    - `col-rep`: `width: 250px !important; min-width: 250px !important;` (`Assigned MedRep`).
    - `col-docs`: `width: 110px !important; min-width: 110px !important; text-align: center !important;` (`Doctor Count`).
    - `col-status`: `width: 100px !important; min-width: 100px !important; text-align: center !important;` (`Status`).
    - `col-actions`: `width: 115px !important; min-width: 115px !important; max-width: 115px !important; text-align: center !important;` (`Actions`).
    - `col-cb`: `width: 48px !important; min-width: 48px !important; max-width: 48px !important; text-align: center !important;`.
  - Enforced `#editorTable { table-layout: fixed; width: 100%; min-width: 1100px; }`.
  - Wrapped within `.table-responsive { overflow-x: auto; width: 100%; }` to guarantee smooth, unclipped horizontal scrolling across all laptop screen sizes (1280px, 1366px, 1920px).

#### 3. Real-Time ERPNext Direct Deletion Synchronization
- **Strict Masterlist Synchronization**: When an administrator deletes a territory directly within ERPNext backend:
  - In `syncProgramTerritoriesWithTree()`: Territories not present in live `territoryTreeData` are instantly filtered out (`if (!node) return false;`).
  - In `switchProgram()`: Baseline territories and loaded records are validated against `territoryTreeData`; deleted records are never resurrected.
  - State is automatically persisted to `localStorage`, removing deleted territories from both Tree View and Table Grid immediately.

#### 4. Bulk Operations Workbench: Decommission Renamed to Archive
- **Terminological Alignment**: In the 4-in-1 Bulk Operations Workbench, Tab 3 is renamed from "Decommission" to **"Archive"**.
- **Archive Policy**:
  - Banner Header: **"Archive Policy (Zero Data Loss Guarantee)"**.
  - Action Subtitle: **"Tag as Inactive & Move to Archive Vault"**.
  - Reason Prompt: **"Archive Reason (Required):"** (Default: `Archived during SFE cycle realignment`).
  - Confirmation Checkbox: **"I confirm archiving of these selected territories (tag Inactive and move to Archive)."**
  - Action Button: **"Confirm & Move to Archive"**.
  - Zero permanent deletion guarantee: Territories are marked `Inactive` and archived in Tab 2 with covered doctors preserved.

#### 5. Removal of Light & Dark Mode Feature
- **Permanent Enterprise Light Mode**: Completely removed the `#btnThemeToggle` button from the header navigation bar.
- **Theme Lock**: System is permanently locked to high-contrast, clean enterprise Light Mode, eliminating any contrast inconsistencies or text invisibility across all views and modals.

#### 6. Retention of Prior Bug Fixes (Argon Bug #7, Bug #4, Bug #8, Bug #9)
- 100% preservation of all previously resolved behaviors:
  - Parent group promotion (`is_group = 1`) on parent territory when adding sub-territories.
  - Multi-window drag-and-drop doctor transfer with live doctor count sync and MedRep search bar.
  - Resignation & Handover quick merge with ERPNext HR employee/user ID auto-population.
  - Live multi-user Institution Approvals sync and MedRep Submission workbench.
- 100% SHA-256 byte-for-byte parity across all 7 mirrored portal files.

---

## [v.0.1.0 - Initial Release: SFE Territory Reconfiguration Web Portal] - 2026-10-18

### Initial Release Foundation
- **Dedicated Versioning**: Established standalone web application versioning starting at `v.0.1.0` with dedicated `VERSION` tracking file (`git tag v.0.1.0` at commit `1f87ffc`).
- **Realignment Tab Refinement**: Eliminated active district cluster grids to retain strictly the Archived & Inactive Territories Directory Vault.
- **Summary Report & Audit Trail UI/UX**: Unified KPI summary numbers and added sticky headers with scrollable viewports for deep audit logs.
- **Strict No-Deletion Architecture**: Replaced permanent territory deletion in table actions with a safe **Tag Inactive / Vacant** workflow and live ERPNext synchronization.
- **Interactive Guidance Engine**: Implemented first-time user login detection with an interactive onboarding walkthrough.
