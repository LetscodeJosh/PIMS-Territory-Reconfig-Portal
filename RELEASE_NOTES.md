# PIMS Territory Reconfiguration Web App — Release Notes (`v.0.1.1`)

**Release Version**: `v.0.1.1` (Repository Suite `v.0.8.0` / Build `0.8.0+51`)  
**Release Date**: November 2026  
**Target Environment**: ERPNext v15 Staging (`https://staging.pmii-marketing.com`) & Streamlit Cloud (`https://github.com/LetscodeJosh/PIMS-Territory-Reconfig-Portal.git` — `main` branch)

---

## 🚀 1. Fixes Applied in `v.0.1.1` (UAT Item #7 — Table Grid Row Actions, Territory Status & Parent Transfer)

### 1.1 Eliminated False `"ERPNext Error (HTTP 403)"` Toast on Parent Territory Transfer & Sub-Territory Creation
- **Root Cause**:
  1. When `get_authenticated_opener(force_refresh=True)` was triggered in `app.py` without `PIMS_SERVICE_USER` environment variables configured, it replaced the logged-in SFE user's authenticated ERPNext session opener in `st.session_state["opener"]` with an unauthenticated `Guest` opener, causing subsequent `PUT /api/resource/Territory/<name>` calls to return `HTTP 403 Forbidden`.
  2. Transferring a territory or adding a sub-territory (e.g., `AD101 - sub`) under a leaf territory (`AD0101`) required promoting the parent territory to `is_group = 1` on ERPNext first.
  3. Direct browser `fetch('/api/resource/Territory/...')` calls inside `territory_reconfiguration_portal.html` hit Streamlit's Tornado server when running on Streamlit Cloud.
- **Fix**:
  - Preserved the authenticated user session opener in `st.session_state["opener"]` across `get_authenticated_opener()` and `call_erpnext_resiliently()`.
  - Added automatic parent promotion (`_ensure_parent_territory_is_group`) in `app.py` (`tree_add` and `tree_edit`) and in `territory_reconfiguration_portal.html` so any territory (including `AD0101`) can accept sub-territories (`AD101 - sub`) or transferred child territories without HTTP 403/404 errors.
  - Guarded browser-direct `/api/resource/...` calls so they only execute in standalone local desktop mode (`server.py`), while Streamlit Cloud exclusively uses the authenticated `streamlit:setComponentValue` bridge.

### 1.2 Theme-Optimized Dropdowns & Popover Menus (Light Mode & Dark Mode)
- **Root Cause**: The Table Grid Row Actions popover (`.grid-actions-popover`), searchable ERP dropdowns (`.erp-search-input-box`, `.erp-dropdown-menu`), and `(Unassigned)` dropdown items had hardcoded Dark Mode colors (`#0F172A`, `#18181B`, `#27272A`), appearing dark even when the portal was in Light Mode.
- **Fix**:
  - Redesigned `.grid-actions-popover`, `.erp-search-input-box`, `.erp-dropdown-menu`, and dropdown item styles to automatically match the active theme: crisp white surfaces (`#FFFFFF` background, `#CBD5E1` border, `#0F172A` text) in **Light Mode** and slate dark surfaces (`#0F172A` / `#18181B` background, `#334155` border, `#F8FAFC` text) in **Dark Mode**.
  - Added a persistent **Light / Dark Mode toggle button** (`☀️ Light Mode` / `🌙 Dark Mode`) in the top header bar (`localStorage` key `pims_portal_theme`).

### 1.3 Three Separate Operational Statuses (`Active`, `Vacant`, `Inactive`) & Full Territory/MedRep Reactivation
- **Root Cause**:
  1. `Vacant` and `Inactive` were previously conflated into a single combined state (`Inactive / Vacant`).
  2. `toggleTreeNodeActiveStatus()` toggled `pt.operationalStatus` but never reset `pt.isActive = true`, leaving `isNodeInactive` permanently `true` so territories and MedReps could never be reactivated.
  3. Assigning a new active MedRep (`LAIZA PLACER`) in `submitTreeEdit()` or `saveRecordChanges()` updated `pt.rep` without resetting `pt.operationalStatus = 'Active'`, `pt.isActive = true`, and `pt.isResigned = false`, causing the newly assigned MedRep to be automatically tagged `Inactive / Resigned`.
  4. Clicking **Confirm** inside the `Tag Territory Inactive & Vacant` modal (`confirmTagInactive()`) threw an uncaught `ReferenceError: activeUser is not defined` and called non-existent functions (`renderGridTable`, `renderInteractiveTree`, `renderArchivedTerritoriesVault`).
- **Fix**:
  - Implemented the unified 3-state status engine (`getTerritoryOperationalStatus`, `setTerritoryOperationalStatus`, `cleanRepDisplayName`) supporting **three separate operational statuses**:
    - 🟢 **`Active`**: Assigned & operational territory.
    - 🟡 **`Vacant`**: Open territory slot awaiting MedRep assignment (all covered doctors preserved).
    - 🔴 **`Inactive`**: Decommissioned / resigned territory preserved in the Archive Directory.
  - Updated **Table Grid** (status filter checkboxes `ACTIVE | VACANT | INACTIVE`, status badges, and Row Actions menu items `Set Active`, `Tag as Vacant`, `Tag as Inactive`), **Territory Tree** (`Set Active`, `Vacant`, `Inactive` action buttons and distinct badges), and **Status Update Modal** (`#inactiveModalOverlay`) to support seamless transitions among all 3 statuses.
  - Assigning a MedRep via **Edit Territory** automatically transitions the territory back to **`Active`** and clears any prior `Inactive`/`Vacant` flags.
  - Resolved conflicting MedRep status in dropdowns (`ALDRIN ESTORICO`) so active MedReps are never falsely locked out, and MedReps on inactive territories can be selected to reactivate/reassign.

---

## 🛠️ 2. Fixes Applied in Previous Version (`v.0.1.0` & UAT Item #4 — Reconfiguration Editor & Staging Cutover)

1. **Staging Environment API Cutover (`https://staging.pmii-marketing.com`)**:
   - Switched all REST endpoints, authentication handlers, and bidirectional sync connectors in `app.py`, `server.py`, and `territory_reconfiguration_portal.html` from Dev to Staging (`https://staging.pmii-marketing.com`), with blank-tree readiness for SFE live data entry.
2. **Program-Locked Territory Manager Dropdowns (UAT #4.1)**:
   - Locked all Territory Manager (`Sales Person`) dropdowns (`treeAddManager`, `treeEditManager`, `editManager`, `addManager`, `newSpParent`) strictly to members of the currently selected program (`activeProgram`, e.g., `Abbott Diabetes Care`, `Bayer Consumer Health`, `RiteMed`, `Vivaro`) via `isSalesPersonInProgram()` and `PROGRAM_SALES_PERSON_ROSTER`.
3. **Territory Name Never Overrides Territory Manager (UAT #4.2)**:
   - Removed the auto-matching logic in `onTreeAddNameInput()` so typing a Territory Name in the `Add Territory` modal never overrides or auto-populates the `Territory Manager` field.
4. **Removed `User ID` and `Account / Program` Fields from Display (UAT #4.3)**:
   - Hidden `User ID` and `Account / Program` fields across the Add Territory modal, Edit Territory modal, Reconfigure Territory modal, Add Sales Person modal, and Table Grid filters.
5. **Program-Locked Parent Territory & Doctor Transfer Dropdowns (UAT #4.4)**:
   - Locked `Parent Territory` selectors and `Transfer & Handover` destination territory dropdowns strictly to territories within the currently selected program (`getProgramTerritoryNames(activeProgram)`), preventing cross-program territory transfers.

---

## ✅ 3. Currently Working Functionalities in `v.0.1.1`

| Module / Feature | Status | Description |
| :--- | :---: | :--- |
| **Dual-Environment Authentication** | ✅ Working | Authenticates against ERPNext Staging (`https://staging.pmii-marketing.com`) on Streamlit Cloud & Desktop (`server.py`) with session persistence (`?sfe_session=`). |
| **Program Selector & Strict Isolation** | ✅ Working | Switches cleanly across `Abbott Diabetes Care`, `Bayer Consumer Health`, `RiteMed`, and `Vivaro` with zero cross-program leakage in territories or MedReps. |
| **Interactive Territory Tree View** | ✅ Working | Expand/collapse hierarchy, search filter, `+ Add Child` (folders & sub-territories like `AD101 - sub` under `AD0101`), `Edit`, `Transfer Doctor`, `Rename`, and 1-click `Set Active` / `Vacant` / `Inactive` buttons. |
| **Table Grid View & Filtering** | ✅ Working | Multi-column search, `ACTIVE \| VACANT \| INACTIVE` status filter checkboxes, column visibility selector, pagination (`10`, `20`, `50`, `All`), and theme-adaptive Row Actions menu. |
| **3-State Operational Status Engine** | ✅ Working | Separate `Active` (Green), `Vacant` (Amber), and `Inactive` (Red) statuses with full reactivation via button click, modal confirmation, or MedRep assignment. |
| **Light & Dark Mode Optimization** | ✅ Working | Header theme toggle (`☀️ Light Mode` / `🌙 Dark Mode`) optimizing all popovers, searchable ERP dropdowns, tables, and modals. |
| **Doctor Transfer & Handover** | ✅ Working | Two-pane doctor transfer & merge modal (`openDoctorTransferModal`) scoped to the active program with real-time doctor count recalculation. |
| **Covered Doctors & Audit Trail** | ✅ Working | Per-territory Covered Doctors viewer (`openCoveredDoctorsModal`) and full timestamped change ledger (`openAuditModal` & Summary Report). |
| **Archive Directory Vault** | ✅ Working | Zero-deletion preservation of `Vacant` and `Inactive` territories with 1-click restoration to active cycles. |
| **SFE Institution Approvals** | ✅ Working | Review, normalize, deduplicate, and approve new medical institutions submitted from the HCP Profiling Mobile App. |
