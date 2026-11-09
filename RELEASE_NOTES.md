# PIMS Territory Reconfiguration Web App — Release Notes (`v.0.1.1`)

**Release Version**: `v.0.1.1` (Repository Suite `v.0.8.0` / Build `0.8.0+51`)  
**Release Date**: November 2026  
**Target Environment**: ERPNext v15 Staging (`https://staging.pmii-marketing.com`) & Streamlit Cloud (`https://github.com/LetscodeJosh/PIMS-Territory-Reconfig-Portal.git` — `main` branch)

---

## 🚀 1. Fixes Applied in `v.0.1.1` (UAT Item #9 — Transfer of Doctor Two-Window Drag-and-Drop)

### 1.1 Doctor Transfer Persistence Bug Fix (Streamlit Cloud & Tab Refresh)
- **Root Cause**:
  1. `loadProgramTerritories()` / `switchProgram()` previously overwrote `programAccounts` on every page load with the static baseline `progData.accounts`, ignoring all transferred doctor assignments saved in browser `localStorage`.
  2. In Streamlit Cloud (`app.py`), the `execute_tree_action()` dispatcher did not have a handler for `action == "doctor_transfer"`, causing Streamlit reruns to drop doctor transfer state.
- **Fix**:
  - `switchProgram()` now strictly loads `programAccounts` from `localStorage` (`pims_accounts_<program>` / `pims_global_doctor_assignments_<program>`) before falling back to baseline data.
  - In `saveDoctorTransfer()`, doctor assignments are updated on both `programAccounts` and working arrays, persisted to `localStorage` under multiple redundant keys, and dispatched to Streamlit with the full `accounts` payload.
  - In `app.py`, added a dedicated `doctor_transfer` handler in `execute_tree_action()` that logs the transfer, persists doctor accounts in `st.session_state[f"live_accounts_{prog}"]`, and passes `live_accounts` back to `portal_component`. Doctor transfers now fully survive browser refreshes, Streamlit reruns, and tab switches without resetting.

### 1.2 Accurate Dynamic Doctor Count (Elimination of Double-Counting)
- **Root Cause**:
  - In `getCoveredDoctorsForTerritory()`, the previous matching condition matched any account where `accRep.includes(repClean)`. If a Medical Representative was assigned to multiple territories or shared common name tokens, their doctors were erroneously counted across every territory they touched, inflating doctor counts.
  - Furthermore, `row.docs` was reading static baseline numbers rather than dynamically syncing with live account arrays.
- **Fix**:
  - Refactored `getCoveredDoctorsForTerritory()` to enforce **primary territory matching**: if `acc.liveTerritory` is present, it must strictly match the territory's active or previous code (`c1`, `c2`, or `c3`). Only if `acc.liveTerritory` is blank does it fall back to matching by rep name.
  - Accounts with mismatched program tags are filtered out.
  - Synchronized `row.docs` dynamically with `getCoveredDoctorsForTerritory(row).length` in `renderTable()`, `syncProgramTerritoriesWithTree()`, `switchProgram()`, and `populateTransferTerritoryDropdowns()`, ensuring 100% accurate doctor counts everywhere.

### 1.3 Dedicated MedRep Search Feature Bar in Doctor Transfer Workbench
- **Requirement**:
  - In addition to the doctor search input, provide a dedicated MedRep search bar in both the Target and Source panes of the Doctor Transfer window, strictly filtered to the currently active program.
- **Fix**:
  - Added dedicated MedRep search input bars (`#transferTargetRepSearchInput`, `#transferSourceRepSearchInput`) above the territory dropdowns in both the Target (Destination) and Source panes.
  - Implemented `filterTransferRepDropdown(side)` to filter the dropdown options in real time as the SFE Lead types a representative's name, territory code, or district.
  - Ensured `populateTransferTerritoryDropdowns()` strictly isolates representatives and territories to `activeProgram` via `detectSalesPersonProgram(t.rep)`, `getProgramTerritoryNames(activeProgram)`, and `detectTextProgram(code)`, completely preventing cross-program MedRep leaks.

---

## 🚀 2. Fixes Applied in `v.0.1.1` (UAT Item #8 — Tab 1 MedRep Resignation & Handover Advisory, Bulk Operations Persistence, Tree View Sync & HR Validation)

### 1.1 Removed "Enter New MedRep Name" Freeform Input on Doctor Transfer & Handover Window
- **Root Cause**:
  1. The Doctor Transfer & Handover workbench header previously contained an unvalidated text input (`#handoverNewRepInput` with placeholder `"Enter new MedRep name..."`), allowing ad-hoc typing of arbitrary representative names that bypassed ERPNext HR records.
  2. The Territory Edit modal's `Transfer Rep` button invoked a browser prompt dialog `prompt('Enter new Medical Representative name to transfer territory:')`, which also bypassed validated program rosters.
  3. The Resigned Representative Handover modal contained a freeform text input (`#resignNewRepInput`).
- **Fix**:
  - Completely removed `#handoverNewRepInput` from the Doctor Transfer & Handover window. The workbench header now cleanly displays the source representative, 3-state operational status toggles, and an informational subtitle (`Direct Doctor Portfolio Transfer between Territories`).
  - Refactored `transferRepPrompt()` to immediately open the Doctor Transfer & Handover workbench (`openDoctorTransferModal(terrCode)`) with the target territory preselected, eliminating browser prompt dialogs.
  - In `resignedHandoverPromptModalOverlay`, removed `#resignNewRepInput` and dynamically populated `#resignNewRepSelect` strictly from active program MedReps and ERPNext HR `Sales Person` masterlists. Selecting a representative automatically validates and displays their ERPNext User ID (`onResignNewRepSelectChanged`).

### 1.2 Bulk Operations Tab Refresh Persistence Bug Fix
- **Root Cause**:
  1. In `applyBulkEdit()`, `applyBulkRename()`, and `applyBulkAdd()`, modifications were applied to in-memory arrays (`programTerritories`, `programAccounts`), but were **never saved to `localStorage`** (`pims_stg_program_territories_<program>`, `pims_stg_territory_tree_v1`, `pims_accounts_<program>`).
  2. On tab refresh or page reload, `loadProgramTerritories()` retrieved the stale previous state from `localStorage`, causing all newly created MedReps, clusters, and bulk edits to vanish.
- **Fix**:
  - Implemented automatic, comprehensive `localStorage` persistence across all bulk operations (`applyBulkEdit`, `applyBulkRename`, `applyBulkAdd`, and `applyBulkDelete`). All bulk edits and newly added territories survive tab refreshes, browser reloads, and cycle navigation 100%.

### 1.3 Bulk Operations UI Cleanup & Removal of "Update Status" Selector
- **Root Cause**:
  1. Unnecessary emojis and decorative icons (`⚡`, `✏️`, `🏷️`, `🗑️`, `➕`, `ℹ️`, `✨`) cluttered modal titles, tabs, and form labels.
  2. The Modify tab contained an `"Update Status"` dropdown (`#bulkEditStatus` with options `CHANGED` / `UNCHANGED`), which was redundant because operational statuses (`Active`, `Vacant`, `Inactive`) are managed via dedicated status engines and row actions.
- **Fix**:
  - Cleaned all bulk operations modal headers, tabs, and labels to adhere to clean enterprise design standards without decorative emojis.
  - Completely removed the `#bulkEditStatus` dropdown from the Modify tab and `applyBulkEdit()` handler. Bulk modifications focus cleanly on MedRep reassignment, cluster regrouping, and audit logging.

### 1.4 Bulk Operations Territory Tree Synchronization Bug Fix
- **Root Cause**:
  1. `applyBulkAdd()` and `applyBulkEdit()` only pushed records into the flat table grid array (`programTerritories`), but never created or updated corresponding nodes in `territoryTreeData`.
  2. Newly created clusters and territories appeared in the Table Grid view but were completely missing from the Territory Tree hierarchy.
- **Fix**:
  - `applyBulkAdd()` now automatically detects if a district cluster exists in `territoryTreeData`. If not, it creates a new group node (`is_group = 1`, `parent_territory = programBranch`) and expands the branch in `treeExpandedNodes`.
  - For each added territory, `applyBulkAdd()` inserts a leaf node (`is_group = 0`, `parent_territory = cluster`, `territory_manager = rep`, `operational_status = initialStatus`) into `territoryTreeData`.
  - `applyBulkEdit()` automatically synchronizes cluster changes (`parent_territory`) and representative reassignments (`territory_manager`) into `territoryTreeData` and re-renders both views immediately (`renderTable()`, `renderTree()`).

### 1.5 Flexible Per-Territory MedRep Assignment in Bulk Add
- **Root Cause**:
  - `applyBulkAdd()` previously forced a single hardcoded representative across all entered territory codes, preventing SFE Leads from allocating multiple territories across different MedReps who share the same coverage area.
- **Fix**:
  - Added an interactive **Per-Territory Assignment Grid** (`#bulkAddRowsContainer`, `#bulkAddTableBody`, `renderBulkAddAssignmentRows()`) that dynamically parses entered codes and renders individual rows with editable District Cluster and Assigned MedRep selectors per territory.
  - SFE Leads can freely assign each territory to different representatives or vacant slots, or click **"Fill All"** (`applyBulkAddDefaultsToAllRows()`) to apply uniform defaults when desired.

### 1.6 HR Record Validation for New MedReps & Auto-Populating User ID
- **Root Cause**:
  - Previously, representatives could be entered as arbitrary names without verifying that an official Employee record was created by the HR Department in ERPNext, resulting in missing User IDs and broken mobile sync.
- **Fix**:
  - Enforced strict HR validation in `submitNewSalesPerson()`: every new representative must be linked to an official ERPNext Employee record (`empId` from `availableEmployees`), and must have an active User ID (`userAcc` email). If either is missing, creation is blocked with a clear warning directive.
  - Selecting an employee in `selectErpItem('newSpEmployee')` automatically searches `availableUsers` and auto-populates the matching User ID and email into `newSpUserAccount`.

### 1.7 Strict Zero-Deletion Standard (Elimination of Permanent Delete)
- **Root Cause**:
  - The Bulk Operations modal previously included a `"Delete"` tab with a radio option `"Permanently remove territory records"` and a red `"Confirm & Delete Selected"` button, violating the enterprise zero-deletion invariant.
- **Fix**:
  - Converted Tab 3 from `"Delete"` to **`"Decommission"`** (`#btnBulkTab_decommission`, `#bulkPane_decommission`).
  - Completely eliminated the permanent deletion option from the UI and backend logic.
  - Replaced the action with **Tag as Inactive & Move to Archive Vault**: decommissioned territories are marked `operationalStatus = 'Inactive'`, added to `archivedRecords` (Archive Vault — Tab 2), excluded from active dropdowns, and preserved with 100% doctor history without data loss. Button renamed to **`Confirm & Decommission to Archive`**.

---

## 🚀 2. Fixes Applied in `v.0.1.1` (UAT Item #7 — Table Grid Row Actions, Territory Status & Parent Transfer)

### 2.1 Eliminated False `"ERPNext Error (HTTP 403)"` Toast on Parent Territory Transfer & Sub-Territory Creation
- Preserved the authenticated user session opener in `st.session_state["opener"]` across `get_authenticated_opener()` and `call_erpnext_resiliently()`.
- Added automatic parent promotion (`_ensure_parent_territory_is_group`) in `app.py` (`tree_add` and `tree_edit`) and in `territory_reconfiguration_portal.html` so any territory (including `AD0101`) can accept sub-territories (`AD101 - sub`) or transferred child territories without HTTP 403/404 errors.
- Guarded browser-direct `/api/resource/...` calls so they only execute in standalone local desktop mode (`server.py`), while Streamlit Cloud exclusively uses the authenticated `streamlit:setComponentValue` bridge.

### 2.2 Theme-Optimized Dropdowns & Popover Menus (Light Mode & Dark Mode)
- Redesigned `.grid-actions-popover`, `.erp-search-input-box`, `.erp-dropdown-menu`, and dropdown item styles to automatically match the active theme: crisp white surfaces in **Light Mode** and slate dark surfaces in **Dark Mode**.
- Added a persistent **Light / Dark Mode toggle button** (`☀️ Light Mode` / `🌙 Dark Mode`) in the top header bar (`localStorage` key `pims_portal_theme`).

### 2.3 Three Separate Operational Statuses (`Active`, `Vacant`, `Inactive`) & Full Territory/MedRep Reactivation
- Implemented the unified 3-state status engine (`getTerritoryOperationalStatus`, `setTerritoryOperationalStatus`, `cleanRepDisplayName`) supporting **three separate operational statuses**:
  - 🟢 **`Active`**: Assigned & operational territory.
  - 🟡 **`Vacant`**: Open territory slot awaiting MedRep assignment (all covered doctors preserved).
  - 🔴 **`Inactive`**: Decommissioned / resigned territory preserved in the Archive Directory.
- Updated **Table Grid**, **Territory Tree**, and **Status Update Modal** (`#inactiveModalOverlay`) to support seamless transitions among all 3 statuses.
- Assigning a MedRep via **Edit Territory** automatically transitions the territory back to **`Active`** and clears any prior `Inactive`/`Vacant` flags.

---

## 🛠️ 3. Fixes Applied in Previous Version (`v.0.1.0` & UAT Item #4 — Reconfiguration Editor & Staging Cutover)

1. **Staging Environment API Cutover (`https://staging.pmii-marketing.com`)**:
   - Switched all REST endpoints, authentication handlers, and bidirectional sync connectors in `app.py`, `server.py`, and `territory_reconfiguration_portal.html` from Dev to Staging (`https://staging.pmii-marketing.com`), with blank-tree readiness for SFE live data entry.
2. **Program-Locked Territory Manager Dropdowns (UAT #4.1)**:
   - Locked all Territory Manager (`Sales Person`) dropdowns (`treeAddManager`, `treeEditManager`, `editManager`, `addManager`, `newSpParent`) strictly to members of the currently selected program (`activeProgram`) via `isSalesPersonInProgram()` and `PROGRAM_SALES_PERSON_ROSTER`.
3. **Territory Name Never Overrides Territory Manager (UAT #4.2)**:
   - Fixed the event handler on territory name input fields so typing or editing a territory name never overrides or modifies the territory manager.
4. **Clean Presentation (User ID & Program Fields Hidden from Standard UI) (UAT #4.3)**:
   - Hid technical internal fields (`User ID`, `Account/Program`) from standard view, keeping them strictly in the background for automated ERPNext payload construction.
5. **Program-Isolated Territory Transfers (No Cross-Program Crossover) (UAT #4.4)**:
   - Enforced strict program boundaries on all parent territory dropdowns (`editParentSelect`, `treeAddParentSelect`, `treeEditParentSelect`) so territories can only be reparented within their own program.

---

## 📦 4. Comprehensive Feature Matrix & Operational Status

| Module / Workbench | Operational Status | Summary of Capabilities |
| :--- | :---: | :--- |
| **Authentication & Session Bridge** | ✅ Working | Seamless single-click and URL token (`?sfe_session=...`) auth with 24/7 session persistence across page refreshes. |
| **Staging Environment API** | ✅ Working | Direct REST communication with `https://staging.pmii-marketing.com` with blank-tree onboarding readiness. |
| **Program-Locked Selection** | ✅ Working | Program switcher strictly isolates territories, managers, and doctors to the active program. |
| **Territory Reconfiguration Editor** | ✅ Working | Real-time inline editing of territory names, parent hierarchy, clusters, and representative assignments. |
| **Bulk Operations Workbench** | ✅ Working | Bulk modify, rename, decommission to archive vault, and bulk add with per-territory MedRep assignment, zero-deletion safety, clean UI, and full reload persistence. |
| **Territory Tree Hierarchy** | ✅ Working | Interactive collapsible tree with parent group auto-promotion, instant cluster/MedRep synchronization, and 3 distinct operational statuses. |
| **Doctor Transfer & Handover** | ✅ Working | Two-pane transfer tool for reassigning doctors between source and target territories with real-time recalculation and zero freeform prompt leaks. |
| **Covered Doctors & Audit Trail** | ✅ Working | Per-territory Covered Doctors viewer (`openCoveredDoctorsModal`) and full timestamped change ledger (`openAuditModal` & Summary Report). |
| **Archive Directory Vault** | ✅ Working | Zero-deletion preservation of `Vacant` and `Inactive` territories with 1-click restoration to active cycles. |
| **SFE Institution Approvals** | ✅ Working | Review, normalize, deduplicate, and approve new medical institutions submitted from the HCP Profiling Mobile App. |
