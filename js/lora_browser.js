import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { ensureUmiTheme } from "./umi_theme.js";

class LoraBrowserPanel {
  constructor() {
    this.element = null;
    this.loras = [];
    this.filtered = [];
    this.selected = null;
    this.searchTerm = "";
    this.globalStrength = 1.0;
    this.localStrength = 1.0;
    this.currentPage = 0;
    this.pageSize = 30;
    this.cardSize = "medium";
    this.sourceFilter = "all";
    this.metadataFilter = "all";
    this.sortBy = "name";
    this.pathFilter = "";
    this.tagsOnly = false;
    this.baseModels = [];
    this.folders = [];
    this.selectedFolders = new Set();
    this.selectedBaseModels = new Set();
    this.selectedIds = new Set();
    this.hasLoaded = false;
    this.expandedFolders = new Set(["Lora"]);
    this.resizeObserver = null;
    this.showAllTags = false;
    this.manualFolderSelection = false;
    this.fetchStats = { current: 0, total: 0, currentName: "" };
    this.wildcards = [];
    this.wildcardTarget = "";
    this.lastError = null;
    this.previousFocus = null;
    this.fetchGeneration = 0;
  }

  async fetchLoras(force = false) {
    const generation = ++this.fetchGeneration;
    try {
      const response = await fetch(force ? "/umiapp/loras?force=1" : "/umiapp/loras");
      let data = null;
      try {
        data = await response.json();
      } catch (parseError) {
        data = null;
      }
      if (generation !== this.fetchGeneration) return null;
      if (!response.ok || !data || data.success === false) {
        this.lastError = (data && data.error) || `Request failed (HTTP ${response.status})`;
        this.loras = [];
        this.baseModels = [];
        this.folders = [];
        return this.loras;
      }
      this.lastError = null;
      this.loras = data.loras || [];
      this.baseModels = data.base_models || [];
      this.folders = [...new Set(this.loras.map(l => l.folder || "(root)"))].sort((a, b) => a.localeCompare(b));
      return this.loras;
    } catch (error) {
      if (generation !== this.fetchGeneration) return null;
      console.error("[Umi LoRA Browser] Failed to fetch LoRAs:", error);
      this.lastError = (error && error.message) || String(error);
      this.loras = [];
      this.baseModels = [];
      this.folders = [];
      return [];
    }
  }

  createPanel() {
    const panel = document.createElement("div");
    panel.className = "umi-lora-browser";
    panel.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            width: 100vw;
            height: 100vh;
            background: var(--umi-sunken);
            z-index: 10000;
            display: none;
            color: var(--umi-ink);
            font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
        `;

    ensureUmiTheme();
    panel.innerHTML = `
            <style>
                .umi-lb-root { display: flex; flex-direction: column; height: 100%; width: 100%; position: relative; }
                
                /* Header */
                .umi-lb-header { display: flex; align-items: center; padding: 12px 18px; border-bottom: 1px solid var(--umi-rule); background: var(--umi-surface); gap: 16px; min-height: 60px; flex-shrink: 0; box-sizing: border-box; }
                .umi-lb-title { font-size: 18px; font-weight: 600; color: var(--umi-accent); white-space: nowrap; }
                .umi-lb-search-container { flex: 1; display: flex; justify-content: center; max-width: 600px; margin: 0 auto; position: relative; }
                .umi-lb-search-input { width: 100%; padding: 8px 12px; background: var(--umi-sunken); border: 1px solid var(--umi-rule-strong); border-radius: 6px; color: var(--umi-ink-strong); font-size: 14px; box-shadow: 0 2px 4px rgba(0,0,0,0.2) inset; }
                .umi-lb-search-input:focus { border-color: var(--umi-accent); outline: none; }
                .umi-lb-search-help { position: absolute; right: 10px; top: 50%; transform: translateY(-50%); font-size: 10px; color: var(--umi-ink-3); cursor: help; }
                .umi-lb-actions { display: flex; gap: 12px; align-items: center; white-space: nowrap; }
                .umi-lb-btn { background: var(--umi-surface-alt); color: var(--umi-ink); border: 1px solid var(--umi-rule-strong); padding: 6px 12px; border-radius: 6px; cursor: pointer; font-size: 12px; height: 32px; position: relative; display: inline-flex; align-items: center; justify-content: center; }
                .umi-lb-btn:hover { border-color: var(--umi-rule-hover); background: var(--umi-surface-hover); }
                
                /* Danger Button */
                .umi-lb-btn-danger { color: var(--umi-danger); border-color: var(--umi-danger-soft); }
                .umi-lb-btn-danger:hover { background: var(--umi-danger-wash); border-color: var(--umi-danger); }

                /* Gold Button Style */
                .umi-lb-btn-gold { background: var(--umi-warn-fill); color: var(--umi-ink-inverse); border: 1px solid var(--umi-warn-fill-hover); font-weight: 600; width: 100%; margin-top: 8px; }
                .umi-lb-btn-gold:hover { background: var(--umi-warn-fill-hover); color: var(--umi-ink-inverse); border-color: var(--umi-warn); }

                .umi-lb-select { background: var(--umi-surface); color: var(--umi-ink); border: 1px solid var(--umi-rule-strong); padding: 0 8px; border-radius: 6px; font-size: 12px; height: 32px; }

                /* Layout */
                .umi-lb-body { display: grid; grid-template-columns: 280px minmax(0, 1fr) 360px; flex: 1; min-height: 0; width: 100%; position: relative; }
                .umi-lb-sidebar { border-right: 1px solid var(--umi-rule); padding: 14px; overflow-y: auto; background: var(--umi-sunken); display: flex; flex-direction: column; gap: 16px; }
                .umi-lb-main { position: relative; overflow: hidden; display: flex; flex-direction: column; min-width: 0; background: var(--umi-sunken); }
                .umi-lb-grid { display: grid; align-content: start; justify-content: start; gap: 12px; padding: 14px; overflow-y: auto; flex: 1; }
                
                /* Grid Sizes */
                .grid-small { grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); }
                .grid-medium { grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); }
                .grid-large { grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); }

                /* Pagination */
                .umi-lb-pagination { display: flex; justify-content: center; align-items: center; gap: 8px; padding: 8px; border-top: 1px solid var(--umi-rule); background: var(--umi-sunken); height: 50px; box-sizing: border-box; }
                .umi-lb-chip { display: inline-flex; align-items: center; gap: 6px; font-size: 11px; background: var(--umi-surface); border: 1px solid var(--umi-rule); padding: 4px 8px; border-radius: 6px; }
                .umi-lb-page-input { background: transparent; border: 1px solid var(--umi-rule-strong); color: var(--umi-accent); width: 35px; text-align: center; font-size: 11px; border-radius: 4px; margin: 0 4px; }
                .umi-lb-selection-bar { display: none; align-items: center; gap: 8px; padding: 8px 14px; border-bottom: 1px solid var(--umi-rule); background: var(--umi-ground); }
                .umi-lb-selection-bar.active { display: flex; }
                .umi-lb-selection-spacer { flex: 1; }

                /* Tree */
                .umi-lb-tree { font-size: 12px; line-height: 1.6; user-select: none; }
                .umi-lb-tree-item { display: flex; align-items: center; gap: 4px; padding: 3px 6px; border-radius: 4px; cursor: pointer; color: var(--umi-ink); transition: background 0.1s; }
                .umi-lb-tree-item:hover { background: rgba(255, 255, 255, 0.05); }
                .umi-lb-tree-item.active-folder { color: var(--umi-ink); font-weight: 600; }
                .umi-lb-tree-file { font-size: 11px; color: var(--umi-ink-2); padding: 3px 6px 3px 24px; cursor: pointer; border-radius: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
                .umi-lb-tree-file:hover { color: var(--umi-ink-strong); background: rgba(255, 255, 255, 0.05); }
                .umi-lb-tree-file.selected { background: rgba(33, 150, 243, 0.2); color: var(--umi-accent); border: 1px solid rgba(33, 150, 243, 0.3); }
                .umi-lb-tree-toggle { width: 14px; height: 14px; display: flex; align-items: center; justify-content: center; transition: transform 0.2s; font-size: 10px; color: var(--umi-ink-3); }
                .umi-lb-tree-toggle.collapsed { transform: rotate(-90deg); }
                .umi-lb-tree-children { margin-left: 7px; border-left: 1px solid var(--umi-rule); }

                /* Details */
                .umi-lb-details { border-left: 1px solid var(--umi-rule); padding: 14px; overflow-y: auto; overflow-x: visible; background: var(--umi-sunken); min-width: 0; position: relative; }
                .umi-lb-detail-image-container { position: relative; width: 100%; height: 400px; background: var(--umi-sunken); border-radius: 6px; overflow: hidden; margin-bottom: 10px; border: 1px solid var(--umi-rule); }
                .umi-lb-detail-image { width: 100%; height: 100%; object-fit: contain; }
                
                /* Editable Fields */
                .umi-lb-editable { padding: 4px; border: 1px dashed transparent; border-radius: 4px; transition: all 0.2s; }
                .umi-lb-editable:hover { border-color: var(--umi-rule-strong); background: var(--umi-surface); cursor: text; }
                .umi-lb-editable:focus { border-color: var(--umi-accent); background: var(--umi-ground); outline: none; border-style: solid; }
                .umi-lb-editable[data-placeholder]:empty::before { content: attr(data-placeholder); color: var(--umi-ink-3); pointer-events: none; }

                .umi-lb-detail-title { font-size: 14px; color: var(--umi-accent); margin-bottom: 4px; font-weight: 600; line-height: 1.4; word-break: break-all; }
                .umi-lb-detail-meta { font-size: 11px; color: var(--umi-ink); margin-bottom: 12px; line-height: 1.5; }
                .umi-lb-detail-label { font-size: 11px; color: var(--umi-ink-2); margin-bottom: 4px; text-transform: uppercase; letter-spacing: 0.05em; }
                .umi-lb-detail-box { background: var(--umi-surface); border: 1px solid var(--umi-rule); border-radius: 6px; padding: 8px; font-size: 12px; color: var(--umi-ink); max-height: 160px; overflow-y: auto; white-space: pre-wrap; }
                .umi-lb-detail-actions { display: flex; gap: 8px; margin-top: 10px; flex-wrap: wrap; }
                .umi-lb-detail-back { display: none; }
                
                /* Dropdown Menu */
                .umi-lb-dropdown { position: absolute; top: 100%; right: 0; left: auto; background: var(--umi-surface-alt); border: 1px solid var(--umi-rule-strong); border-radius: 6px; padding: 4px 0; z-index: 10050; display: none; min-width: 140px; box-shadow: 0 4px 12px rgba(0,0,0,0.5); }
                .umi-lb-dropdown.show { display: block; }
                .umi-lb-dropdown-item { padding: 8px 12px; font-size: 12px; color: var(--umi-ink); cursor: pointer; white-space: nowrap; }
                .umi-lb-dropdown-item:hover { background: var(--umi-surface-hover); color: var(--umi-ink-strong); }

                /* Card Styles */
                .umi-lb-card { background: var(--umi-ground); border: 1px solid var(--umi-rule); border-radius: 8px; overflow: hidden; cursor: pointer; transition: transform 0.1s ease, border-color 0.1s ease; position: relative; display: flex; flex-direction: column; height: 100%; box-shadow: 0 2px 4px rgba(0,0,0,0.2); }
                .umi-lb-card:hover { border-color: var(--umi-accent-soft); transform: translateY(-2px); }
                .umi-lb-card.selected { border-color: var(--umi-accent); box-shadow: 0 0 0 1px var(--umi-accent) inset; }
                .umi-lb-thumb { width: 100%; height: 100%; background: var(--umi-sunken); position: relative; overflow: hidden; }
                .umi-lb-thumb img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: contain; }
                
                .umi-lb-overlay { color: var(--umi-ink-on-media); }
                .umi-lb-overlay .umi-lb-card-name { color: inherit; }
                .umi-lb-overlay .umi-lb-tag { color: var(--umi-ink-on-media); background: rgba(0,0,0,.65); }
                /* Heights based on class */
                .grid-small .umi-lb-thumb { min-height: 140px; }
                .grid-medium .umi-lb-thumb { min-height: 200px; }
                .grid-large .umi-lb-thumb { min-height: 380px; }

                /* Overlay & Tags */
                .umi-lb-overlay { position: absolute; left: 0; right: 0; bottom: 0; padding: 8px 8px 6px; background: linear-gradient(0deg, rgba(0,0,0,0.95) 0%, rgba(0,0,0,0.8) 60%, rgba(0,0,0,0) 100%); z-index: 5; pointer-events: none; }
                .umi-lb-card-name { font-size: 11px; font-weight: 600; color: var(--umi-ink-strong); margin-bottom: 2px; white-space: normal; word-break: break-word; text-shadow: 0 1px 2px black; line-height: 1.2; }
                .grid-small .umi-lb-overlay { display: none; }
                .umi-lb-badge { position: absolute; top: 6px; right: 6px; background: rgba(47, 125, 75, 0.9); color: var(--umi-ink-strong); padding: 2px 6px; font-size: 9px; border-radius: 4px; z-index: 6; box-shadow: 0 1px 2px rgba(0,0,0,0.5); }
                
                .umi-lb-tags { display: flex; gap: 4px; margin-top: 4px; overflow: hidden; flex-wrap: nowrap; height: 15px; mask-image: linear-gradient(to right, black 85%, transparent 100%); -webkit-mask-image: linear-gradient(to right, black 85%, transparent 100%); transition: height 0.2s ease; }
                .umi-lb-show-tags .umi-lb-tags { flex-wrap: wrap; height: auto; mask-image: none; -webkit-mask-image: none; overflow: visible; }
                .umi-lb-tag { background: rgba(255, 255, 255, 0.15); color: var(--umi-ink); font-size: 9px; padding: 0 4px; border-radius: 3px; backdrop-filter: blur(2px); white-space: nowrap; flex-shrink: 0; line-height: 14px; margin-bottom: 2px; }

                /* Inputs */
                .umi-lb-section { margin-bottom: 12px; }
                .umi-lb-section-title { font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--umi-ink-2); margin-bottom: 6px; border-bottom: 1px solid var(--umi-rule); padding-bottom: 4px; font-weight: 600; }
                .umi-lb-input { width: 100%; padding: 6px 8px; background: var(--umi-surface); border: 1px solid var(--umi-rule-strong); border-radius: 6px; color: var(--umi-ink); font-size: 12px; }
                .umi-lb-checkbox { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--umi-ink); cursor: pointer; user-select: none; }
                .umi-lb-filter-grid { display: flex; flex-wrap: wrap; gap: 6px; }
                .umi-lb-slider-row { display: flex; align-items: center; gap: 8px; }
                .umi-range { flex: 1; cursor: pointer; }
                .umi-range-val { font-family: monospace; color: var(--umi-accent); min-width: 32px; text-align: right; }

                /* Modal Styles */
                .umi-lb-modal-overlay { position: absolute; inset: 0; background: rgba(0,0,0,0.85); z-index: 20000; display: flex; align-items: center; justify-content: center; backdrop-filter: blur(2px); opacity: 0; transition: opacity 0.2s; pointer-events: none; }
                .umi-lb-modal-overlay.open { opacity: 1; pointer-events: auto; }
                .umi-lb-modal { background: var(--umi-surface); border: 1px solid var(--umi-rule-strong); border-radius: 8px; width: 90%; max-width: 600px; max-height: 85vh; display: flex; flex-direction: column; box-shadow: 0 10px 40px rgba(0,0,0,0.6); transform: scale(0.95); transition: transform 0.2s; overflow: hidden; }
                .umi-lb-modal-overlay.open .umi-lb-modal { transform: scale(1); }
                .umi-lb-modal-header { padding: 14px 18px; border-bottom: 1px solid var(--umi-rule); display: flex; justify-content: space-between; align-items: center; font-weight: 600; color: var(--umi-accent); background: var(--umi-ground); border-radius: 8px 8px 0 0; }
                .umi-lb-modal-close { cursor: pointer; font-size: 18px; color: var(--umi-ink-2); }
                .umi-lb-modal-close:hover { color: var(--umi-ink-strong); }
                .umi-lb-modal-body { padding: 20px; overflow-y: auto; background: var(--umi-sunken); }
                
                /* Fetch Options Modal Grid */
                .umi-lb-fetch-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 14px; }
                .umi-lb-fetch-option { 
                    background: var(--umi-surface-alt); padding: 14px; border-radius: 6px; border: 2px solid var(--umi-rule-strong); cursor: pointer; transition: all 0.2s; 
                    display: flex; flex-direction: column; justify-content: center; align-items: center; text-align: center; min-height: 80px;
                }
                .umi-lb-fetch-option:hover { border-color: var(--umi-rule-hover); background: var(--umi-surface-hover); }
                .umi-lb-fetch-option.selected { border-color: var(--umi-accent); background: var(--umi-surface); }
                .umi-lb-fetch-title { font-weight: 600; font-size: 13px; color: var(--umi-ink); margin-bottom: 4px; }
                .umi-lb-fetch-desc { font-size: 11px; color: var(--umi-ink); line-height: 1.4; }

                /* Status Bar in Header */
                .umi-lb-status { 
                    font-size: 11px; color: var(--umi-accent); font-family: monospace; 
                    display: flex; flex-direction: column; align-items: flex-end; justify-content: center;
                    min-width: 120px; text-align: right;
                    margin-left: 12px;
                }
                .umi-lb-status-line { line-height: 1.2; }

                /* Modal Grids (Images) */
                .umi-lb-img-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 14px; }
                .umi-lb-img-choice { width: 100%; aspect-ratio: 2/3; object-fit: contain; background: var(--umi-sunken); border-radius: 4px; border: 2px solid var(--umi-rule); cursor: pointer; transition: all 0.1s; }
                .umi-lb-img-choice:hover { border-color: var(--umi-accent); box-shadow: 0 0 10px rgba(143, 198, 255, 0.2); }
                
                .umi-lb-tag-grid { display: flex; flex-wrap: wrap; gap: 8px; }
                .umi-lb-int-tag { background: var(--umi-surface-alt); padding: 6px 10px; border-radius: 4px; font-size: 12px; cursor: pointer; border: 1px solid var(--umi-rule-strong); color: var(--umi-ink); transition: all 0.1s; }
                .umi-lb-int-tag:hover { background: var(--umi-surface-hover); border-color: var(--umi-accent); color: var(--umi-ink-strong); }
                .umi-lb-int-tag.copied { background: var(--umi-ok-soft); border-color: var(--umi-ok); color: var(--umi-ink-strong); }

                .umi-lb-filter-toggle { display: none; }
                @media (max-width: 1000px) {
                    .umi-lb-header { height: auto; min-height: 60px; flex-wrap: wrap; }
                    .umi-lb-search-container { order: 3; flex-basis: 100%; max-width: none; }
                    .umi-lb-body { grid-template-columns: 220px minmax(0, 1fr); height: auto; }
                    .umi-lb-details { position: absolute; inset: 0 0 0 auto; width: min(360px, 90vw); z-index: 20; box-shadow: -4px 0 18px rgba(0,0,0,.4); }
                    .umi-lb-details:not(.has-selection) { display: none; }
                    .umi-lb-detail-back { display: inline-flex; margin-bottom: 8px; }
                }
                @media (max-width: 680px) {
                    .umi-lb-sidebar { position: absolute; inset: 0 auto 0 0; width: min(280px, 88vw); z-index: 25; display: none; box-shadow: 4px 0 14px rgba(0,0,0,.2); }
                    .umi-lb-sidebar.filters-open { display: flex; }
                    .umi-lb-filter-toggle { display: inline-flex; }
                    .umi-lb-body { grid-template-columns: minmax(0, 1fr); }
                    .umi-lb-actions { flex-wrap: wrap; white-space: normal; }
                }

            </style>
            <div class="umi-lb-root">
                <div class="umi-lb-header">
                    <div class="umi-lb-title">LoRA Browser</div>
                    <div class="umi-lb-search-container">
                        <input class="umi-lb-search-input" data-role="search" placeholder="Search LoRAs or tags (supports 'tag:', 'lora:', regex, +, -)" />
                        <span class="umi-lb-search-help" title="Advanced Search:
'cat girl' - OR search
+'cat' +'girl' - AND search
-'3d' - Exclude
tag:anime - Search tags only
lora:xl - Search filenames only
regex:^SDXL.* - Regex search
/pattern/ - Regex search">?</span>
                    </div>
                    
                    <!-- Status Bar -->
                    <div class="umi-lb-status" data-role="status-bar">
                        <span class="umi-lb-status-line">Ready</span>
                    </div>

                    <div style="width: 1px; height: 24px; background: var(--umi-surface-hover); margin: 0 4px;"></div>

                    <div class="umi-lb-actions">
                        <button class="umi-lb-btn umi-lb-filter-toggle" data-action="toggle-filters" aria-expanded="false">Filters</button>
                        <label class="umi-lb-checkbox" title="Toggle full activation text on thumbnails">
                            <input type="checkbox" data-role="expand-tags" /> Expand Tags
                        </label>
                        <div style="width: 1px; height: 24px; background: var(--umi-surface-hover); margin: 0 4px;"></div>
                        <label class="umi-lb-checkbox" title="Global Default Strength">Default strength</label>
                        <div class="umi-lb-slider-row" style="width: 120px;">
                             <input type="range" class="umi-range" data-role="global-strength" min="0" max="3" step="0.1" value="1.0" />
                             <span class="umi-range-val" data-role="global-strength-val">1.0</span>
                        </div>
                        <select class="umi-lb-select" data-role="card-size" aria-label="Thumbnail size" title="Thumbnail size">
                            <option value="small">Small</option>
                            <option value="medium" selected>Medium</option>
                            <option value="large">Large</option>
                        </select>
                        <select class="umi-lb-select" data-role="sort" aria-label="Sort LoRAs">
                            <option value="name">Name</option>
                            <option value="newest">Newest</option>
                            <option value="oldest">Oldest</option>
                            <option value="size">File size</option>
                            <option value="base_model">Base model</option>
                            <option value="folder">Folder</option>
                        </select>
                        <button class="umi-lb-btn" data-action="fetch-all">Fetch CivitAI</button>
                        <button class="umi-lb-btn" data-action="close">Close</button>
                    </div>
                </div>
                <div class="umi-lb-body">
                    <aside class="umi-lb-sidebar">
                        <div class="umi-lb-section">
                            <button class="umi-lb-btn" style="width:100%" data-action="refresh">Refresh LoRAs</button>
                        </div>
                        <div class="umi-lb-section">
                            <div class="umi-lb-section-title">Metadata</div>
                            <select class="umi-lb-select" data-role="metadata-filter" style="width:100%;">
                                <option value="all">All LoRAs</option>
                                <option value="missing_preview">Missing preview</option>
                                <option value="has_preview">Has preview</option>
                                <option value="missing_civitai">Missing CivitAI</option>
                                <option value="has_civitai">Has CivitAI</option>
                                <option value="missing_triggers">Missing triggers</option>
                                <option value="has_triggers">Has triggers</option>
                            </select>
                        </div>
                        <div class="umi-lb-section">
                            <div class="umi-lb-section-title">Base Model</div>
                            <div class="umi-lb-tag-grid" data-role="base-model-filters"></div>
                        </div>
                        <div class="umi-lb-section">
                            <div class="umi-lb-section-title">Folders</div>
                            <div class="umi-lb-filter-grid" data-role="folder-filters"></div>
                        </div>
                        <div class="umi-lb-section" style="flex:1; overflow-y:auto; min-height:0;">
                            <div class="umi-lb-section-title">Folder Browser</div>
                            <div class="umi-lb-tree" data-role="folder-tree"></div>
                        </div>
                    </aside>
                    <main class="umi-lb-main">
                        <div class="umi-lb-selection-bar" data-role="selection-bar"></div>
                        <div class="umi-lb-grid grid-medium" data-role="grid"></div>
                        <div class="umi-lb-pagination" data-role="pagination"></div>
                    </main>
                    <aside class="umi-lb-details" data-role="details">
                        <div class="umi-lb-details-empty" style="color:var(--umi-ink-2);text-align:center;padding:20px;font-size:12px;">Select a LoRA</div>
                    </aside>
                </div>
                <!-- Modal Container -->
                <div class="umi-lb-modal-overlay" id="umi-lb-modal">
                    <div class="umi-lb-modal">
                        <div class="umi-lb-modal-header">
                            <span class="umi-lb-modal-title">Title</span>
                            <span class="umi-lb-modal-close">&times;</span>
                        </div>
                        <div class="umi-lb-modal-body"></div>
                    </div>
                </div>
            </div>
            <!-- Hidden File Input for Image Upload -->
            <input type="file" id="umi-lb-file-input" accept="image/*" style="display:none" />
        `;

    this.element = panel;
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-modal", "true");
    panel.setAttribute("aria-label", "LoRA Browser");
    panel.tabIndex = -1;
    document.body.appendChild(panel);
    
    this.resizeObserver = new ResizeObserver(() => {
        if (this.element.style.display !== 'none') {
            this.recalculatePageSize();
        }
    });
    this.resizeObserver.observe(this.element.querySelector('.umi-lb-main'));

    this.bindEvents();
    
    const modalOverlay = panel.querySelector('#umi-lb-modal');
    const modalClose = panel.querySelector('.umi-lb-modal-close');
    const closeModal = () => modalOverlay.classList.remove('open');
    modalClose.addEventListener('click', closeModal);
    modalOverlay.addEventListener('click', (e) => {
        if (e.target === modalOverlay) closeModal();
    });
  }

  updateStatus(message, subMessage = "") {
      const statusEl = this.element.querySelector('[data-role="status-bar"]');
      if(statusEl) {
          statusEl.replaceChildren();
          const primary = document.createElement("span");
          primary.className = "umi-lb-status-line";
          primary.textContent = String(message || "");
          statusEl.appendChild(primary);
          if (subMessage) {
              const secondary = document.createElement("span");
              secondary.className = "umi-lb-status-line";
              secondary.style.color = "var(--umi-ink)";
              secondary.textContent = String(subMessage);
              statusEl.appendChild(secondary);
          }
      }
  }

  closeDropdowns() {
      if (!this.element) return;
      this.element.querySelectorAll('.umi-lb-dropdown.show').forEach(dropdown => {
          dropdown.classList.remove('show');
          dropdown.style.position = '';
      });
  }

  // --- Search Logic ---
  
  parseSearchQuery(query) {
      if (!query) return null;
      
      const result = {
          must: [],
          mustNot: [],
          should: [],
          type: 'standard'
      };
      
      // Explicit regex syntax /pattern/ or regex:pattern
      if ((query.startsWith('/') && query.endsWith('/')) || query.startsWith('regex:')) {
           try {
               let pattern = query.startsWith('regex:') ? query.substring(6) : query.slice(1, -1);
               result.regex = new RegExp(pattern, 'i');
               result.type = 'regex';
               return result;
           } catch(e) { console.warn("Invalid regex", e); }
      }

      // Advanced Tokenizer
      // Captures: (+/-), (scope:), (quoted string) OR (word)
      const regex = /([+\-]?)(?:(tag:|lora:))?(?:"([^"]+)"|(\S+))/g;
      let match;
      while ((match = regex.exec(query)) !== null) {
          const prefix = match[1]; // + or - or empty
          const scope = match[2];  // tag: or lora: or undefined
          const content = (match[3] || match[4]).toLowerCase();
          
          const item = { scope, content };
          
          if (prefix === '+') result.must.push(item);
          else if (prefix === '-') result.mustNot.push(item);
          else result.should.push(item);
      }
      return result;
  }

  checkMatch(lora, name, tags, term) {
      const checkContent = (text) => text.includes(term.content);
      
      if (term.scope === 'tag:') {
          return checkContent(tags);
      } else if (term.scope === 'lora:') {
          return checkContent(name);
      } else {
          // Global scope
          return checkContent(name) || checkContent(tags);
      }
  }

  applyFilters(list) {
    const query = this.parseSearchQuery(this.searchTerm);

    return list.filter((lora) => {
      const name = (lora.filename || lora.name).toLowerCase();
      const activations = this.getActivationTags(lora);
      const tags = (lora.tags || []).concat(activations.tags).join(" ").toLowerCase();
      const activationText = activations.tags.join(" ").toLowerCase();
      
      // Path Filter
      // When pathFilter is empty, show all loras (root folder shows everything)
      if (this.pathFilter !== "") {
        const relativeFilter = this.pathFilter.replace(/^Lora\//, "").toLowerCase();
        if (!name.startsWith(relativeFilter)) return false;
      }

      if (this.selectedFolders.size > 0) {
        const folder = (lora.folder || "(root)").toLowerCase();
        const match = [...this.selectedFolders].some((f) => f.toLowerCase() === folder);
        if (!match) return false;
      }
      
      // Base Model Filter
      if (this.selectedBaseModels.size > 0) {
        const baseModel = (lora.base_model || lora.civitai?.base_model || "").toLowerCase();
        const match = [...this.selectedBaseModels].some((m) => m.toLowerCase() === baseModel);
        if (!match) return false;
      }

      if (!this.matchesMetadataFilter(lora, activations)) return false;

      // Advanced Search Filter
      if (query) {
          if (query.type === 'regex') {
              if (!query.regex.test(name) && !query.regex.test(tags)) return false;
          } else {
              // MUST NOT matches
              for (let term of query.mustNot) {
                  if (this.checkMatch(lora, name, tags, term)) return false;
              }
              // MUST matches
              for (let term of query.must) {
                  if (!this.checkMatch(lora, name, tags, term)) return false;
              }
              // SHOULD matches (If any exist, at least one must match, effectively behaving like OR search if used alone, or narrowing if mixed)
              // If user typed "cat girl", we usually treat that as AND in file search. 
              // If user typed "cat" "girl", standard search engines treat as AND.
              // We will treat non-prefixed terms as required (AND) to narrow down search as requested.
              for (let term of query.should) {
                  if (!this.checkMatch(lora, name, tags, term)) return false;
              }
          }
      }

      return true;
    });
  }

  async fetchWildcards() {
    try {
      const response = await fetch("/umiapp/wildcards/text/list");
      const data = await response.json();
      this.wildcards = data.files || [];
      return this.wildcards;
    } catch (error) {
      console.error("[Umi LoRA Browser] Failed to fetch wildcards:", error);
      this.wildcards = [];
      return [];
    }
  }

  matchesMetadataFilter(lora, activation = null) {
    const mode = this.metadataFilter || "all";
    if (mode === "all") return true;
    const activations = activation || this.getActivationTags(lora);
    const hasPreview = Boolean(this.getPreviewUrl(lora));
    const hasCivitai = Boolean(lora.civitai && (lora.civitai.id || lora.civitai.url || lora.civitai.name));
    const hasTriggers = activations.tags && activations.tags.length > 0;
    if (mode === "missing_preview") return !hasPreview;
    if (mode === "has_preview") return hasPreview;
    if (mode === "missing_civitai") return !hasCivitai;
    if (mode === "has_civitai") return hasCivitai;
    if (mode === "missing_triggers") return !hasTriggers;
    if (mode === "has_triggers") return hasTriggers;
    return true;
  }

  sortLoras(list) {
    const sorted = [...list];
    const clean = (lora) => this.getCleanFileName(lora.filename || lora.name).toLowerCase();
    if (this.sortBy === "newest") sorted.sort((a, b) => (b.mtime || 0) - (a.mtime || 0));
    else if (this.sortBy === "oldest") sorted.sort((a, b) => (a.mtime || 0) - (b.mtime || 0));
    else if (this.sortBy === "size") sorted.sort((a, b) => (b.size || 0) - (a.size || 0));
    else if (this.sortBy === "base_model") sorted.sort((a, b) => String(a.base_model || a.civitai?.base_model || "").localeCompare(String(b.base_model || b.civitai?.base_model || "")) || clean(a).localeCompare(clean(b)));
    else if (this.sortBy === "folder") sorted.sort((a, b) => String(a.folder || "").localeCompare(String(b.folder || "")) || clean(a).localeCompare(clean(b)));
    else sorted.sort((a, b) => clean(a).localeCompare(clean(b)));
    return sorted;
  }

  // --- End Search Logic ---

  showFetchOptionsModal() {
      const html = `
        <div style="margin-bottom:10px;font-size:12px;color:var(--umi-ink);">Choose what data to fetch from CivitAI:</div>
        <div style="margin-bottom:12px;">
            <div class="umi-lb-detail-label">CivitAI API Token (optional)</div>
            <input class="umi-lb-input" data-role="civitai-api-token" type="password" placeholder="Paste API token for account-gated models" value="${this.escapeHtmlAttr(localStorage.getItem("umi_civitai_api_token") || "")}" />
            <div style="font-size:11px;color:var(--umi-ink-2);margin-top:5px;">Stored locally in this browser. Leave empty to use the server environment token or anonymous access.</div>
        </div>
        <div class="umi-lb-fetch-grid">
            <div class="umi-lb-fetch-option" data-mode="update_missing">
                <div class="umi-lb-fetch-title">Update Missing</div>
                <div class="umi-lb-fetch-desc">Fill in missing thumbnails, JSON, and CivitAI info files. Links models to CivitAI.</div>
            </div>
            <div class="umi-lb-fetch-option" data-mode="replace_previews">
                <div class="umi-lb-fetch-title">Replace Previews</div>
                <div class="umi-lb-fetch-desc">Fetch and replace preview images for all models.</div>
            </div>
            <div class="umi-lb-fetch-option" data-mode="replace_civitai_info">
                <div class="umi-lb-fetch-title">Replace CivitAI Info</div>
                <div class="umi-lb-fetch-desc">Refresh .civitai.info files with latest data.</div>
            </div>
            <div class="umi-lb-fetch-option" data-mode="replace_json_info">
                <div class="umi-lb-fetch-title">Replace JSON Info</div>
                <div class="umi-lb-fetch-desc">Overwrite .json metadata files with latest data.</div>
            </div>
            <div class="umi-lb-fetch-option" data-mode="replace_json_and_civitai">
                <div class="umi-lb-fetch-title">Replace JSON & Info</div>
                <div class="umi-lb-fetch-desc">Refresh both .json and .civitai.info files.</div>
            </div>
            <div class="umi-lb-fetch-option" style="border-color: var(--umi-danger);" data-mode="replace_all">
                <div class="umi-lb-fetch-title" style="color: var(--umi-danger);">Replace All</div>
                <div class="umi-lb-fetch-desc">Previews, Info, and JSON. Warning: Very slow.</div>
            </div>
        </div>
      `;
      
      const body = this.createModal("CivitAI Fetch Options", html);
      
      let selectedMode = null;
      
      body.querySelectorAll('.umi-lb-fetch-option').forEach(opt => {
          opt.addEventListener('click', () => {
              body.querySelectorAll('.umi-lb-fetch-option').forEach(o => o.classList.remove('selected'));
              opt.classList.add('selected');
              selectedMode = opt.dataset.mode;
          });
      });
      
      // Auto select first one
      body.querySelector('.umi-lb-fetch-option').click();

      // Add Start Button
      const startBtn = document.createElement('button');
      startBtn.className = 'umi-lb-btn umi-lb-btn-gold';
      startBtn.textContent = "Start Fetching";
      startBtn.style.marginTop = "20px";
      startBtn.style.width = "100%";
      startBtn.onclick = () => {
          if(selectedMode) {
              const tokenInput = body.querySelector('[data-role="civitai-api-token"]');
              const token = tokenInput ? tokenInput.value.trim() : "";
              if (token) localStorage.setItem("umi_civitai_api_token", token);
              else localStorage.removeItem("umi_civitai_api_token");
              document.getElementById('umi-lb-modal').classList.remove('open');
              this.startBatchFetch(selectedMode, token);
          }
      };
      body.appendChild(startBtn);
  }

  async startBatchFetch(mode, apiToken = "") {
      this.updateStatus("Initializing...", "Batch fetch started");
      
      try {
          const items = this.loras.length ? [...this.loras] : await this.fetchLoras(true);
          if (items === null) return;
          let processed = 0;
          let failed = 0;
          let cached = 0;
          let warnings = 0;
          this.showNotification(`Starting ${items.length} LoRA fetches...`, false);

          for (let i = 0; i < items.length; i++) {
              const lora = items[i];
              const label = lora.filename || lora.name || `LoRA ${i + 1}`;
              this.updateStatus(`Fetching ${i + 1}/${items.length}`, label);
              const result = await this.fetchSingleCivitai(lora, false, mode, apiToken);
              if (result && result.success) {
                  processed += 1;
                  if (result.cached) cached += 1;
                  if (result.warning) warnings += 1;
              } else {
                  failed += 1;
              }
              await new Promise(resolve => setTimeout(resolve, 0));
          }

          await this.loadLoras(true);
          this.renderFolderTree();
          this.renderLoras();
          const suffix = failed ? `, ${failed} failed` : "";
          const warningSuffix = warnings ? `, ${warnings} warning${warnings === 1 ? "" : "s"}` : "";
          const cachedSuffix = cached ? ` (${cached} already cached)` : "";
          this.updateStatus("Fetch Complete", `Processed ${processed}/${items.length}${suffix}${warningSuffix}${cachedSuffix}`);
          this.showNotification(`Processed ${processed}/${items.length}${suffix}${warningSuffix}`, Boolean(failed || warnings));
      } catch (e) {
          console.error(e);
          this.updateStatus("Error", e.message);
          this.showNotification("Error during batch fetch", true);
      }
  }

  createModal(title, contentHTML) {
      const overlay = this.element.querySelector('#umi-lb-modal');
      const titleEl = overlay.querySelector('.umi-lb-modal-title');
      const bodyEl = overlay.querySelector('.umi-lb-modal-body');
      
      titleEl.textContent = title;
      bodyEl.innerHTML = contentHTML;
      overlay.classList.add('open');
      return bodyEl;
  }

  showInternalTagsModal(tagPairs) {
      if (!tagPairs || !tagPairs.length) {
          this.createModal("Internal Tags", `<div style="text-align:center; color:var(--umi-ink); padding:20px;">No internal tags found in metadata.</div>`);
          return;
      }

      const sortedPairs = [...tagPairs].sort((a, b) => b.count - a.count);
      const counts = sortedPairs.map(p => p.count).sort((a, b) => a - b);
      const maxCount = Math.max(counts[counts.length - 1] || 1, 1);
      const topPercentCount = Math.max(1, Math.ceil(sortedPairs.length * 0.05));
      const topCount = Math.min(topPercentCount, 10);
      const topTags = new Set(sortedPairs.slice(0, topCount).map(p => p.tag));
      const percentile = (arr, p) => {
          const idx = Math.max(0, Math.min(arr.length - 1, Math.round((arr.length - 1) * p)));
          return arr[idx];
      };
      const lowBound = percentile(counts, 0.1);
      const highBound = percentile(counts, 0.9);
      const rangeCount = Math.max(1, highBound - lowBound);
      const getTagColor = (tag, count) => {
          if (topTags.has(tag)) return "var(--umi-accent)"; // blue for top 5%
          const clamped = Math.min(highBound, Math.max(lowBound, count));
          const ratio = (clamped - lowBound) / rangeCount; // 0..1
          if (ratio <= 0.5) {
              const t = ratio / 0.5;
              const r = 220;
              const g = Math.round(60 + (200 - 60) * t);
              const b = 60;
              return `rgb(${r}, ${g}, ${b})`; // red -> yellow
          }
          const t = (ratio - 0.5) / 0.5;
          const r = Math.round(220 - (220 - 60) * t);
          const g = 200;
          const b = 60;
          return `rgb(${r}, ${g}, ${b})`; // yellow -> green
      };
      const html = `
        <div style="margin-bottom:12px; font-size:12px; color:var(--umi-ink-2);">Filter tags by training count and click to copy.</div>
        <div class="umi-lb-slider-row" style="margin-bottom:10px;">
            <input type="range" class="umi-range" data-role="tag-threshold" min="1" max="${maxCount}" step="1" value="1" />
            <span class="umi-range-val" data-role="tag-threshold-val">1</span>
        </div>
        <div style="max-height:45vh; overflow-y:auto;">
            <div class="umi-lb-tag-grid" data-role="internal-tag-grid"></div>
        </div>
      `;
      
      const body = this.createModal("Internal Metadata Tags", html);
      const grid = body.querySelector('[data-role="internal-tag-grid"]');
      const slider = body.querySelector('[data-role="tag-threshold"]');
      const sliderVal = body.querySelector('[data-role="tag-threshold-val"]');

      const renderTags = (minCount) => {
          const filtered = sortedPairs.filter(p => p.count >= minCount);
          grid.innerHTML = filtered.map(({ tag, count }) => `
              <div class="umi-lb-int-tag" data-tag="${this.escapeHtmlAttr(tag)}" title="Count: ${count}" style="color:${this.escapeHtmlAttr(getTagColor(tag, count))}">
                  ${this.escapeHtml(tag)} <span style="opacity:0.7">(${count})</span>
              </div>
          `).join('');
          grid.querySelectorAll('.umi-lb-int-tag').forEach(btn => {
              btn.addEventListener('click', async () => {
                  if (!await this.copyText(btn.dataset.tag, "Tag copied")) return;
                  btn.classList.add('copied');
                  btn.textContent = "Copied!";
                  setTimeout(() => {
                      btn.classList.remove('copied');
                      btn.textContent = btn.dataset.tag;
                  }, 1000);
              });
          });
      };

      slider.addEventListener('input', () => {
          const val = parseInt(slider.value, 10) || 1;
          sliderVal.textContent = String(val);
          renderTags(val);
      });

      renderTags(1);
  }

  getPreviewPrompts(lora) {
      const prompts = lora?.preview_prompts || lora?.civitai?.preview_prompts || [];
      return Array.isArray(prompts) ? prompts.filter(item => item && typeof item === "object") : [];
  }

  showPreviewPromptsModal(lora) {
      const prompts = this.getPreviewPrompts(lora);
      if (!prompts.length) {
          this.createModal("Preview Prompts", `<div style="text-align:center; color:var(--umi-ink); padding:20px;">No preview prompt metadata found. Try fetching or refreshing CivitAI info for this LoRA.</div>`);
          return;
      }

      const settingLine = (item) => {
          const parts = [];
          if (item.model) parts.push(`Model: ${item.model}`);
          if (item.sampler) parts.push(`Sampler: ${item.sampler}`);
          if (item.scheduler) parts.push(`Scheduler: ${item.scheduler}`);
          if (item.steps) parts.push(`Steps: ${item.steps}`);
          if (item.cfg_scale) parts.push(`CFG: ${item.cfg_scale}`);
          if (item.seed) parts.push(`Seed: ${item.seed}`);
          if (item.size) parts.push(`Size: ${item.size}`);
          return parts.join(" | ");
      };

      const resourcesLine = (resources) => {
          if (!Array.isArray(resources) || !resources.length) return "";
          return resources
              .map(resource => {
                  const name = resource.name || "resource";
                  const type = resource.type ? ` (${resource.type})` : "";
                  const weight = resource.weight !== undefined && resource.weight !== "" ? `: ${resource.weight}` : "";
                  return `${name}${type}${weight}`;
              })
              .join(", ");
      };

      const promptBlocks = prompts.map((item, idx) => {
          const settings = settingLine(item);
          const resources = resourcesLine(item.resources);
          const fullPrompt = [
              item.prompt ? `Prompt:\n${item.prompt}` : "",
              item.negative_prompt ? `Negative:\n${item.negative_prompt}` : "",
              settings ? `Settings:\n${settings}` : "",
              resources ? `Resources:\n${resources}` : "",
          ].filter(Boolean).join("\n\n");
          return `
            <div style="background:var(--umi-ground);border:1px solid var(--umi-rule);border-radius:6px;padding:10px;margin-bottom:12px;">
                <div style="display:flex;gap:10px;align-items:flex-start;">
                    ${item.url ? `<img src="${this.escapeHtmlAttr(item.url)}" style="width:96px;height:128px;object-fit:contain;background:var(--umi-sunken);border-radius:4px;border:1px solid var(--umi-rule);flex-shrink:0;" />` : ""}
                    <div style="min-width:0;flex:1;">
                        <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
                            <div style="font-size:12px;font-weight:600;color:var(--umi-accent);">Preview ${this.escapeHtml(String(item.index || idx + 1))}</div>
                            <button class="umi-lb-btn" data-action="copy-preview-prompt" data-preview-index="${idx}">Copy</button>
                        </div>
                        ${settings ? `<div style="font-size:11px;color:var(--umi-ink);margin-bottom:8px;">${this.escapeHtml(settings)}</div>` : ""}
                        ${item.prompt ? `<div class="umi-lb-detail-label">Prompt</div><div class="umi-lb-detail-box" style="max-height:180px;margin-bottom:8px;">${this.escapeHtml(item.prompt)}</div>` : ""}
                        ${item.negative_prompt ? `<div class="umi-lb-detail-label">Negative</div><div class="umi-lb-detail-box" style="max-height:120px;margin-bottom:8px;">${this.escapeHtml(item.negative_prompt)}</div>` : ""}
                        ${resources ? `<div class="umi-lb-detail-label">Resources</div><div class="umi-lb-detail-box" style="max-height:100px;">${this.escapeHtml(resources)}</div>` : ""}
                    </div>
                </div>
            </div>
            <textarea data-role="preview-copy-${idx}" style="display:none;">${this.escapeHtml(fullPrompt)}</textarea>
          `;
      }).join("");

      const body = this.createModal("Preview Prompts", `<div style="max-height:65vh;overflow-y:auto;">${promptBlocks}</div>`);
      body.querySelectorAll('[data-action="copy-preview-prompt"]').forEach(btn => {
          btn.addEventListener("click", () => {
              const idx = btn.dataset.previewIndex;
              const source = body.querySelector(`[data-role="preview-copy-${idx}"]`);
              const text = source ? source.value : "";
              if (!text) return;
              navigator.clipboard.writeText(text);
              this.showNotification("Copied preview prompt");
          });
      });
  }

  async fetchInternalTags(lora) {
      const request = this.tagsRequest = (this.tagsRequest || 0) + 1;
      try {
          this.updateStatus("Loading tags...", lora.name);
          const res = await fetch("/umiapp/loras/internal_tags", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ lora_name: lora.name })
          });
          const data = await res.json();
          if (request !== this.tagsRequest) return;
          if (!res.ok || !data?.success) throw new Error(data?.error || `Request failed (HTTP ${res.status})`);
          this.showInternalTagsModal(data.tag_pairs || []);
          this.updateStatus("Ready");
      } catch (e) {
          if (request !== this.tagsRequest) return;
          console.error(e);
          this.showNotification(`Could not load tags for ${lora.name}: ${e.message}`, true);
          this.updateStatus("Ready");
      }
  }

  getCleanFileName(pathOrName) {
    if (!pathOrName) return "";
    let parts = pathOrName.split(/[\\/]/);
    let name = parts[parts.length - 1];
    return name.replace(/\.[^/.]+$/, "");
  }

  bindEvents() {
    this.element.querySelector('[data-action="toggle-filters"]')?.addEventListener('click', (event) => {
      const sidebar = this.element.querySelector('.umi-lb-sidebar');
      sidebar.classList.toggle('filters-open');
      event.currentTarget.setAttribute('aria-expanded', String(sidebar.classList.contains('filters-open')));
    });
    const closeBtn = this.element.querySelector('[data-action="close"]');
    closeBtn.addEventListener("click", () => this.hide());

    document.addEventListener('click', () => this.closeDropdowns());
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && this.element.style.display !== 'none') {
        const modal = this.element.querySelector('#umi-lb-modal');
        if (modal?.classList.contains('open')) modal.classList.remove('open');
        else this.hide();
      }
    });

    const refreshBtn = this.element.querySelector('[data-action="refresh"]');
    refreshBtn.addEventListener("click", () => {
        // If they haven't manually navigated, we reset to Lora root
        if (!this.manualFolderSelection) {
            this.pathFilter = "";
        }
        this.loadLoras(true);
    });

    const searchInput = this.element.querySelector('[data-role="search"]');
    searchInput.addEventListener("input", (e) => {
      this.searchTerm = e.target.value.toLowerCase();
      this.currentPage = 0;
      this.scheduleSearch();
    });

    const metadataFilter = this.element.querySelector('[data-role="metadata-filter"]');
    metadataFilter.addEventListener("change", (e) => {
      this.metadataFilter = e.target.value;
      this.currentPage = 0;
      this.renderLoras();
    });

    const sortSelect = this.element.querySelector('[data-role="sort"]');
    sortSelect.addEventListener("change", (e) => {
      this.sortBy = e.target.value;
      this.currentPage = 0;
      this.renderLoras();
    });

    // Base model and folder filters are rendered dynamically; no static listeners needed here.

    const expandTags = this.element.querySelector('[data-role="expand-tags"]');
    expandTags.addEventListener("change", (e) => {
        const grid = this.element.querySelector('[data-role="grid"]');
        if (e.target.checked) grid.classList.add('umi-lb-show-tags');
        else grid.classList.remove('umi-lb-show-tags');
    });

    const globalSlider = this.element.querySelector('[data-role="global-strength"]');
    const globalVal = this.element.querySelector('[data-role="global-strength-val"]');
    globalSlider.addEventListener("input", (e) => {
      this.globalStrength = parseFloat(e.target.value);
      globalVal.textContent = this.globalStrength.toFixed(1);
    });

    const cardSizeSelect = this.element.querySelector('[data-role="card-size"]');
    cardSizeSelect.addEventListener("change", (e) => {
      this.cardSize = e.target.value;
      const grid = this.element.querySelector('[data-role="grid"]');
      grid.classList.remove("grid-small", "grid-medium", "grid-large");
      grid.classList.add(`grid-${this.cardSize}`);
      this.recalculatePageSize();
    });

    this.element.querySelectorAll('[data-action="fetch-all"]').forEach((btn) => {
      btn.addEventListener("click", () => this.showFetchOptionsModal());
    });

    const fileInput = document.getElementById('umi-lb-file-input');
    fileInput.addEventListener('change', async (e) => {
        if (e.target.files && e.target.files[0] && this.selected) {
            const file = e.target.files[0];
            const formData = new FormData();
            formData.append('image', file);
            formData.append('lora_name', this.selected.name);
            
            try {
                this.showNotification("Uploading image...");
                const res = await fetch("/umiapp/loras/upload_preview", { method: 'POST', body: formData });
                const data = await res.json();
                if (res.ok && data.success) {
                    this.showNotification("Preview updated");
                    // Save state before hard refresh
                    const selectedName = this.selected.name;
                    await this.loadLoras(true);
                    this.selected = this.loras.find(l => l.name === selectedName);
                    this.renderDetails();
                } else {
                    this.showNotification(data.error || "Upload failed", true);
                }
            } catch (err) {
                this.showNotification(err?.message || "Error uploading", true);
            }
        }
        fileInput.value = '';
    });
  }

  recalculatePageSize() {
      const gridEl = this.element.querySelector('[data-role="grid"]');
      if (!gridEl) return;
      
      const containerWidth = gridEl.clientWidth;
      const containerHeight = gridEl.clientHeight;
      
      let itemWidth, itemHeight;
      if (this.cardSize === 'small') { itemWidth = 152; itemHeight = 150; }
      else if (this.cardSize === 'large') { itemWidth = 332; itemHeight = 390; }
      else { itemWidth = 232; itemHeight = 210; } 

      const cols = Math.floor(containerWidth / itemWidth);
      const rows = Math.floor(containerHeight / itemHeight);
      const newSize = Math.max(1, cols) * Math.max(1, rows);
      
      if (newSize !== this.pageSize) {
          this.pageSize = newSize;
          this.renderLoras();
      }
  }

  buildFolderTree() {
    const tree = { name: "Lora", children: {}, files: [] };
    this.loras.forEach(lora => {
      const path = lora.filename || lora.name;
      const parts = path.split(/[\\/]/);
      let current = tree;
      for (let i = 0; i < parts.length - 1; i++) {
        const folderName = parts[i];
        if (!current.children[folderName]) {
          current.children[folderName] = { name: folderName, children: {}, files: [], fullPath: parts.slice(0, i + 1).join("/") };
        }
        current = current.children[folderName];
      }
      current.files.push(lora);
    });
    return tree;
  }

  renderFolderTree() {
    const treeData = this.buildFolderTree();
    const container = this.element.querySelector('[data-role="folder-tree"]');
    container.innerHTML = this.createTreeNodeHTML(treeData, "Lora");
    
    container.querySelectorAll('.umi-lb-tree-item').forEach(el => {
      el.addEventListener('click', (e) => {
         const path = el.dataset.path;
         if (this.expandedFolders.has(path)) this.expandedFolders.delete(path);
         else this.expandedFolders.add(path);
         
         this.manualFolderSelection = true; // User manually clicked a folder
         this.pathFilter = path === "Lora" ? "" : path;
         this.currentPage = 0;
         this.renderFolderTree();
         this.renderLoras();
      });
    });

    container.querySelectorAll('.umi-lb-tree-file').forEach(el => {
        el.addEventListener('click', (e) => {
            e.stopPropagation();
            const filename = el.dataset.filename;
            const lora = this.loras.find(l => (l.filename || l.name) === filename);
            if (lora) {
                this.selected = lora;
                this.localStrength = this.getLoraStrength(lora);
                this.renderFolderTree();
                this.renderDetails();
            }
        });
    });
  }

  renderBaseModelFilters() {
    const container = this.element.querySelector('[data-role="base-model-filters"]');
    if (!container) return;
    container.innerHTML = "";
    if (!this.baseModels || !this.baseModels.length) {
      container.innerHTML = `<div style="font-size:11px;color:var(--umi-ink-2);">No base models detected</div>`;
      return;
    }

    this.baseModels.forEach((model) => {
      const chip = document.createElement("div");
      chip.className = "umi-lb-tag";
      chip.textContent = model;
      chip.style.cursor = "pointer";
      chip.style.userSelect = "none";
      if (this.selectedBaseModels.has(model)) {
        chip.style.background = "rgba(79, 195, 247, 0.35)";
        chip.style.border = "1px solid rgba(79, 195, 247, 0.5)";
      } else {
        chip.style.border = "1px solid rgba(255,255,255,0.05)";
      }
      chip.addEventListener("click", () => {
        if (this.selectedBaseModels.has(model)) this.selectedBaseModels.delete(model);
        else this.selectedBaseModels.add(model);
        this.currentPage = 0;
        this.renderBaseModelFilters();
        this.renderLoras();
      });
      container.appendChild(chip);
    });
  }

  renderFolderFilters() {
    const container = this.element.querySelector('[data-role="folder-filters"]');
    if (!container) return;
    container.innerHTML = "";
    if (!this.folders || !this.folders.length) {
      container.innerHTML = `<div style="font-size:11px;color:var(--umi-ink-2);">No folders detected</div>`;
      return;
    }

    this.folders.slice(0, 80).forEach((folder) => {
      const chip = document.createElement("div");
      chip.className = "umi-lb-tag";
      chip.textContent = folder;
      chip.title = folder;
      chip.style.cursor = "pointer";
      chip.style.userSelect = "none";
      if (this.selectedFolders.has(folder)) {
        chip.style.background = "rgba(79, 195, 247, 0.35)";
        chip.style.border = "1px solid rgba(79, 195, 247, 0.5)";
      } else {
        chip.style.border = "1px solid rgba(255,255,255,0.05)";
      }
      chip.addEventListener("click", () => {
        if (this.selectedFolders.has(folder)) this.selectedFolders.delete(folder);
        else this.selectedFolders.add(folder);
        this.currentPage = 0;
        this.renderFolderFilters();
        this.renderLoras();
      });
      container.appendChild(chip);
    });
  }

  createTreeNodeHTML(node, path) {
    const isExpanded = this.expandedFolders.has(path);
    const hasChildren = Object.keys(node.children).length > 0;
    const isFolderActive = (path === "Lora" && this.pathFilter === "") || (this.pathFilter === path);
    
    let html = `
      <div class="umi-lb-tree-item ${isFolderActive ? 'active-folder' : ''}" data-path="${this.escapeHtmlAttr(path)}">
        <span class="umi-lb-tree-toggle ${isExpanded ? '' : 'collapsed'}" style="visibility: ${hasChildren ? 'visible' : 'hidden'}">▼</span>
        <span class="umi-lb-tree-name">${this.escapeHtml(node.name)}</span>
      </div>
    `;

    if (isExpanded) {
      html += `<div class="umi-lb-tree-children">`;
      Object.keys(node.children).sort().forEach(childKey => {
        html += this.createTreeNodeHTML(node.children[childKey], `${path}/${childKey}`);
      });
      node.files.sort((a,b) => a.name.localeCompare(b.name)).forEach(file => {
        const fName = file.filename || file.name;
        const isSelected = this.selected && (this.selected.filename || this.selected.name) === fName;
        html += `<div class="umi-lb-tree-file ${isSelected ? 'selected' : ''}" data-filename="${this.escapeHtmlAttr(fName)}" title="${this.escapeHtmlAttr(file.name)}">${this.escapeHtml(this.getCleanFileName(fName))}.safetensor</div>`;
      });
      html += `</div>`;
    }
    return html;
  }

  getActivationTags(lora) {
    const override = lora.override || {};
    const civitaiInfoTags = lora.civitai_info_tags || [];
    if (override.activation_tags && override.activation_tags.length > 0) return { tags: override.activation_tags, source: "override" };
    if (override.tags && override.tags.length > 0) return { tags: override.tags, source: "override" };
    if (civitaiInfoTags.length > 0) return { tags: civitaiInfoTags, source: "civitai_info" };
    if (lora.civitai?.trigger_words?.length > 0) return { tags: lora.civitai.trigger_words, source: "civitai" };
    if (lora.tags && lora.tags.length > 0) return { tags: lora.tags, source: "safetensors" };
    return { tags: [], source: "none" };
  }

  getPreviewUrl(lora) {
    const override = lora.override || {};
    if (override.preview_url) return override.preview_url;
    if (lora.local_preview) {
      const timestamp = lora.preview_mtime ? `&t=${encodeURIComponent(lora.preview_mtime)}` : '';
      return `/umiapp/preview?path=${encodeURIComponent(lora.local_preview)}${timestamp}`;
    }
    if (lora.civitai?.preview_url) return lora.civitai.preview_url;
    return null;
  }

  getLoraStrength(lora) {
    const saved = Number(lora?.override?.strength);
    return Number.isFinite(saved) ? Math.max(0, Math.min(3, saved)) : this.globalStrength;
  }

  async loadLoras(force = false) {
    const grid = this.element.querySelector('[data-role="grid"]');
    if (this.loras.length > 0 && this.hasLoaded && !force) {
      this.recalculatePageSize(); 
      this.renderFolderTree();
      this.renderLoras();
      return;
    }
    
    // Perform fetch
    if (force || !this.hasLoaded) {
        grid.innerHTML = '<div class="umi-lb-details-empty">Loading...</div>';
        if (await this.fetchLoras(force) === null) return;
        this.hasLoaded = true;
    }
    
    this.recalculatePageSize();
    this.renderFolderTree();
    this.renderBaseModelFilters();
    this.renderFolderFilters();
    this.renderLoras();
  }

  renderLoras() {
    const grid = this.element.querySelector('[data-role="grid"]');
    this.filtered = this.sortLoras(this.applyFilters(this.loras));
    if (this.lastError) {
      grid.innerHTML = `<div class="umi-lb-details-empty" style="color:var(--umi-danger);">Failed to load LoRAs: ${this.escapeHtml(this.lastError)}<br />Use Refresh LoRAs to retry.</div>`;
      this.renderPagination();
      this.renderSelectionBar();
      return;
    }
    if (!this.filtered.length) {
      grid.innerHTML = `<div class="umi-lb-details-empty">${this.loras.length ? "No results found" : "No LoRAs found"}</div>`;
      this.renderPagination();
      this.renderSelectionBar();
      return;
    }

    const totalPages = Math.ceil(this.filtered.length / this.pageSize);
    if (this.currentPage >= totalPages) this.currentPage = Math.max(0, totalPages - 1);

    const start = this.currentPage * this.pageSize;
    const end = start + this.pageSize;
    const pageItems = this.filtered.slice(start, end);
    grid.innerHTML = pageItems.map((lora) => this.createCardHTML(lora)).join("");
    grid.querySelectorAll(".umi-lb-card").forEach((card, idx) => {
      const selectCard = (event) => {
        const lora = pageItems[idx];
        const id = lora.filename || lora.name;
        if (event.ctrlKey || event.metaKey) {
          if (this.selectedIds.has(id)) this.selectedIds.delete(id);
          else this.selectedIds.add(id);
        } else if (event.shiftKey) {
          this.selectedIds.add(id);
        } else {
          this.selectedIds.clear();
          this.selectedIds.add(id);
        }
        this.selected = lora;
        this.localStrength = this.getLoraStrength(lora);
        this.renderFolderTree(); 
        this.renderLoras();
        this.renderDetails();
      };
      card.addEventListener("click", selectCard);
      card.addEventListener("keydown", (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          selectCard(event);
        }
      });
    });
    this.renderPagination();
    this.renderSelectionBar();
  }

  renderPagination() {
    const pagination = this.element.querySelector('[data-role="pagination"]');
    if (!pagination) return;
    const totalPages = Math.ceil(this.filtered.length / this.pageSize);
    if (totalPages <= 1) {
      pagination.innerHTML = "";
      return;
    }
    pagination.innerHTML = `
        <button class="umi-lb-btn" data-page="${this.currentPage - 1}" ${this.currentPage === 0 ? "disabled" : ""}>Prev</button>
        <span class="umi-lb-chip">Page <input type="text" class="umi-lb-page-input" value="${this.currentPage + 1}" /> of ${totalPages}</span>
        <button class="umi-lb-btn" data-page="${this.currentPage + 1}" ${this.currentPage >= totalPages - 1 ? "disabled" : ""}>Next</button>
    `;
    pagination.querySelectorAll("button[data-page]:not([disabled])").forEach((btn) => {
      btn.addEventListener("click", () => {
        this.currentPage = parseInt(btn.dataset.page, 10);
        this.renderLoras();
      });
    });
    const pageInput = pagination.querySelector(".umi-lb-page-input");
    if(pageInput) {
        pageInput.addEventListener("keydown", (e) => {
          if (e.key === "Enter") {
            let val = parseInt(e.target.value, 10);
            if (!isNaN(val) && val > 0 && val <= totalPages) {
              this.currentPage = val - 1;
              this.renderLoras();
            } else { e.target.value = this.currentPage + 1; }
          }
        });
        pageInput.addEventListener("click", (e) => e.target.select());
    }
  }

  renderSelectionBar() {
    const bar = this.element.querySelector('[data-role="selection-bar"]');
    if (!bar) return;
    const count = this.selectedIds.size;
    if (!count) {
      bar.className = "umi-lb-selection-bar";
      bar.innerHTML = "";
      return;
    }

    bar.className = "umi-lb-selection-bar active";
    bar.innerHTML = `
      <span class="umi-lb-chip">${count} selected</span>
      <button class="umi-lb-btn" data-action="select-page">Select page</button>
      <button class="umi-lb-btn" data-action="clear-selection">Clear</button>
      <button class="umi-lb-btn" data-action="copy-selected">Copy LoRA tags</button>
      <button class="umi-lb-btn" data-action="append-selected-wildcard">Append to wildcard</button>
      <button class="umi-lb-btn" data-action="fetch-selected">Fetch selected</button>
      <span class="umi-lb-selection-spacer"></span>
    `;

    bar.querySelector('[data-action="select-page"]').addEventListener("click", () => {
      const start = this.currentPage * this.pageSize;
      const end = start + this.pageSize;
      this.filtered.slice(start, end).forEach(lora => this.selectedIds.add(lora.filename || lora.name));
      this.renderLoras();
    });
    bar.querySelector('[data-action="clear-selection"]').addEventListener("click", () => {
      this.selectedIds.clear();
      this.renderLoras();
    });
    bar.querySelector('[data-action="copy-selected"]').addEventListener("click", () => this.copySelectedLoraTags());
    bar.querySelector('[data-action="append-selected-wildcard"]').addEventListener("click", () => this.appendSelectedToWildcard());
    bar.querySelector('[data-action="fetch-selected"]').addEventListener("click", () => this.fetchSelectedCivitai());
  }

  selectedLoras() {
    return Array.from(this.selectedIds)
      .map(id => this.loras.find(lora => (lora.filename || lora.name) === id))
      .filter(Boolean);
  }

  async copySelectedLoraTags() {
    const tags = this.selectedLoras().map(lora => `<lora:${lora.filename || lora.name}:${this.globalStrength.toFixed(1)}>`).join(", ");
    if (!tags) return;
    await this.copyText(tags, `Copied ${this.selectedIds.size} LoRA tags`);
  }

  loraWildcardLine(lora, includeActivation = false, strength = this.localStrength) {
    const loraName = lora.filename || lora.name;
    const numericStrength = Number(strength);
    const loraText = `<lora:${loraName}:${(Number.isFinite(numericStrength) ? numericStrength : 1).toFixed(1)}>`;
    if (!includeActivation) return loraText;
    const activation = this.getActivationTags(lora);
    const tags = activation.tags || [];
    return tags.length ? `${loraText}, ${tags.join(", ")}` : loraText;
  }

  wildcardName() {
    return this.element?.querySelector('[data-role="wildcard-name"]')?.value?.trim() || this.wildcardTarget || "";
  }

  async writeWildcard(name, content, mode = "append") {
    const target = String(name || "").trim();
    if (!target) {
      this.showNotification("Choose a wildcard name", true);
      return false;
    }
    if (!String(content || "").trim()) {
      this.showNotification("Nothing to write", true);
      return false;
    }
    try {
      const response = await fetch("/umiapp/wildcards/text/write", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: target, mode, content }),
      });
      const data = await response.json();
      if (!response.ok || data.success === false) {
        throw new Error(data.error || "Wildcard write failed");
      }
      this.wildcardTarget = data.name || target;
      await this.fetchWildcards();
      this.showNotification(mode === "append" ? "Added to wildcard" : "Wildcard saved");
      this.renderDetails();
      return true;
    } catch (error) {
      this.showNotification(error.message || "Wildcard write failed", true);
      return false;
    }
  }

  async appendSelectedToWildcard() {
    const selected = this.selectedLoras();
    if (!selected.length) return;
    const name = prompt("Append selected LoRAs to wildcard:", this.wildcardTarget || "");
    if (!name) return;
    const content = selected.map(lora => this.loraWildcardLine(lora, false, this.globalStrength)).join("\n");
    await this.writeWildcard(name, content, "append");
  }

  async fetchSelectedCivitai() {
    const selected = this.selectedLoras();
    if (!selected.length) return;
    const apiToken = localStorage.getItem("umi_civitai_api_token") || "";
    let processed = 0;
    let failed = 0;
    for (let i = 0; i < selected.length; i++) {
      this.updateStatus(`Fetching ${i + 1}/${selected.length}`, selected[i].filename || selected[i].name);
      const result = await this.fetchSingleCivitai(selected[i], false, "replace_civitai_info", apiToken);
      if (result && result.success) processed += 1;
      else failed += 1;
    }
    await this.loadLoras(true);
    this.updateStatus("Ready", `Fetched ${processed}/${selected.length}${failed ? `, ${failed} failed` : ""}`);
  }

  createCardHTML(lora) {
    const activation = this.getActivationTags(lora);
    const previewUrl = this.getPreviewUrl(lora);
    const cleanName = this.getCleanFileName(lora.filename || lora.name);
    const tags = activation.tags.slice(0, 20); 
    const tagHtml = tags.map((t) => `<span class="umi-lb-tag">#${this.escapeHtml(t)}</span>`).join("");
    const baseModel = lora.base_model || lora.civitai?.base_model || "";
    const badge = baseModel ? `<div class="umi-lb-badge">${this.escapeHtml(baseModel)}</div>` : "";
    const selectedClass = this.selected && this.selected.name === lora.name ? "selected" : "";
    const multiSelectedClass = this.selectedIds.has(lora.filename || lora.name) ? "selected" : "";
    const missingPreview = !previewUrl ? `<div class="umi-lb-badge" style="right:auto;left:6px;background:rgba(160,90,40,0.9);">No preview</div>` : "";

    return `
            <div class="umi-lb-card ${selectedClass || multiSelectedClass}" role="button" tabindex="0" aria-label="Select ${this.escapeHtmlAttr(cleanName)}">
                <div class="umi-lb-thumb">
                    ${previewUrl ? `<img src="${this.escapeHtmlAttr(previewUrl)}" alt="${this.escapeHtmlAttr(cleanName)}" loading="lazy" />` : ""}
                    ${badge}
                    ${missingPreview}
                    <div class="umi-lb-overlay">
                        <div class="umi-lb-card-name">${this.escapeHtml(cleanName)}</div>
                        <div class="umi-lb-tags">${tagHtml}</div>
                    </div>
                </div>
            </div>
        `;
  }

  renderDetails() {
    const details = this.element.querySelector('[data-role="details"]');
    if (!this.selected) {
      details.classList.remove('has-selection');
      details.innerHTML = '<div class="umi-lb-details-empty" style="color:var(--umi-ink-2);text-align:center;padding:20px;font-size:12px;">Select a LoRA</div>';
      return;
    }
    details.classList.add('has-selection');

    const lora = this.selected;
    const activation = this.getActivationTags(lora);
    const civitai = lora.civitai || {};
    const previewUrl = this.getPreviewUrl(lora);
    const override = lora.override || {};
    const previewPrompts = this.getPreviewPrompts(lora);
    
    // Check local metadata for URL first
    const civitaiUrl = civitai.url || (lora.metadata && lora.metadata.url) || null;
    
    const displayName = override.nickname || this.getCleanFileName(lora.filename || lora.name);
    const tagList = override.activation_text || activation.tags.join(", ");
    const baseModel = lora.base_model || civitai.base_model || "Unknown";
    const rawDescription = override.description || civitai.description || lora.local?.description || "";
    const description = this.stripHtml(rawDescription);

    details.innerHTML = `
            <button class="umi-lb-btn umi-lb-detail-back" data-action="close-details">Back to LoRAs</button>
            <div class="umi-lb-detail-section">
                <div class="umi-lb-detail-image-container">
                    ${previewUrl ? `<img class="umi-lb-detail-image" src="${this.escapeHtmlAttr(previewUrl)}" />` : ""}
                </div>
                
                <div class="umi-lb-detail-title umi-lb-editable" contenteditable="true" data-role="edit-name" title="Click to edit name">${this.escapeHtml(displayName)}</div>
                
                <div class="umi-lb-detail-meta">Source: ${this.escapeHtml(activation.source)} | Base: ${this.escapeHtml(baseModel)}</div>
                
                <div class="umi-lb-section">
                     <div class="umi-lb-detail-label">Specific Strength Override</div>
                     <div class="umi-lb-slider-row">
                         <input type="range" class="umi-range" data-role="local-strength" min="0" max="3" step="0.1" value="${this.localStrength}" />
                         <span class="umi-range-val" data-role="local-strength-val">${this.localStrength.toFixed(1)}</span>
                     </div>
                </div>

                <div class="umi-lb-detail-actions">
                    <button class="umi-lb-btn" data-action="insert">Insert</button>
                    <button class="umi-lb-btn" data-action="copy">Copy Tag</button>
                    <div style="position:relative; display:inline-block;">
                        <button class="umi-lb-btn" data-action="replace-preview">Replace Preview</button>
                        <div class="umi-lb-dropdown" id="umi-lb-preview-menu">
                            <div class="umi-lb-dropdown-item" data-action="preview-url">From URL</div>
                            <div class="umi-lb-dropdown-item" data-action="preview-local">From Computer</div>
                        </div>
                    </div>
                    ${civitaiUrl ? `<button class="umi-lb-btn" data-action="open">Open CivitAI</button>` : `<button class="umi-lb-btn" data-action="fetch">Fetch</button>`}
                    <button class="umi-lb-btn" data-action="view-preview-prompts">Preview Prompts${previewPrompts.length ? ` (${previewPrompts.length})` : ""}</button>
                    
                    <!-- New Manage Button -->
                    <div style="position:relative; display:inline-block;">
                        <button class="umi-lb-btn" data-action="manage">Manage</button>
                        <div class="umi-lb-dropdown" id="umi-lb-manage-menu">
                            <div class="umi-lb-dropdown-item" data-action="manage-open">Open Location</div>
                            <div class="umi-lb-dropdown-item" style="color:var(--umi-danger)" data-action="manage-delete">Delete Lora</div>
                        </div>
                    </div>

                </div>
            </div>
            
            <div class="umi-lb-detail-section">
                <div class="umi-lb-detail-label">Activation Tags (Edit and click Save)</div>
                <div class="umi-lb-detail-box umi-lb-editable" contenteditable="true" data-role="edit-tags">${this.escapeHtml(tagList)}</div>
                <button class="umi-lb-btn umi-lb-btn-gold" data-action="view-internal-tags">Internal Tags</button>
            </div>

            <div class="umi-lb-detail-section">
                <div class="umi-lb-detail-label">Wildcard</div>
                <input class="umi-lb-input" data-role="wildcard-name" list="umi-lb-wildcards" placeholder="AlexLora or folder/my_loras" value="${this.escapeHtmlAttr(this.wildcardTarget)}" />
                <datalist id="umi-lb-wildcards">${this.wildcards.map(name => `<option value="${this.escapeHtmlAttr(name)}"></option>`).join("")}</datalist>
                <div class="umi-lb-detail-box" style="margin-top:8px;max-height:92px;">${this.escapeHtml(this.loraWildcardLine(lora, true))}</div>
                <div class="umi-lb-detail-actions">
                    <button class="umi-lb-btn" data-action="append-wildcard">Append LoRA</button>
                    <button class="umi-lb-btn" data-action="append-wildcard-tags">Append LoRA + tags</button>
                    <button class="umi-lb-btn" data-action="overwrite-wildcard">Overwrite</button>
                </div>
            </div>
            
            <div class="umi-lb-detail-section">
                <div class="umi-lb-detail-label">Description (Edit and click Save)</div>
                <div class="umi-lb-detail-box umi-lb-editable" contenteditable="true" data-role="edit-desc" data-placeholder="No description">${this.escapeHtml(description)}</div>
            </div>

            <button class="umi-lb-btn umi-lb-btn-gold" data-action="save-metadata" style="margin-top:10px; background:var(--umi-ok); color:white; border-color:var(--umi-ok);">Save Metadata Changes</button>
        `;

    const locSlider = details.querySelector('[data-role="local-strength"]');
    const locVal = details.querySelector('[data-role="local-strength-val"]');
    if(locSlider) {
        locSlider.addEventListener('input', (e) => {
            this.localStrength = parseFloat(e.target.value);
            locVal.textContent = this.localStrength.toFixed(1);
        });
    }

    details.querySelector('[data-action="close-details"]')?.addEventListener('click', () => {
        this.selected = null;
        this.renderFolderTree();
        this.renderLoras();
        this.renderDetails();
    });

    const nameEl = details.querySelector('[data-role="edit-name"]');
    const tagsEl = details.querySelector('[data-role="edit-tags"]');
    const descEl = details.querySelector('[data-role="edit-desc"]');
    const wildcardEl = details.querySelector('[data-role="wildcard-name"]');
    if (wildcardEl) {
        wildcardEl.addEventListener("input", () => {
            this.wildcardTarget = wildcardEl.value.trim();
        });
    }

    // Logic for the Save Button
    const saveBtn = details.querySelector('[data-action="save-metadata"]');
    saveBtn.addEventListener('click', async () => {
        saveBtn.disabled = true;
        try {
            const nickname = nameEl.textContent.trim();
            const activationText = tagsEl.textContent.trim();
            const description = descEl.textContent.trim();
            const currentOverride = lora.override || {};
            await this.saveLoraOverride(lora.name, {
                ...currentOverride,
                nickname: nickname === this.getCleanFileName(lora.filename||lora.name) ? "" : nickname,
                activation_text: activationText,
                description,
                strength: this.localStrength
            });
            this.showNotification("Metadata Saved");
        } catch (error) {
            this.showNotification(error?.message || "Metadata save failed", true);
        } finally {
            if (saveBtn.isConnected) saveBtn.disabled = false;
        }
    });

    // Preview Dropdown
    const replaceBtn = details.querySelector('[data-action="replace-preview"]');
    const previewDropdown = document.getElementById('umi-lb-preview-menu');
    replaceBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        previewDropdown.classList.toggle('show');
        manageDropdown.classList.remove('show'); // close other
    });
    
    // Manage Dropdown
    const manageBtn = details.querySelector('[data-action="manage"]');
    const manageDropdown = document.getElementById('umi-lb-manage-menu');
    manageBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        manageDropdown.classList.toggle('show');
        if (manageDropdown.classList.contains('show')) {
            // Render as fixed overlay to avoid clipping
            manageDropdown.style.position = 'fixed';
            manageDropdown.style.left = '';
            manageDropdown.style.right = '';
            manageDropdown.style.top = '';
            manageDropdown.style.bottom = '';

            const btnRect = manageBtn.getBoundingClientRect();
            const dropdownRect = manageDropdown.getBoundingClientRect();
            const viewportWidth = window.innerWidth || document.documentElement.clientWidth;

            let left = btnRect.right - dropdownRect.width;
            if (left < 8) left = btnRect.left;
            if (left + dropdownRect.width > viewportWidth - 8) {
                left = Math.max(8, viewportWidth - dropdownRect.width - 8);
            }

            manageDropdown.style.left = `${Math.round(left)}px`;
            manageDropdown.style.top = `${Math.round(btnRect.bottom)}px`;
        } else {
            manageDropdown.style.position = '';
        }
        previewDropdown.classList.remove('show'); // close other
    });

    // Manage Actions
    details.querySelector('[data-action="manage-open"]').addEventListener('click', async () => {
        try {
            const response = await fetch("/umiapp/loras/manage/open", {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ lora_name: lora.name, filename: lora.filename })
            });
            const data = await response.json();
            if (!response.ok || !data.success) throw new Error(data.error || 'Could not open location');
            this.showNotification("Opened location");
        } catch(e) {
            console.error(e);
            this.showNotification(e?.message || "Could not open location", true);
        }
    });

    details.querySelector('[data-action="manage-delete"]').addEventListener('click', async () => {
        if(confirm(`Are you sure you want to delete "${lora.name}" and all associated files?\nThis cannot be undone.`)) {
             try {
                const res = await fetch("/umiapp/loras/manage/delete", { 
                    method: "POST", headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ lora_name: lora.name, filename: lora.filename })
                });
                const data = await res.json();
                if(data.success) {
                    this.showNotification("Deleted");
                    this.selectedIds.delete(lora.filename || lora.name);
                    this.selected = null;
                    await this.loadLoras(true);
                } else {
                    this.showNotification(data.error || "Delete failed", true);
                }
            } catch(e) { console.error(e); this.showNotification("Delete failed", true); }
        }
    });

    details.querySelector('[data-action="preview-url"]').addEventListener('click', async () => {
        const url = prompt("Enter Image URL:");
        if (url) {
            await this.replaceLoraPreviewFromUrl(lora.name, url);
        }
    });

    details.querySelector('[data-action="preview-local"]').addEventListener('click', () => {
        document.getElementById('umi-lb-file-input').click();
    });

    details.querySelector('[data-action="view-internal-tags"]').addEventListener('click', () => {
        this.fetchInternalTags(lora);
    });

    const previewPromptsBtn = details.querySelector('[data-action="view-preview-prompts"]');
    if (previewPromptsBtn) {
        previewPromptsBtn.addEventListener('click', () => this.showPreviewPromptsModal(lora));
    }

    details.querySelector('[data-action="insert"]').addEventListener("click", () => this.insertLora(lora));
    details.querySelector('[data-action="copy"]').addEventListener("click", async () => {
      const text = `<lora:${lora.filename || lora.name}:${this.localStrength.toFixed(1)}>`;
      await this.copyText(text, "Copied");
    });
    details.querySelector('[data-action="append-wildcard"]').addEventListener("click", () => {
      this.writeWildcard(this.wildcardName(), this.loraWildcardLine(lora, false), "append");
    });
    details.querySelector('[data-action="append-wildcard-tags"]').addEventListener("click", () => {
      this.writeWildcard(this.wildcardName(), this.loraWildcardLine(lora, true), "append");
    });
    details.querySelector('[data-action="overwrite-wildcard"]').addEventListener("click", () => {
      this.writeWildcard(this.wildcardName(), this.loraWildcardLine(lora, false), "overwrite");
    });
    
    const openBtn = details.querySelector('[data-action="open"]');
    if (openBtn) openBtn.addEventListener("click", () => window.open(civitaiUrl, "_blank"));
    const fetchBtn = details.querySelector('[data-action="fetch"]');
    if (fetchBtn) fetchBtn.addEventListener("click", () => this.fetchSingleCivitai(lora, true, "replace_civitai_info", localStorage.getItem("umi_civitai_api_token") || ""));
  }

  insertLora(lora) {
    const loraName = lora.filename || lora.name;
    const loraText = `<lora:${loraName}:${this.localStrength.toFixed(1)}>`;
    const activation = this.getActivationTags(lora);
    const activeNode = this.findActiveUmiNode();
    if (activeNode) {
      const promptWidget = activeNode.widgets.find((w) => w.name === "text");
      if (promptWidget) {
        let val = promptWidget.value || "";
        let newValue = val ? `${val}, ${loraText}` : loraText;
        if (activation.tags.length) newValue = `${newValue}, ${activation.tags.slice(0, 3).join(", ")}`;
        promptWidget.value = newValue;
        if (promptWidget.callback) promptWidget.callback(newValue);
        app.graph.setDirtyCanvas(true, true);
        this.showNotification(`Inserted`);
      }
    } else {
      this.copyText(loraText, "Copied");
    }
  }

  findActiveUmiNode() {
    const sel = app.canvas.selected_nodes;
    if (sel) {
      for (const id in sel) {
        const n = app.graph.getNodeById(parseInt(id, 10));
        if (n && n.type.startsWith("UmiAIWildcard")) return n;
      }
    }
    return app.graph._nodes.find(n => n.type.startsWith("UmiAIWildcard")) || null;
  }

  async fetchSingleCivitai(lora, refreshAfter = true, mode = "replace_civitai_info", apiToken = "") {
    try {
      this.updateStatus("Fetching...", lora.name);
      if (refreshAfter) this.showNotification("Fetching...");
      const res = await fetch("/umiapp/loras/civitai/single", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ lora_name: lora.name, mode, api_token: apiToken }),
      });
      const data = await res.json();
      if (data.success) {
        if (!refreshAfter) return data;
        const currentName = this.selected?.name;
        const currentPage = this.currentPage;
        await this.loadLoras(true);
        this.selected = this.loras.find(item => item.name === currentName) || null;
        this.currentPage = currentPage;
        this.renderLoras();
        this.renderDetails();
        this.updateStatus(data.warning ? "Completed with warning" : "Ready", data.warning || "");
        this.showNotification(data.warning || "Fetch Complete", Boolean(data.warning));
        return true;
      } else {
        this.updateStatus("Error", data.error || "Fetch failed");
        if (refreshAfter) this.showNotification(data.error || "Fetch Failed", true);
        return data;
      }
    } catch (e) {
        this.updateStatus("Error", e.message);
        if (refreshAfter) this.showNotification("Error", true);
        return { success: false, error: e.message };
    }
  }

  async saveLoraOverride(loraName, override) {
    const res = await fetch("/umiapp/loras/overrides/save", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lora_name: loraName, override }),
    });
    let data = null;
    try { data = await res.json(); } catch (_) { data = null; }
    if (!res.ok || !data || !data.success) {
      throw new Error(data?.error || `Metadata save failed (HTTP ${res.status})`);
    }
    // Persist navigation and selection state
    const prevPage = this.currentPage;
    const prevName = this.selected?.name;
    await this.loadLoras(true);
    this.selected = this.loras.find(i => i.name === prevName) || null;
    this.currentPage = prevPage;
    this.renderLoras();
    this.renderDetails();
    return true;
  }

  async replaceLoraPreviewFromUrl(loraName, url) {
    try {
      this.showNotification("Updating preview...");
      const res = await fetch("/umiapp/loras/preview/replace_url", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ lora_name: loraName, url }),
      });
      const data = await res.json();
      if (res.ok && data.success) {
        const prevName = this.selected?.name;
        const prevPage = this.currentPage;
        await this.loadLoras(true);
        this.selected = this.loras.find(i => i.name === prevName) || null;
        this.currentPage = prevPage;
        this.renderLoras();
        this.renderDetails();
        this.showNotification("Preview updated");
      } else {
        this.showNotification(data.error || "Preview update failed", true);
      }
    } catch (e) {
      console.error(e);
      this.showNotification("Preview update failed", true);
    }
  }

  showNotification(msg, isError = false) {
    const n = document.createElement("div");
    n.style.cssText = `position:fixed;top:20px;right:20px;background:${isError ? "var(--umi-danger)" : "var(--umi-ok-soft)"};color:white;padding:8px 14px;border-radius:6px;z-index:10002;font-size:12px;`;
    n.textContent = msg;
    document.body.appendChild(n);
    setTimeout(() => n.remove(), 1500);
  }

  async copyText(text, successMessage = "Copied") {
    try {
      await navigator.clipboard.writeText(String(text || ""));
      this.showNotification(successMessage);
      return true;
    } catch (error) {
      console.error("[Umi LoRA Browser] Clipboard write failed:", error);
      this.showNotification("Clipboard access failed", true);
      return false;
    }
  }

  escapeHtml(t) { return !t ? "" : String(t).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;"); }
  escapeHtmlAttr(t) { return this.escapeHtml(t).replace(/\n/g, " "); }
  stripHtml(v) { if (!v) return ""; let doc = new DOMParser().parseFromString(String(v), "text/html"); return doc.body.textContent.trim() || ""; }
  async show() {
    this.previousFocus = document.activeElement;
    if (!this.element) this.createPanel();
    this.element.style.display = "block";
    this.element.querySelector('[data-role="search"]')?.focus();
    await Promise.all([this.fetchWildcards(), this.loadLoras()]);
    if (this.element.style.display === 'none') return;
    this.renderSelectionBar();
    this.renderDetails();
  }
  scheduleSearch() {
    clearTimeout(this.searchTimer);
    this.searchTimer = setTimeout(() => {
      this.searchTimer = null;
      this.renderLoras();
    }, 100);
  }

  hide() {
    clearTimeout(this.searchTimer);
    this.searchTimer = null;
    this.tagsRequest = (this.tagsRequest || 0) + 1;
    this.fetchGeneration++;
    if (this.element) {
      this.element.querySelector('.umi-lb-sidebar')?.classList.remove('filters-open');
      this.element.querySelector('[data-action="toggle-filters"]')?.setAttribute('aria-expanded', 'false');
      this.closeDropdowns();
      this.element.style.display = "none";
      this.selectedIds.clear();
      if (this.previousFocus && typeof this.previousFocus.focus === 'function') this.previousFocus.focus();
    }
  }
}

const loraBrowser = new LoraBrowserPanel();
window.umiLoraBrowser = loraBrowser;
app.registerExtension({
  name: "Umi.LoraBrowser",
  async setup() {
    const menu = document.querySelector(".comfy-menu");
    if (menu) {
      const btn = document.createElement("button");
      btn.textContent = "LoRA Browser";
      btn.onclick = () => loraBrowser.show();
      menu.appendChild(btn);
    }
    document.addEventListener("keydown", (e) => { if (e.altKey && !e.ctrlKey && e.key.toLowerCase() === "l") { e.preventDefault(); loraBrowser.show(); } });
  }
});
