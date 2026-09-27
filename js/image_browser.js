import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { ensureUmiTheme } from "./umi_theme.js";

class ImageBrowser {
    constructor() {
        this.element = null;
        this.images = [];
        this.imageMap = new Map();
        this.currentPage = 0;
        this.pageSize = 30;
        this.totalImages = 0;
        this.sortBy = "newest";
        this.selectedImage = null;
        this.selectedIds = new Set();
        this.facets = { folders: [], models: [], loras: [], samplers: [], tags: [] };
        this.lastError = null;
        this.refreshTimer = null;
        this.loadGeneration = 0;
        this.scanController = null;
        this.previousFocus = null;
        this.filters = {
            search: "",
            favoritesOnly: false,
            dateFrom: "",
            dateTo: "",
            stepsMin: "",
            stepsMax: "",
            cfgMin: "",
            cfgMax: "",
            widthMin: "",
            widthMax: "",
            heightMin: "",
            heightMax: "",
            orientation: "any",
            recursive: true,
            folders: new Set(),
            models: new Set(),
            loras: new Set(),
            samplers: new Set(),
            tags: new Set()
        };
        this.tagSearch = "";
        this.contextMenu = null;
        this.compareOverlay = null;
    }

    createPanel() {
        const panel = document.createElement("div");
        panel.className = "umi-image-browser";
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

        panel.innerHTML = this.getStyles() + this.getLayout();
        panel.setAttribute("role", "dialog");
        panel.setAttribute("aria-modal", "true");
        panel.setAttribute("aria-label", "Image Browser");
        panel.tabIndex = -1;

        this.element = panel;
        document.body.appendChild(panel);
        this.contextMenu = panel.querySelector('[data-role="context-menu"]');
        this.compareOverlay = panel.querySelector('[data-role="compare"]');
        const body = panel.querySelector('.umi-ib-body');
        if (body) {
            body.style.display = 'grid';
            body.style.width = '100%';
            body.style.height = '100%';
            body.style.gridTemplateColumns = '260px minmax(0, 1fr) 360px';
        }
        const main = panel.querySelector('.umi-ib-main');
        if (main) {
            main.style.flex = '1';
            main.style.minWidth = '0';
        }
        const grid = panel.querySelector('.umi-ib-grid');
        if (grid) {
            grid.style.flex = '1';
            grid.style.minHeight = '0';
        }
        this.setDetailsVisible(false);
        this.bindEvents();
    }

    getStyles() {
        ensureUmiTheme();
        return `
            <style>
                .umi-ib-root {
                    display: flex;
                    flex-direction: column;
                    height: 100%;
                    width: 100%;
                    flex: 1;
                }
                .umi-ib-header {
                    display: flex;
                    align-items: center;
                    justify-content: space-between;
                    padding: 12px 18px;
                    border-bottom: 1px solid var(--umi-rule);
                    background: var(--umi-surface);
                }
                .umi-ib-title {
                    font-size: 18px;
                    font-weight: 600;
                    color: var(--umi-accent);
                }
                .umi-ib-header-actions {
                    display: flex;
                    gap: 8px;
                    align-items: center;
                }
                .umi-ib-btn {
                    background: var(--umi-surface-alt);
                    color: var(--umi-ink);
                    border: 1px solid var(--umi-rule-strong);
                    padding: 6px 10px;
                    border-radius: 6px;
                    cursor: pointer;
                    font-size: 12px;
                }
                .umi-ib-btn:hover {
                    border-color: var(--umi-rule-hover);
                }
                .umi-ib-select {
                    background: var(--umi-surface);
                    color: var(--umi-ink);
                    border: 1px solid var(--umi-rule-strong);
                    padding: 6px 8px;
                    border-radius: 6px;
                    font-size: 12px;
                }
                .umi-ib-body {
                    display: grid;
                    grid-template-columns: 260px minmax(0, 1fr) 360px;
                    height: 100%;
                    width: 100%;
                    flex: 1;
                    min-height: 0;
                }
                .umi-ib-sidebar {
                    border-right: 1px solid var(--umi-rule);
                    padding: 14px;
                    overflow-y: auto;
                    background: var(--umi-sunken);
                    min-width: 0;
                }
                .umi-ib-main {
                    position: relative;
                    overflow: hidden;
                    display: flex;
                    flex-direction: column;
                    min-width: 0;
                }
                .umi-ib-grid {
                    display: grid;
                    grid-template-columns: repeat(auto-fill, minmax(200px, 200px));
                    justify-content: start;
                    align-content: start;
                    gap: 12px;
                    padding: 14px;
                    overflow-y: auto;
                    height: 100%;
                    min-height: 0;
                }
                .umi-ib-details {
                    border-left: 1px solid var(--umi-rule);
                    padding: 14px;
                    overflow-y: auto;
                    background: var(--umi-sunken);
                    min-width: 0;
                }
                .umi-ib-details-back { display: none; }
                .umi-ib-section {
                    margin-bottom: 16px;
                }
                .umi-ib-section-title {
                    font-size: 12px;
                    letter-spacing: 0.08em;
                    text-transform: uppercase;
                    color: var(--umi-ink-2);
                    margin-bottom: 8px;
                }
                .umi-ib-input {
                    width: 100%;
                    padding: 6px 8px;
                    background: var(--umi-surface);
                    border: 1px solid var(--umi-rule-strong);
                    border-radius: 6px;
                    color: var(--umi-ink);
                    font-size: 12px;
                }
                .umi-ib-row {
                    display: flex;
                    gap: 8px;
                }
                .umi-ib-checkbox {
                    display: flex;
                    align-items: center;
                    gap: 6px;
                    font-size: 12px;
                    color: var(--umi-ink);
                }
                .umi-ib-facet-list {
                    display: flex;
                    flex-direction: column;
                    gap: 6px;
                    max-height: 180px;
                    overflow-y: auto;
                    padding-right: 4px;
                }
                .umi-ib-facet-item {
                    display: flex;
                    justify-content: space-between;
                    gap: 8px;
                    font-size: 12px;
                }
                .umi-ib-facet-item label {
                    display: flex;
                    align-items: center;
                    gap: 6px;
                    cursor: pointer;
                }
                .umi-ib-facet-count {
                    color: var(--umi-ink-2);
                }
                .umi-ib-card {
                    background: var(--umi-ground);
                    border: 1px solid var(--umi-rule);
                    border-radius: 8px;
                    overflow: hidden;
                    cursor: pointer;
                    transition: transform 0.1s ease, border-color 0.1s ease;
                    position: relative;
                }
                .umi-ib-card:hover {
                    border-color: var(--umi-accent-soft);
                    transform: translateY(-2px);
                }
                .umi-ib-card.selected {
                    border-color: var(--umi-accent);
                    box-shadow: 0 0 0 1px var(--umi-accent) inset;
                }
                .umi-ib-thumb {
                    width: 100%;
                    height: 180px;
                    background-size: cover;
                    background-position: center;
                    position: relative;
                }
                .umi-ib-card-meta {
                    padding: 8px;
                }
                .umi-ib-card-name {
                    font-size: 11px;
                    color: var(--umi-ink);
                    white-space: nowrap;
                    overflow: hidden;
                    text-overflow: ellipsis;
                }
                .umi-ib-card-sub {
                    font-size: 10px;
                    color: var(--umi-ink-2);
                    margin-top: 4px;
                }
                .umi-ib-badge {
                    position: absolute;
                    top: 6px;
                    right: 6px;
                    background: var(--umi-ok-soft);
                    color: var(--umi-ink-strong);
                    padding: 2px 6px;
                    font-size: 9px;
                    border-radius: 4px;
                }
                .umi-ib-fav {
                    position: absolute;
                    top: 6px;
                    left: 6px;
                    background: rgba(0,0,0,0.6);
                    color: var(--umi-warn);
                    border: none;
                    font-size: 12px;
                    padding: 2px 6px;
                    border-radius: 4px;
                    cursor: pointer;
                }
                .umi-ib-tags {
                    display: flex;
                    gap: 4px;
                    flex-wrap: wrap;
                    margin-top: 6px;
                }
                .umi-ib-tag {
                    background: var(--umi-surface-alt);
                    color: var(--umi-ink);
                    font-size: 9px;
                    padding: 2px 6px;
                    border-radius: 4px;
                }
                .umi-ib-tag[data-tag] {
                    cursor: pointer;
                }
                .umi-ib-fav--off {
                    opacity: 1;
                    color: var(--umi-ink-on-media);
                }
                .umi-ib-pagination {
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    gap: 8px;
                    padding: 10px;
                    border-top: 1px solid var(--umi-rule);
                    background: var(--umi-sunken);
                }
                .umi-ib-selection-bar {
                    display: none;
                    align-items: center;
                    gap: 8px;
                    padding: 8px 14px;
                    border-bottom: 1px solid var(--umi-rule);
                    background: var(--umi-ground);
                }
                .umi-ib-selection-bar.active {
                    display: flex;
                }
                .umi-ib-selection-spacer {
                    flex: 1;
                }
                .umi-ib-page-input {
                    background: transparent;
                    border: 1px solid var(--umi-rule-strong);
                    color: var(--umi-accent);
                    width: 35px;
                    text-align: center;
                    font-size: 11px;
                    border-radius: 4px;
                    margin: 0 4px;
                    padding: 2px 4px;
                }
                .umi-ib-page-input:focus {
                    outline: none;
                    border-color: var(--umi-accent);
                }
                .umi-ib-details-empty {
                    color: var(--umi-ink-2);
                    text-align: center;
                    padding: 20px;
                    font-size: 12px;
                }
                .umi-ib-detail-image {
                    width: 100%;
                    border-radius: 6px;
                    margin-bottom: 10px;
                }
                .umi-ib-detail-title {
                    font-size: 14px;
                    color: var(--umi-accent);
                    margin-bottom: 6px;
                }
                .umi-ib-detail-meta {
                    font-size: 11px;
                    color: var(--umi-ink);
                    margin-bottom: 10px;
                }
                .umi-ib-detail-section {
                    margin-bottom: 12px;
                }
                .umi-ib-detail-label {
                    font-size: 11px;
                    color: var(--umi-ink-2);
                    margin-bottom: 4px;
                }
                .umi-ib-detail-box {
                    background: var(--umi-surface);
                    border: 1px solid var(--umi-rule);
                    border-radius: 6px;
                    padding: 8px;
                    font-size: 12px;
                    color: var(--umi-ink);
                    max-height: 160px;
                    overflow-y: auto;
                    white-space: pre-wrap;
                }
                .umi-ib-detail-actions {
                    display: flex;
                    gap: 8px;
                    margin-top: 6px;
                }
                .umi-ib-context-menu {
                    position: fixed;
                    display: none;
                    background: var(--umi-surface);
                    border: 1px solid var(--umi-rule);
                    border-radius: 6px;
                    padding: 6px 0;
                    z-index: 10002;
                    min-width: 180px;
                }
                .umi-ib-context-menu button {
                    width: 100%;
                    background: none;
                    border: none;
                    color: var(--umi-ink);
                    padding: 6px 12px;
                    text-align: left;
                    font-size: 12px;
                    cursor: pointer;
                }
                .umi-ib-context-menu button:hover {
                    background: var(--umi-surface-alt);
                }
                .umi-ib-compare {
                    position: fixed;
                    top: 60px;
                    left: 60px;
                    right: 60px;
                    bottom: 60px;
                    background: var(--umi-sunken);
                    border: 1px solid var(--umi-rule);
                    border-radius: 10px;
                    z-index: 10001;
                    display: none;
                    flex-direction: column;
                }
                .umi-ib-compare-header {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    padding: 10px 14px;
                    border-bottom: 1px solid var(--umi-rule);
                }
                .umi-ib-compare-body {
                    display: grid;
                    grid-template-columns: 1fr 1fr;
                    gap: 12px;
                    padding: 12px;
                    overflow: auto;
                }
                .umi-ib-compare-card {
                    background: var(--umi-ground);
                    border: 1px solid var(--umi-rule);
                    border-radius: 8px;
                    padding: 10px;
                }
                .umi-ib-compare-card img {
                    width: 100%;
                    border-radius: 6px;
                    margin-bottom: 8px;
                }
                .umi-ib-chip {
                    display: inline-flex;
                    align-items: center;
                    gap: 6px;
                    font-size: 11px;
                    background: var(--umi-surface);
                    border: 1px solid var(--umi-rule);
                    padding: 4px 8px;
                    border-radius: 6px;
                }
                .umi-ib-filter-toggle {
                    display: none;
                }
                @media (max-width: 900px) {
                    .umi-ib-header {
                        align-items: flex-start;
                        gap: 8px;
                        padding: 10px;
                    }
                    .umi-ib-header-actions {
                        justify-content: flex-end;
                        flex-wrap: wrap;
                    }
                    .umi-ib-filter-toggle {
                        display: inline-block;
                    }
                    .umi-ib-body {
                        grid-template-columns: minmax(0, 1fr) !important;
                        position: relative;
                    }
                    .umi-ib-sidebar {
                        position: absolute;
                        inset: 0 auto 0 0;
                        width: min(280px, 88vw);
                        z-index: 5;
                        transform: translateX(-105%);
                        transition: transform 160ms ease;
                        box-shadow: 4px 0 18px rgba(0,0,0,.4);
                    }
                    .umi-ib-sidebar.filters-open {
                        transform: translateX(0);
                    }
                    .umi-ib-details {
                        position: absolute;
                        inset: 0 0 0 auto;
                        width: min(360px, 90vw);
                        z-index: 4;
                        box-shadow: -4px 0 18px rgba(0,0,0,.4);
                    }
                    .umi-ib-details-back { display: inline-flex; margin-bottom: 8px; }
                    .umi-ib-grid {
                        grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
                    }
                }
            </style>
        `;
    }

    getLayout() {
        return `
            <div class="umi-ib-root">
                <div class="umi-ib-header">
                    <div class="umi-ib-title">Image Browser</div>
                    <div class="umi-ib-header-actions">
                        <button class="umi-ib-btn umi-ib-filter-toggle" data-action="toggle-filters" aria-expanded="false">Filters</button>
                        <button class="umi-ib-btn" data-action="refresh">Refresh</button>
                        <select class="umi-ib-select" data-role="sort">
                            <option value="newest">Newest</option>
                            <option value="oldest">Oldest</option>
                            <option value="name">Name</option>
                            <option value="resolution">Resolution</option>
                            <option value="size">File size</option>
                            <option value="steps">Steps</option>
                            <option value="cfg">CFG</option>
                            <option value="seed">Seed</option>
                        </select>
                        <select class="umi-ib-select" data-role="page-size">
                            <option value="15">15</option>
                            <option value="30" selected>30</option>
                            <option value="60">60</option>
                        </select>
                        <button class="umi-ib-btn" data-action="close">Close</button>
                    </div>
                </div>
                <div class="umi-ib-body">
                    <aside class="umi-ib-sidebar">
                        <div class="umi-ib-section">
                            <div class="umi-ib-section-title">Search</div>
                            <input class="umi-ib-input" data-role="search" placeholder="Search prompts, models, tags" />
                        </div>
                        <div class="umi-ib-section">
                            <label class="umi-ib-checkbox">
                                <input type="checkbox" data-role="favorites-only" /> Favorites only
                            </label>
                        </div>
                        <div class="umi-ib-section">
                            <label class="umi-ib-checkbox">
                                <input type="checkbox" data-role="recursive-scan" checked /> Include subfolders
                            </label>
                        </div>
                        <div class="umi-ib-section">
                            <div class="umi-ib-section-title">Date Range</div>
                            <div class="umi-ib-row">
                                <input class="umi-ib-input" type="date" data-role="date-from" />
                                <input class="umi-ib-input" type="date" data-role="date-to" />
                            </div>
                        </div>
                        <div class="umi-ib-section">
                            <div class="umi-ib-section-title">Steps</div>
                            <div class="umi-ib-row">
                                <input class="umi-ib-input" type="number" min="0" data-role="steps-min" placeholder="Min" />
                                <input class="umi-ib-input" type="number" min="0" data-role="steps-max" placeholder="Max" />
                            </div>
                        </div>
                        <div class="umi-ib-section">
                            <div class="umi-ib-section-title">CFG</div>
                            <div class="umi-ib-row">
                                <input class="umi-ib-input" type="number" step="0.1" min="0" data-role="cfg-min" placeholder="Min" />
                                <input class="umi-ib-input" type="number" step="0.1" min="0" data-role="cfg-max" placeholder="Max" />
                            </div>
                        </div>
                        <div class="umi-ib-section">
                            <div class="umi-ib-section-title">Dimensions</div>
                            <select class="umi-ib-select" data-role="orientation" style="width:100%; margin-bottom:8px;">
                                <option value="any">Any orientation</option>
                                <option value="portrait">Portrait</option>
                                <option value="landscape">Landscape</option>
                                <option value="square">Square</option>
                            </select>
                            <div class="umi-ib-row">
                                <input class="umi-ib-input" type="number" min="0" data-role="width-min" placeholder="Min W" />
                                <input class="umi-ib-input" type="number" min="0" data-role="width-max" placeholder="Max W" />
                            </div>
                            <div class="umi-ib-row">
                                <input class="umi-ib-input" type="number" min="0" data-role="height-min" placeholder="Min H" />
                                <input class="umi-ib-input" type="number" min="0" data-role="height-max" placeholder="Max H" />
                            </div>
                        </div>
                        <div class="umi-ib-section">
                            <div class="umi-ib-section-title">Folders</div>
                            <div class="umi-ib-facet-list" data-facet="folders"></div>
                        </div>
                        <div class="umi-ib-section">
                            <div class="umi-ib-section-title">Models</div>
                            <div class="umi-ib-facet-list" data-facet="models"></div>
                        </div>
                        <div class="umi-ib-section">
                            <div class="umi-ib-section-title">LoRAs</div>
                            <div class="umi-ib-facet-list" data-facet="loras"></div>
                        </div>
                        <div class="umi-ib-section">
                            <div class="umi-ib-section-title">Samplers</div>
                            <div class="umi-ib-facet-list" data-facet="samplers"></div>
                        </div>
                        <div class="umi-ib-section">
                            <div class="umi-ib-section-title">Tags</div>
                            <input class="umi-ib-input" data-role="tag-search" placeholder="Filter tags" />
                            <div class="umi-ib-facet-list" data-facet="tags"></div>
                        </div>
                        <button class="umi-ib-btn" data-action="clear-filters">Clear filters</button>
                    </aside>
                    <main class="umi-ib-main">
                        <div class="umi-ib-selection-bar" data-role="selection-bar"></div>
                        <div class="umi-ib-grid" data-role="grid"></div>
                        <div class="umi-ib-pagination" data-role="pagination"></div>
                    </main>
                    <aside class="umi-ib-details" data-role="details">
                        <div class="umi-ib-details-empty">Select an image to view details.</div>
                    </aside>
                </div>
                <div class="umi-ib-context-menu" data-role="context-menu"></div>
                <div class="umi-ib-compare" data-role="compare"></div>
            </div>
        `;
    }

    bindEvents() {
        const closeBtn = this.element.querySelector('[data-action="close"]');
        closeBtn.addEventListener('click', () => this.hide());

        const refreshBtn = this.element.querySelector('[data-action="refresh"]');
        refreshBtn.addEventListener('click', () => this.loadImages());

        const filterToggle = this.element.querySelector('[data-action="toggle-filters"]');
        const sidebar = this.element.querySelector('.umi-ib-sidebar');
        filterToggle.addEventListener('click', () => {
            const isOpen = sidebar.classList.toggle('filters-open');
            filterToggle.setAttribute('aria-expanded', String(isOpen));
        });

        const sortSelect = this.element.querySelector('[data-role="sort"]');
        sortSelect.addEventListener('change', (e) => {
            this.sortBy = e.target.value;
            this.currentPage = 0;
            this.loadImages();
        });

        const pageSizeSelect = this.element.querySelector('[data-role="page-size"]');
        pageSizeSelect.addEventListener('change', (e) => {
            this.pageSize = parseInt(e.target.value, 10);
            this.currentPage = 0;
            this.loadImages();
        });

        const searchInput = this.element.querySelector('[data-role="search"]');
        searchInput.addEventListener('input', (e) => {
            this.filters.search = e.target.value.toLowerCase();
            this.scheduleRefresh();
        });

        const favoritesOnly = this.element.querySelector('[data-role="favorites-only"]');
        favoritesOnly.addEventListener('change', (e) => {
            this.filters.favoritesOnly = e.target.checked;
            this.currentPage = 0;
            this.loadImages();
        });

        const recursiveScan = this.element.querySelector('[data-role="recursive-scan"]');
        recursiveScan.addEventListener('change', (e) => {
            this.filters.recursive = e.target.checked;
            this.currentPage = 0;
            this.loadImages();
        });

        const dateFrom = this.element.querySelector('[data-role="date-from"]');
        const dateTo = this.element.querySelector('[data-role="date-to"]');
        dateFrom.addEventListener('change', (e) => {
            this.filters.dateFrom = e.target.value;
            this.scheduleRefresh();
        });
        dateTo.addEventListener('change', (e) => {
            this.filters.dateTo = e.target.value;
            this.scheduleRefresh();
        });

        const stepsMin = this.element.querySelector('[data-role="steps-min"]');
        const stepsMax = this.element.querySelector('[data-role="steps-max"]');
        stepsMin.addEventListener('input', (e) => {
            this.filters.stepsMin = e.target.value;
            this.scheduleRefresh();
        });
        stepsMax.addEventListener('input', (e) => {
            this.filters.stepsMax = e.target.value;
            this.scheduleRefresh();
        });

        const cfgMin = this.element.querySelector('[data-role="cfg-min"]');
        const cfgMax = this.element.querySelector('[data-role="cfg-max"]');
        cfgMin.addEventListener('input', (e) => {
            this.filters.cfgMin = e.target.value;
            this.scheduleRefresh();
        });
        cfgMax.addEventListener('input', (e) => {
            this.filters.cfgMax = e.target.value;
            this.scheduleRefresh();
        });

        ['width-min', 'width-max', 'height-min', 'height-max'].forEach(role => {
            const input = this.element.querySelector(`[data-role="${role}"]`);
            const key = role.replace(/-([a-z])/g, (_, char) => char.toUpperCase());
            input.addEventListener('input', (e) => {
                this.filters[key] = e.target.value;
                this.scheduleRefresh();
            });
        });

        const orientation = this.element.querySelector('[data-role="orientation"]');
        orientation.addEventListener('change', (e) => {
            this.filters.orientation = e.target.value;
            this.currentPage = 0;
            this.loadImages();
        });

        const tagSearch = this.element.querySelector('[data-role="tag-search"]');
        tagSearch.addEventListener('input', (e) => {
            this.tagSearch = e.target.value.toLowerCase();
            this.renderFacets();
        });

        const clearFilters = this.element.querySelector('[data-action="clear-filters"]');
        clearFilters.addEventListener('click', () => {
            this.resetFilters();
        });

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.element.style.display !== 'none') {
                if (this.compareOverlay && this.compareOverlay.style.display === 'flex') {
                    this.compareOverlay.style.display = 'none';
                } else {
                    this.hide();
                }
            }
        });

        document.addEventListener('click', () => {
            if (this.contextMenu && this.contextMenu.style.display === 'block') {
                this.contextMenu.style.display = 'none';
            }
        });
    }

    resetFilters() {
        this.filters = {
            search: "",
            favoritesOnly: false,
            dateFrom: "",
            dateTo: "",
            stepsMin: "",
            stepsMax: "",
            cfgMin: "",
            cfgMax: "",
            widthMin: "",
            widthMax: "",
            heightMin: "",
            heightMax: "",
            orientation: "any",
            recursive: true,
            folders: new Set(),
            models: new Set(),
            loras: new Set(),
            samplers: new Set(),
            tags: new Set()
        };
        this.tagSearch = "";
        this.currentPage = 0;
        this.element.querySelector('[data-role="search"]').value = "";
        this.element.querySelector('[data-role="favorites-only"]').checked = false;
        this.element.querySelector('[data-role="recursive-scan"]').checked = true;
        this.element.querySelector('[data-role="date-from"]').value = "";
        this.element.querySelector('[data-role="date-to"]').value = "";
        this.element.querySelector('[data-role="steps-min"]').value = "";
        this.element.querySelector('[data-role="steps-max"]').value = "";
        this.element.querySelector('[data-role="cfg-min"]').value = "";
        this.element.querySelector('[data-role="cfg-max"]').value = "";
        this.element.querySelector('[data-role="width-min"]').value = "";
        this.element.querySelector('[data-role="width-max"]').value = "";
        this.element.querySelector('[data-role="height-min"]').value = "";
        this.element.querySelector('[data-role="height-max"]').value = "";
        this.element.querySelector('[data-role="orientation"]').value = "any";
        this.element.querySelector('[data-role="tag-search"]').value = "";
        this.loadImages();
    }

    scheduleRefresh() {
        if (this.refreshTimer) {
            clearTimeout(this.refreshTimer);
        }
        this.refreshTimer = setTimeout(() => {
            this.currentPage = 0;
            this.loadImages();
        }, 350);
    }

    buildQuery() {
        const params = new URLSearchParams();
        params.set('limit', String(this.pageSize));
        params.set('offset', String(this.currentPage * this.pageSize));
        params.set('sort', this.sortBy);
        if (this.filters.search) params.set('search', this.filters.search);
        if (this.filters.favoritesOnly) params.set('favorites', '1');
        if (!this.filters.recursive) params.set('recursive', '0');
        if (this.filters.dateFrom) params.set('date_from', this.filters.dateFrom);
        if (this.filters.dateTo) params.set('date_to', this.filters.dateTo);
        if (this.filters.stepsMin) params.set('steps_min', this.filters.stepsMin);
        if (this.filters.stepsMax) params.set('steps_max', this.filters.stepsMax);
        if (this.filters.cfgMin) params.set('cfg_min', this.filters.cfgMin);
        if (this.filters.cfgMax) params.set('cfg_max', this.filters.cfgMax);
        if (this.filters.widthMin) params.set('width_min', this.filters.widthMin);
        if (this.filters.widthMax) params.set('width_max', this.filters.widthMax);
        if (this.filters.heightMin) params.set('height_min', this.filters.heightMin);
        if (this.filters.heightMax) params.set('height_max', this.filters.heightMax);
        if (this.filters.orientation && this.filters.orientation !== 'any') params.set('orientation', this.filters.orientation);
        if (this.filters.folders.size > 0) {
            params.set('folder', Array.from(this.filters.folders)[0]);
        }
        if (this.filters.models.size > 0) {
            params.set('models', Array.from(this.filters.models).join(','));
        }
        if (this.filters.loras.size > 0) {
            params.set('loras', Array.from(this.filters.loras).join(','));
        }
        if (this.filters.samplers.size > 0) {
            params.set('samplers', Array.from(this.filters.samplers).join(','));
        }
        if (this.filters.tags.size > 0) {
            params.set('tags', Array.from(this.filters.tags).join(','));
        }
        return params.toString();
    }

    beginLoad() {
        if (this.scanController) {
            this.scanController.abort();
        }
        this.scanController = new AbortController();
        return {
            generation: ++this.loadGeneration,
            signal: this.scanController.signal
        };
    }

    isCurrentLoad(context) {
        return Boolean(context) && context.generation === this.loadGeneration && !context.signal.aborted;
    }

    async fetchImages(quick = false, context = null) {
        const loadContext = context || this.beginLoad();
        try {
            const quickFlag = quick ? '&quick=1' : '';
            const response = await fetch(`/umiapp/images/scan?${this.buildQuery()}${quickFlag}`, {
                signal: loadContext.signal
            });
            let data = null;
            try {
                data = await response.json();
            } catch (parseError) {
                data = null;
            }
            if (!this.isCurrentLoad(loadContext)) return null;
            if (!response.ok || !data || data.success === false) {
                this.lastError = (data && data.error) || `Request failed (HTTP ${response.status})`;
                this.images = [];
                this.totalImages = 0;
                this.facets = { folders: [], models: [], loras: [], samplers: [], tags: [] };
                return this.images;
            }
            this.lastError = null;
            this.images = data.images || [];
            this.totalImages = data.total || 0;
            this.facets = data.facets || { folders: [], models: [], loras: [], samplers: [], tags: [] };
            this.images.forEach(img => this.imageMap.set(img.relative_path, img));
            return this.images;
        } catch (error) {
            if (error?.name === 'AbortError' || !this.isCurrentLoad(loadContext)) {
                return null;
            }
            console.error('[Umi Image Browser] Failed to fetch images:', error);
            this.lastError = (error && error.message) || String(error);
            this.images = [];
            this.totalImages = 0;
            this.facets = { folders: [], models: [], loras: [], samplers: [], tags: [] };
            return [];
        }
    }

    async loadImages(quick = false) {
        const context = this.beginLoad();
        const grid = this.element.querySelector('[data-role="grid"]');
        const title = this.element.querySelector('.umi-ib-title');
        if (title) {
            title.textContent = 'Image Browser';
            title.style.opacity = '1';
        }
        grid.innerHTML = '<div class="umi-ib-details-empty">Loading images...</div>';
        const result = await this.fetchImages(quick, context);
        if (result === null || !this.isCurrentLoad(context)) return;

        const totalPages = Math.ceil(this.totalImages / this.pageSize);
        if (totalPages > 0 && this.currentPage >= totalPages) {
            this.currentPage = totalPages - 1;
            const clampedResult = await this.fetchImages(quick, context);
            if (clampedResult === null || !this.isCurrentLoad(context)) return;
        }
        this.renderGrid();
        this.renderPagination();
        this.renderFacets();
        this.renderSelectionBar();
    }

    async loadImagesProgressive() {
        const context = this.beginLoad();
        const grid = this.element.querySelector('[data-role="grid"]');
        const title = this.element.querySelector('.umi-ib-title');
        const originalTitle = 'Image Browser';

        grid.innerHTML = '<div class="umi-ib-details-empty">Loading images...</div>';

        // Phase 1: Quick load with cached data
        const quickResult = await this.fetchImages(true, context);
        if (quickResult === null || !this.isCurrentLoad(context)) return;
        const quickPaths = this.images.map(img => img.relative_path);

        // Render immediately with cached data (if any)
        this.renderGrid();
        this.renderPagination();
        this.renderFacets();
        this.renderSelectionBar();

        // Phase 2: Background full load. The quick pass only guarantees dimensions;
        // the full pass repairs stale caches and fills prompt/model details.
        if (title) {
            title.textContent = `${originalTitle} (Loading metadata...)`;
            title.style.opacity = '0.7';
        }

        const fullResult = await this.fetchImages(false, context);
        if (fullResult === null || !this.isCurrentLoad(context)) return;

        // Smoothly update the grid (no flash, just update existing cards).
        // If the full pass failed, fall back to a full render so the error
        // state is shown instead of stale quick-pass cards.
        if (this.lastError) {
            this.renderGrid();
        } else if (
            quickPaths.length !== this.images.length ||
            quickPaths.some((path, index) => path !== this.images[index]?.relative_path)
        ) {
            this.renderGrid();
        } else {
            this.updateGridMetadata();
        }
        this.renderPagination();
        this.renderFacets();
        this.renderSelectionBar();

        if (title) {
            title.textContent = originalTitle;
            title.style.opacity = '1';
        }
    }

    updateGridMetadata() {
        // Update existing cards with new metadata without re-rendering entire grid
        // This prevents the flash by only updating the data that changed
        const grid = this.element.querySelector('[data-role="grid"]');

        this.images.forEach(img => {
            const card = grid.querySelector(`[data-id="${CSS.escape(img.relative_path)}"]`);
            if (!card) return;

            // Update metadata in imageMap
            this.imageMap.set(img.relative_path, img);

            const preview = card.querySelector('.umi-ib-thumb-image');
            const previewUrl = img.thumbnail_url || img.url;
            if (preview && preview.getAttribute('src') !== previewUrl && !preview.dataset.fallback) {
                preview.src = previewUrl;
            }

            // Update resolution if it changed
            const metaDiv = card.querySelector('.umi-ib-card-sub');
            if (metaDiv && img.metadata) {
                const resolution = `${img.metadata?.width || '?'}x${img.metadata?.height || '?'}`;
                const size = (img.size / 1024).toFixed(1);
                metaDiv.textContent = `${resolution} | ${size} KB`;
            }

            // Update prompt badge if metadata now available
            const thumb = card.querySelector('.umi-ib-thumb');
            const hasPrompt = Boolean(this.outputPrompt(img.metadata));
            const existingBadge = thumb.querySelector('.umi-ib-badge');

            if (hasPrompt && !existingBadge) {
                const badge = document.createElement('div');
                badge.className = 'umi-ib-badge';
                badge.textContent = 'Prompt';
                thumb.appendChild(badge);
            } else if (!hasPrompt && existingBadge) {
                existingBadge.remove();
            }
        });

        // Update details panel if image is selected
        if (this.selectedImage) {
            const updatedImage = this.imageMap.get(this.selectedImage.relative_path);
            if (updatedImage) {
                this.selectedImage = updatedImage;
                this.renderDetails();
            }
        }
    }

    renderGrid() {
        const grid = this.element.querySelector('[data-role="grid"]');
        if (this.lastError) {
            grid.innerHTML = `<div class="umi-ib-details-empty" style="color:var(--umi-danger);">Failed to load images: ${this.escapeHtml(this.lastError)}<br />Use Refresh to retry.</div>`;
            return;
        }

        if (!this.images.length) {
            grid.innerHTML = '<div class="umi-ib-details-empty">No images found</div>';
            return;
        }

        grid.innerHTML = this.images.map(img => this.createCardHTML(img)).join('');

        grid.querySelectorAll('.umi-ib-card').forEach(card => {
            const relPath = card.dataset.id;
            const img = this.imageMap.get(relPath);

            const preview = card.querySelector('.umi-ib-thumb-image');
            if (preview) preview.addEventListener('error', () => {
                // Older servers or unsupported images can still use /view.
                if (!preview.dataset.fallback) {
                    preview.dataset.fallback = '1';
                    preview.src = img.url;
                }
            });

            card.addEventListener('click', (e) => this.handleCardClick(img, e));
            card.addEventListener('keydown', (e) => {
                if (e.target !== card) return;
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    this.handleCardClick(img, e);
                }
            });
            card.addEventListener('contextmenu', (e) => {
                e.preventDefault();
                this.showContextMenu(img, e.clientX, e.clientY);
            });

            const favBtn = card.querySelector('.umi-ib-fav');
            if (favBtn) {
                favBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const isFavorite = !(img.annotations && img.annotations.favorite);
                    this.updateAnnotations(img.relative_path, { favorite: isFavorite });
                });
            }
        });
    }

    createCardHTML(img) {
        this.imageMap.set(img.relative_path, img);
        const hasPrompt = Boolean(this.outputPrompt(img.metadata));
        const resolution = `${img.metadata?.width || '?'}x${img.metadata?.height || '?'}`;
        const tags = (img.annotations?.tags || []).slice(0, 3);
        const extraTagCount = (img.annotations?.tags || []).length - tags.length;
        const tagHtml = tags.map(tag => {
            return `<span class="umi-ib-tag">#${this.escapeHtml(tag)}</span>`;
        }).join('') + (extraTagCount > 0 ? `<span class="umi-ib-tag">+${extraTagCount}</span>` : '');
        const favClass = img.annotations?.favorite ? 'umi-ib-fav' : 'umi-ib-fav umi-ib-fav--off';

        return `
            <div class="umi-ib-card ${this.selectedIds.has(img.relative_path) ? 'selected' : ''}" data-id="${this.escapeHtmlAttr(img.relative_path)}" role="button" tabindex="0" aria-label="Select ${this.escapeHtmlAttr(img.filename)}">
                <div class="umi-ib-thumb">
                    <img class="umi-ib-thumb-image" src="${this.escapeHtmlAttr(img.thumbnail_url || img.url)}" alt="" loading="lazy" decoding="async" style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover;pointer-events:none" />
                    <button class="${favClass}" aria-label="${img.annotations?.favorite ? 'Remove favorite' : 'Add favorite'}">Fav</button>
                    ${hasPrompt ? '<div class="umi-ib-badge">Prompt</div>' : ''}
                </div>
                <div class="umi-ib-card-meta">
                    <div class="umi-ib-card-name" title="${this.escapeHtml(img.filename)}">${this.escapeHtml(img.filename)}</div>
                    <div class="umi-ib-card-sub">${resolution} | ${(img.size / 1024).toFixed(1)} KB</div>
                    <div class="umi-ib-tags">${tagHtml}</div>
                </div>
            </div>
        `;
    }

    handleCardClick(img, event) {
        if (!img) return;
        const relPath = img.relative_path;

        if (event.ctrlKey || event.metaKey) {
            if (this.selectedIds.has(relPath)) {
                this.selectedIds.delete(relPath);
            } else {
                this.selectedIds.add(relPath);
            }
        } else if (event.shiftKey) {
            this.selectedIds.add(relPath);
        } else {
            this.selectedIds.clear();
            this.selectedIds.add(relPath);
        }

        this.selectedImage = img;
        this.renderGrid();
        this.renderDetails();
        this.renderSelectionBar();
    }

    renderPagination() {
        const pagination = this.element.querySelector('[data-role="pagination"]');
        const totalPages = Math.ceil(this.totalImages / this.pageSize);

        if (totalPages > 0 && this.currentPage >= totalPages) {
            this.currentPage = totalPages - 1;
        }

        if (totalPages <= 1) {
            pagination.innerHTML = '';
            return;
        }

        pagination.innerHTML = `
            <button class="umi-ib-btn" data-page="${this.currentPage - 1}" ${this.currentPage === 0 ? 'disabled' : ''}>Prev</button>
            <span class="umi-ib-chip">Page <input type="text" class="umi-ib-page-input" value="${this.currentPage + 1}" /> of ${totalPages} (${this.totalImages})</span>
            <button class="umi-ib-btn" data-page="${this.currentPage + 1}" ${this.currentPage >= totalPages - 1 ? 'disabled' : ''}>Next</button>
        `;

        pagination.querySelectorAll('button[data-page]:not([disabled])').forEach(btn => {
            btn.addEventListener('click', () => {
                this.currentPage = parseInt(btn.dataset.page, 10);
                this.loadImages();
            });
        });

        // Page jump input
        const pageInput = pagination.querySelector('.umi-ib-page-input');
        if (pageInput) {
            pageInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    let val = parseInt(e.target.value, 10);
                    if (!isNaN(val) && val > 0 && val <= totalPages) {
                        this.currentPage = val - 1;
                        this.loadImages();
                    } else {
                        e.target.value = this.currentPage + 1;
                    }
                }
            });
            pageInput.addEventListener('click', (e) => e.target.select());
        }
    }

    renderFacets() {
        ['folders', 'models', 'loras', 'samplers', 'tags'].forEach((facet) => {
            const container = this.element.querySelector(`[data-facet="${facet}"]`);
            if (!container) return;

            let list = this.facets[facet] || [];
            if (facet === 'tags' && this.tagSearch) {
                list = list.filter(item => item.name.toLowerCase().includes(this.tagSearch));
            }

            if (!list.length) {
                container.innerHTML = '<div class="umi-ib-details-empty">None</div>';
                return;
            }

            container.innerHTML = list.slice(0, 50).map(item => {
                const selected = this.filters[facet].has(item.name);
                return `
                    <div class="umi-ib-facet-item">
                        <label>
                            <input type="checkbox" data-facet-item="${facet}" data-value="${this.escapeHtml(item.name)}" ${selected ? 'checked' : ''} />
                            <span>${this.escapeHtml(item.name)}</span>
                        </label>
                        <span class="umi-ib-facet-count">${item.count}</span>
                    </div>
                `;
            }).join('');

            container.querySelectorAll('input[type="checkbox"]').forEach(input => {
                input.addEventListener('change', (e) => {
                    const value = e.target.dataset.value;
                    if (!value) return;
                    if (facet === 'folders' && e.target.checked) {
                        this.filters.folders.clear();
                    }
                    if (e.target.checked) {
                        this.filters[facet].add(value);
                    } else {
                        this.filters[facet].delete(value);
                    }
                    this.currentPage = 0;
                    this.loadImages();
                });
            });
        });
    }

    renderSelectionBar() {
        const bar = this.element.querySelector('[data-role="selection-bar"]');
        if (!bar) return;
        const count = this.selectedIds.size;
        if (!count) {
            bar.className = 'umi-ib-selection-bar';
            bar.innerHTML = '';
            return;
        }

        bar.className = 'umi-ib-selection-bar active';
        bar.innerHTML = `
            <span class="umi-ib-chip">${count} selected</span>
            <button class="umi-ib-btn" data-action="select-page">Select page</button>
            <button class="umi-ib-btn" data-action="clear-selection">Clear</button>
            <button class="umi-ib-btn" data-action="compare-selected">Compare</button>
            <button class="umi-ib-btn" data-action="favorite-selected">Favorite</button>
            <input class="umi-ib-input" data-role="bulk-tag-input" placeholder="Add tag to selected" style="max-width:180px; margin:0;" />
            <button class="umi-ib-btn" data-action="tag-selected">Tag</button>
            <span class="umi-ib-selection-spacer"></span>
        `;

        bar.querySelector('[data-action="select-page"]').addEventListener('click', () => {
            this.images.forEach(img => this.selectedIds.add(img.relative_path));
            this.renderGrid();
            this.renderSelectionBar();
        });
        bar.querySelector('[data-action="clear-selection"]').addEventListener('click', () => {
            this.selectedIds.clear();
            this.renderGrid();
            this.renderSelectionBar();
        });
        bar.querySelector('[data-action="compare-selected"]').addEventListener('click', () => this.showCompare());
        bar.querySelector('[data-action="favorite-selected"]').addEventListener('click', () => this.bulkUpdateSelected({ favorite: true }));
        bar.querySelector('[data-action="tag-selected"]').addEventListener('click', () => {
            const input = bar.querySelector('[data-role="bulk-tag-input"]');
            const tag = input.value.trim();
            if (!tag) return;
            this.bulkAddTag(tag);
            input.value = '';
        });
        bar.querySelector('[data-role="bulk-tag-input"]').addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                const tag = e.target.value.trim();
                if (!tag) return;
                this.bulkAddTag(tag);
                e.target.value = '';
            }
        });
    }

    setDetailsVisible(isVisible) {
        const details = this.element.querySelector('[data-role="details"]');
        const body = this.element.querySelector('.umi-ib-body');
        if (!details || !body) return;
        if (isVisible) {
            details.style.display = 'block';
            body.style.gridTemplateColumns = '260px minmax(0, 1fr) 360px';
        } else {
            details.style.display = 'none';
            body.style.gridTemplateColumns = '260px minmax(0, 1fr)';
        }
    }

    readableMetadataText(value) {
        if (typeof value !== 'string') return '';
        const text = value.trim();
        if (!text) return '';
        try {
            const parsed = JSON.parse(text);
            if (parsed && typeof parsed === 'object') return '';
        } catch (_) {
            // Plain prompt text is expected to fail JSON parsing.
        }
        return text;
    }

    outputPrompt(metadata = {}) {
        return metadata.umi_prompt || this.readableMetadataText(metadata.prompt);
    }

    outputNegative(metadata = {}) {
        return metadata.umi_negative || this.readableMetadataText(metadata.negative);
    }

    renderDetails() {
        const details = this.element.querySelector('[data-role="details"]');
        if (!this.selectedImage) {
            this.setDetailsVisible(false);
            details.innerHTML = '<div class="umi-ib-details-empty">Select an image to view details.</div>';
            return;
        }

        this.setDetailsVisible(true);
        const img = this.selectedImage;
        const metadata = img.metadata || {};
        const derived = img.derived || {};
        const annotations = img.annotations || {};

        const inputPrompt = metadata.umi_input_prompt || "";
        const inputNegative = metadata.umi_input_negative || "";
        const outputPrompt = this.outputPrompt(metadata);
        const outputNegative = this.outputNegative(metadata);

        const tagChips = (annotations.tags || []).map(tag => `
            <span class="umi-ib-tag" data-tag="${this.escapeHtmlAttr(tag)}">${this.escapeHtml(tag)}</span>
        `).join('');

        details.innerHTML = `
            <button class="umi-ib-btn umi-ib-details-back" data-action="close-details">Back to images</button>
            <div class="umi-ib-detail-section">
                <img class="umi-ib-detail-image" src="${this.escapeHtmlAttr(img.url)}" alt="${this.escapeHtmlAttr(img.filename)}" />
                <div class="umi-ib-detail-title">${this.escapeHtml(img.filename)}</div>
                <div class="umi-ib-detail-meta">
                    ${metadata.width || '?'}x${metadata.height || '?'} | ${(img.size / 1024).toFixed(1)} KB<br />
                    ${new Date(img.mtime * 1000).toLocaleString()}
                </div>
                <div class="umi-ib-detail-actions">
                    <button class="umi-ib-btn" data-action="toggle-favorite">${annotations.favorite ? 'Unfavorite' : 'Favorite'}</button>
                    <button class="umi-ib-btn" data-action="open-image">Open</button>
                </div>
            </div>

            <div class="umi-ib-detail-section">
                <div class="umi-ib-detail-label">Tags</div>
                <div>${tagChips || '<span class="umi-ib-details-empty">No tags</span>'}</div>
                <div class="umi-ib-detail-actions">
                    <input class="umi-ib-input" data-role="tag-input" placeholder="Add tag" />
                    <button class="umi-ib-btn" data-action="add-tag">Add</button>
                </div>
            </div>

            <div class="umi-ib-detail-section">
                <div class="umi-ib-detail-label">Metadata</div>
                <div class="umi-ib-detail-box">Model: ${this.escapeHtml((derived.models || [])[0] || 'Unknown')}
Sampler: ${this.escapeHtml(derived.sampler || 'Unknown')}
Steps: ${derived.steps ?? 'Unknown'}
CFG: ${derived.cfg ?? 'Unknown'}
Seed: ${derived.seed ?? 'Unknown'}
LoRAs: ${(derived.loras || []).length ? this.escapeHtml((derived.loras || []).join(', ')) : 'None'}</div>
            </div>

            ${this.renderPromptSection('Input Prompt', inputPrompt, inputNegative)}
            ${this.renderPromptSection('Output Prompt', outputPrompt, outputNegative)}
        `;

        const openBtn = details.querySelector('[data-action="open-image"]');
        if (openBtn) {
            openBtn.addEventListener('click', () => window.open(img.url, '_blank'));
        }

        details.querySelector('[data-action="close-details"]')?.addEventListener('click', () => {
            this.selectedImage = null;
            this.renderDetails();
        });

        const favBtn = details.querySelector('[data-action="toggle-favorite"]');
        if (favBtn) {
            favBtn.addEventListener('click', () => {
                this.updateAnnotations(img.relative_path, { favorite: !annotations.favorite });
            });
        }

        const addTagBtn = details.querySelector('[data-action="add-tag"]');
        if (addTagBtn) {
            addTagBtn.addEventListener('click', () => this.addTagFromDetails());
        }

        details.querySelectorAll('[data-tag]').forEach(tagEl => {
            tagEl.addEventListener('click', () => {
                const tagValue = tagEl.dataset.tag;
                if (!tagValue) return;
                const nextTags = (annotations.tags || []).filter(tag => tag !== tagValue);
                this.updateAnnotations(img.relative_path, { tags: nextTags });
            });
        });

        details.querySelectorAll('[data-role="copy-to-node"]').forEach(btn => {
            btn.addEventListener('click', () => {
                const prompt = btn.dataset.prompt || '';
                const negative = btn.dataset.negative || '';
                this.copyToUmiNode(prompt, negative);
            });
        });

        details.querySelectorAll('[data-role="copy-to-clipboard"]').forEach(btn => {
            btn.addEventListener('click', async () => {
                const text = btn.dataset.text || '';
                await this.copyText(text, 'Copied to clipboard');
            });
        });
    }

    renderPromptSection(title, prompt, negative) {
        if (!prompt && !negative) {
            return '';
        }

        const promptSafe = this.escapeHtml(prompt || '');
        const negativeSafe = this.escapeHtml(negative || '');
        return `
            <div class="umi-ib-detail-section">
                <div class="umi-ib-detail-label">${title}</div>
                ${prompt ? `<div class="umi-ib-detail-box">${promptSafe}</div>` : ''}
                <div class="umi-ib-detail-actions">
                    <button class="umi-ib-btn" data-role="copy-to-node" data-prompt="${this.escapeHtmlAttr(prompt || '')}" data-negative="${this.escapeHtmlAttr(negative || '')}">Copy to Umi</button>
                    <button class="umi-ib-btn" data-role="copy-to-clipboard" data-text="${this.escapeHtmlAttr(prompt || '')}">Copy prompt</button>
                </div>
                ${negative ? `<div class="umi-ib-detail-label" style="margin-top:8px;">Negative</div><div class="umi-ib-detail-box">${negativeSafe}</div>` : ''}
            </div>
        `;
    }

    addTagFromDetails() {
        const details = this.element.querySelector('[data-role="details"]');
        const input = details.querySelector('[data-role="tag-input"]');
        if (!input || !this.selectedImage) return;
        const value = input.value.trim();
        if (!value) return;
        const currentTags = new Set(this.selectedImage.annotations?.tags || []);
        currentTags.add(value);
        input.value = '';
        this.updateAnnotations(this.selectedImage.relative_path, { tags: Array.from(currentTags) });
    }

    showCompare() {
        if (!this.compareOverlay) return;
        const selected = Array.from(this.selectedIds).slice(0, 2).map(id => this.imageMap.get(id)).filter(Boolean);
        if (selected.length < 2) {
            this.showNotification('Select two images to compare');
            return;
        }

        this.compareOverlay.innerHTML = `
            <div class="umi-ib-compare-header">
                <div class="umi-ib-title">Compare</div>
                <button class="umi-ib-btn" data-action="close-compare">Close</button>
            </div>
            <div class="umi-ib-compare-body">
                ${selected.map(img => `
                    <div class="umi-ib-compare-card">
                        <img src="${img.url}" />
                        <div class="umi-ib-detail-title">${this.escapeHtml(img.filename)}</div>
                        <div class="umi-ib-detail-meta">${img.metadata?.width || '?'}x${img.metadata?.height || '?'} | ${(img.size / 1024).toFixed(1)} KB</div>
                        <div class="umi-ib-detail-box">${this.escapeHtml(this.outputPrompt(img.metadata).slice(0, 800))}</div>
                    </div>
                `).join('')}
            </div>
        `;
        this.compareOverlay.style.display = 'flex';

        const closeBtn = this.compareOverlay.querySelector('[data-action="close-compare"]');
        closeBtn.addEventListener('click', () => {
            this.compareOverlay.style.display = 'none';
        });
    }

    showContextMenu(img, x, y) {
        if (!this.contextMenu || !img) return;
        const prompt = this.outputPrompt(img.metadata);
        const negative = this.outputNegative(img.metadata);
        const seed = img.derived?.seed ?? '';
        const model = (img.derived?.models || [])[0] || '';

        this.contextMenu.innerHTML = `
            <button data-action="copy-prompt">Copy prompt</button>
            <button data-action="copy-negative">Copy negative</button>
            <button data-action="copy-seed">Copy seed</button>
            <button data-action="copy-model">Copy model</button>
            <button data-action="open-image">Open image</button>
        `;

        this.contextMenu.style.left = `${x}px`;
        this.contextMenu.style.top = `${y}px`;
        this.contextMenu.style.display = 'block';

        this.contextMenu.querySelector('[data-action="copy-prompt"]').addEventListener('click', async () => {
            await this.copyText(prompt, 'Prompt copied');
            this.contextMenu.style.display = 'none';
        });
        this.contextMenu.querySelector('[data-action="copy-negative"]').addEventListener('click', async () => {
            await this.copyText(negative, 'Negative copied');
            this.contextMenu.style.display = 'none';
        });
        this.contextMenu.querySelector('[data-action="copy-seed"]').addEventListener('click', async () => {
            await this.copyText(String(seed || ''), 'Seed copied');
            this.contextMenu.style.display = 'none';
        });
        this.contextMenu.querySelector('[data-action="copy-model"]').addEventListener('click', async () => {
            await this.copyText(String(model || ''), 'Model copied');
            this.contextMenu.style.display = 'none';
        });
        this.contextMenu.querySelector('[data-action="open-image"]').addEventListener('click', () => {
            window.open(img.url, '_blank');
            this.contextMenu.style.display = 'none';
        });
    }

    async updateAnnotations(relPath, updates, render = true) {
        try {
            const response = await fetch('/umiapp/images/annotations/update', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ relative_path: relPath, ...updates })
            });
            let data = null;
            try {
                data = await response.json();
            } catch (_) {
                data = null;
            }
            if (!response.ok || !data || data.success === false || !data.item) {
                throw new Error(data?.error || `Update failed (HTTP ${response.status})`);
            }
            if (data.item) {
                const target = this.images.find(img => img.relative_path === relPath);
                if (target) {
                    target.annotations = data.item;
                }
                const known = this.imageMap.get(relPath);
                if (known) {
                    known.annotations = data.item;
                }
                if (this.selectedImage && this.selectedImage.relative_path === relPath) {
                    this.selectedImage.annotations = data.item;
                }
                if (render) this.renderAnnotationChanges();
            }
            return true;
        } catch (error) {
            console.error('[Umi Image Browser] Failed to update annotations:', error);
            this.showNotification(`Update failed: ${error?.message || error}`, true);
            return false;
        }
    }

    async runAnnotationBatch(items, update) {
        let next = 0;
        const results = new Array(items.length);
        // Keep large selections from flooding the server with requests.
        await Promise.all(Array.from({ length: Math.min(4, items.length) }, async () => {
            while (next < items.length) {
                const index = next++;
                results[index] = await update(items[index]);
            }
        }));
        return results;
    }

    async bulkUpdateSelected(updates) {
        const selected = Array.from(this.selectedIds);
        if (!selected.length) return;
        const results = await this.runAnnotationBatch(selected, relPath => this.updateAnnotations(relPath, updates, false));
        this.renderAnnotationChanges();
        const updated = results.filter(Boolean).length;
        if (updated) this.showNotification(`Updated ${updated} image${updated === 1 ? '' : 's'}`);
    }

    async bulkAddTag(tag) {
        const selected = Array.from(this.selectedIds)
            .map(id => this.imageMap.get(id))
            .filter(Boolean);
        if (!selected.length) return;

        const results = await this.runAnnotationBatch(selected, img => {
            const tags = new Set(img.annotations?.tags || []);
            tags.add(tag);
            return this.updateAnnotations(img.relative_path, { tags: Array.from(tags) }, false);
        });
        this.renderAnnotationChanges();
        const updated = results.filter(Boolean).length;
        if (updated) this.showNotification(`Tagged ${updated} image${updated === 1 ? '' : 's'}`);
    }

    renderAnnotationChanges() {
        if (!this.element || this.element.style.display === 'none') return;
        this.renderGrid();
        this.renderDetails();
        this.renderFacets();
        this.renderSelectionBar();
    }

    copyToUmiNode(prompt, negative) {
        const activeNode = this.findActiveUmiNode();

        if (activeNode) {
            const promptWidget = activeNode.widgets.find(w => w.name === 'text');
            if (promptWidget && prompt) {
                promptWidget.value = prompt;
                if (promptWidget.callback) {
                    promptWidget.callback(prompt);
                }
                if (promptWidget.inputEl) {
                    promptWidget.inputEl.dispatchEvent(new Event('input', { bubbles: true }));
                }
            }

            if (negative) {
                const negWidget = activeNode.widgets.find(w => w.name === 'input_negative');
                if (negWidget) {
                    negWidget.value = negative;
                    if (negWidget.callback) {
                        negWidget.callback(negative);
                    }
                    if (negWidget.inputEl) {
                        negWidget.inputEl.dispatchEvent(new Event('input', { bubbles: true }));
                    }
                }
            }

            app.graph.setDirtyCanvas(true, true);
            this.showNotification(`Copied to ${activeNode.type}`);
        } else {
            let text = prompt || '';
            if (negative) {
                text += `\n\nNegative: ${negative}`;
            }
            this.copyText(text, 'Copied to clipboard (no active Umi node)');
        }
    }

    async copyText(text, successMessage = 'Copied to clipboard') {
        try {
            await navigator.clipboard.writeText(String(text || ''));
            this.showNotification(successMessage);
            return true;
        } catch (error) {
            console.error('[Umi Image Browser] Clipboard write failed:', error);
            this.showNotification('Clipboard access failed', true);
            return false;
        }
    }

    findActiveUmiNode() {
        const canvas = app.canvas;
        if (!canvas) return null;

        const selectedNodes = canvas.selected_nodes;
        if (selectedNodes) {
            for (const nodeId in selectedNodes) {
                const node = app.graph.getNodeById(parseInt(nodeId, 10));
                if (node && (node.type === 'UmiAIWildcardNode' || node.type === 'UmiAIWildcardNodeLite')) {
                    return node;
                }
            }
        }

        for (const node of app.graph._nodes) {
            if (node.type === 'UmiAIWildcardNode' || node.type === 'UmiAIWildcardNodeLite') {
                return node;
            }
        }

        return null;
    }

    showNotification(message, isError = false) {
        const notification = document.createElement('div');
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: ${isError ? 'var(--umi-danger)' : 'var(--umi-ok-soft)'};
            color: white;
            padding: 10px 16px;
            border-radius: 6px;
            z-index: 10003;
            font-size: 12px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.4);
        `;
        notification.textContent = message;
        document.body.appendChild(notification);
        setTimeout(() => notification.remove(), 2000);
    }

    escapeHtml(text) {
        if (!text) return '';
        return String(text)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    escapeHtmlAttr(text) {
        if (!text) return '';
        return String(text)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;')
            .replace(/\n/g, '&#10;');
    }

    async show() {
        this.previousFocus = document.activeElement;
        if (!this.element) {
            this.createPanel();
        }

        this.element.style.display = 'flex';
        this.currentPage = 0;
        const search = this.element.querySelector('[data-role="search"]');
        if (search) search.focus();
        await this.loadImagesProgressive();
    }

    hide() {
        clearTimeout(this.refreshTimer);
        this.refreshTimer = null;
        if (this.element) {
            if (this.contextMenu) this.contextMenu.style.display = 'none';
            if (this.compareOverlay) this.compareOverlay.style.display = 'none';
            if (this.scanController) this.scanController.abort();
            this.loadGeneration += 1;
            this.element.style.display = 'none';
            const title = this.element.querySelector('.umi-ib-title');
            if (title) {
                title.textContent = 'Image Browser';
                title.style.opacity = '1';
            }
            const sidebar = this.element.querySelector('.umi-ib-sidebar');
            const toggle = this.element.querySelector('[data-action="toggle-filters"]');
            sidebar?.classList.remove('filters-open');
            toggle?.setAttribute('aria-expanded', 'false');
            this.selectedImage = null;
            this.selectedIds.clear();
            this.imageMap.clear();
            if (this.previousFocus && typeof this.previousFocus.focus === 'function') {
                this.previousFocus.focus();
            }
        }
    }
}

const imageBrowser = new ImageBrowser();
window.umiImageBrowser = imageBrowser;
app.registerExtension({
    name: 'Umi.ImageBrowser',

    async setup() {
        const menu = document.querySelector('.comfy-menu');
        if (menu) {
            const button = document.createElement('button');
            button.textContent = 'Image Browser';
            button.style.cssText = 'margin-left: 4px;';
            button.onclick = () => imageBrowser.show();
            menu.appendChild(button);
        }

        document.addEventListener('keydown', (e) => {
            if (e.ctrlKey && e.key === 'i') {
                e.preventDefault();
                imageBrowser.show();
            }
        });
    }
});
