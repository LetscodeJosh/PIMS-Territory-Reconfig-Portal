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
