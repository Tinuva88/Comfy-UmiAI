import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

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
        this.facets = { models: [], loras: [], samplers: [], tags: [] };
        this.refreshTimer = null;
        this.filters = {
            search: "",
            favoritesOnly: false,
            dateFrom: "",
            dateTo: "",
            stepsMin: "",
            stepsMax: "",
            cfgMin: "",
            cfgMax: "",
            recursive: true,
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
            background: #0f1115;
            z-index: 10000;
            display: none;
            color: #d7dae0;
            font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
        `;

        panel.innerHTML = this.getStyles() + this.getLayout();

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
                    border-bottom: 1px solid #20242c;
                    background: linear-gradient(135deg, #1d2230 0%, #151a24 100%);
                }
                .umi-ib-title {
                    font-size: 18px;
                    font-weight: 600;
                    color: #8fc6ff;
                }
                .umi-ib-header-actions {
                    display: flex;
                    gap: 8px;
                    align-items: center;
                }
                .umi-ib-btn {
                    background: #2a303b;
                    color: #d7dae0;
                    border: 1px solid #3b4250;
                    padding: 6px 10px;
                    border-radius: 6px;
                    cursor: pointer;
                    font-size: 12px;
                }
                .umi-ib-btn:hover {
                    border-color: #5b6b85;
                }
                .umi-ib-select {
                    background: #1c212b;
                    color: #d7dae0;
                    border: 1px solid #3b4250;
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
                    border-right: 1px solid #20242c;
                    padding: 14px;
                    overflow-y: auto;
                    background: #12161f;
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
                    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
                    gap: 12px;
                    padding: 14px;
                    overflow-y: auto;
                    height: 100%;
                    min-height: 0;
                }
                .umi-ib-details {
                    border-left: 1px solid #20242c;
                    padding: 14px;
                    overflow-y: auto;
                    background: #12161f;
                    min-width: 0;
                }
                .umi-ib-section {
                    margin-bottom: 16px;
                }
                .umi-ib-section-title {
                    font-size: 12px;
                    letter-spacing: 0.08em;
                    text-transform: uppercase;
                    color: #8b93a6;
                    margin-bottom: 8px;
                }
                .umi-ib-input {
                    width: 100%;
                    padding: 6px 8px;
                    background: #1c212b;
                    border: 1px solid #313847;
                    border-radius: 6px;
                    color: #d7dae0;
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
                    color: #c1c7d4;
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
                    color: #8b93a6;
                }
                .umi-ib-card {
                    background: #1a1f2b;
                    border: 1px solid #2a303b;
                    border-radius: 8px;
                    overflow: hidden;
                    cursor: pointer;
                    transition: transform 0.1s ease, border-color 0.1s ease;
                    position: relative;
                }
                .umi-ib-card:hover {
                    border-color: #4c6b9a;
                    transform: translateY(-2px);
                }
                .umi-ib-card.selected {
                    border-color: #8fc6ff;
                    box-shadow: 0 0 0 1px #8fc6ff inset;
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
                    color: #c7cbd6;
                    white-space: nowrap;
                    overflow: hidden;
                    text-overflow: ellipsis;
                }
                .umi-ib-card-sub {
                    font-size: 10px;
                    color: #7b8499;
                    margin-top: 4px;
                }
                .umi-ib-badge {
                    position: absolute;
                    top: 6px;
                    right: 6px;
                    background: #2f7d4b;
                    color: #fff;
                    padding: 2px 6px;
                    font-size: 9px;
                    border-radius: 4px;
                }
                .umi-ib-fav {
                    position: absolute;
                    top: 6px;
                    left: 6px;
                    background: rgba(0,0,0,0.6);
                    color: #f5d76e;
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
                    background: #2a303b;
                    color: #c1c7d4;
                    font-size: 9px;
                    padding: 2px 6px;
                    border-radius: 4px;
                }
                .umi-ib-tag[data-tag] {
                    cursor: pointer;
                }
                .umi-ib-fav--off {
                    opacity: 0.35;
                    color: #c7cbd6;
                }
                .umi-ib-pagination {
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    gap: 8px;
                    padding: 10px;
                    border-top: 1px solid #20242c;
                    background: #10141d;
                }
                .umi-ib-details-empty {
                    color: #7b8499;
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
                    color: #8fc6ff;
                    margin-bottom: 6px;
                }
                .umi-ib-detail-meta {
                    font-size: 11px;
                    color: #9aa3b2;
                    margin-bottom: 10px;
                }
                .umi-ib-detail-section {
                    margin-bottom: 12px;
                }
                .umi-ib-detail-label {
                    font-size: 11px;
                    color: #8b93a6;
                    margin-bottom: 4px;
                }
                .umi-ib-detail-box {
                    background: #1c212b;
                    border: 1px solid #2a303b;
                    border-radius: 6px;
                    padding: 8px;
                    font-size: 12px;
                    color: #d7dae0;
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
                    background: #1c212b;
                    border: 1px solid #2a303b;
                    border-radius: 6px;
                    padding: 6px 0;
                    z-index: 10002;
                    min-width: 180px;
                }
                .umi-ib-context-menu button {
                    width: 100%;
                    background: none;
                    border: none;
                    color: #d7dae0;
                    padding: 6px 12px;
                    text-align: left;
                    font-size: 12px;
                    cursor: pointer;
                }
                .umi-ib-context-menu button:hover {
                    background: #2a303b;
                }
                .umi-ib-compare {
                    position: fixed;
                    top: 60px;
                    left: 60px;
                    right: 60px;
                    bottom: 60px;
                    background: #0f1115;
                    border: 1px solid #2a303b;
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
                    border-bottom: 1px solid #20242c;
                }
                .umi-ib-compare-body {
                    display: grid;
                    grid-template-columns: 1fr 1fr;
                    gap: 12px;
                    padding: 12px;
                    overflow: auto;
                }
                .umi-ib-compare-card {
                    background: #151a24;
                    border: 1px solid #2a303b;
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
                    background: #1c212b;
                    border: 1px solid #2a303b;
                    padding: 4px 8px;
                    border-radius: 6px;
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
                        <button class="umi-ib-btn" data-action="refresh">Refresh</button>
                        <select class="umi-ib-select" data-role="sort">
                            <option value="newest">Newest</option>
                            <option value="oldest">Oldest</option>
                            <option value="name">Name</option>
                        </select>
                        <select class="umi-ib-select" data-role="page-size">
                            <option value="15">15</option>
                            <option value="30" selected>30</option>
                            <option value="60">60</option>
                        </select>
                        <button class="umi-ib-btn" data-action="compare" disabled>Compare</button>
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

        const tagSearch = this.element.querySelector('[data-role="tag-search"]');
        tagSearch.addEventListener('input', (e) => {
            this.tagSearch = e.target.value.toLowerCase();
            this.renderFacets();
        });

        const clearFilters = this.element.querySelector('[data-action="clear-filters"]');
        clearFilters.addEventListener('click', () => {
            this.resetFilters();
        });

        const compareBtn = this.element.querySelector('[data-action="compare"]');
        compareBtn.addEventListener('click', () => this.showCompare());

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.element.style.display === 'flex') {
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
            recursive: true,
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

    async fetchImages(quick = false) {
        try {
            const quickFlag = quick ? '&quick=1' : '';
            const response = await fetch(`/umiapp/images/scan?${this.buildQuery()}${quickFlag}`);
            const data = await response.json();
            this.images = data.images || [];
            this.totalImages = data.total || 0;
            this.facets = data.facets || { models: [], loras: [], samplers: [], tags: [] };
            return this.images;
        } catch (error) {
            console.error('[Umi Image Browser] Failed to fetch images:', error);
            return [];
        }
    }

    async loadImages(quick = false) {
        const grid = this.element.querySelector('[data-role="grid"]');
        grid.innerHTML = '<div class="umi-ib-details-empty">Loading images...</div>';
        await this.fetchImages(quick);
        this.renderGrid();
        this.renderPagination();
        this.renderFacets();
        this.updateCompareButton();
    }

    renderGrid() {
        const grid = this.element.querySelector('[data-role="grid"]');
        this.imageMap.clear();

        if (!this.images.length) {
            grid.innerHTML = '<div class="umi-ib-details-empty">No images found</div>';
            return;
        }

        grid.innerHTML = this.images.map(img => this.createCardHTML(img)).join('');

        grid.querySelectorAll('.umi-ib-card').forEach(card => {
            const relPath = card.dataset.id;
            const img = this.imageMap.get(relPath);

            card.addEventListener('click', (e) => this.handleCardClick(img, e));
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
        const hasPrompt = img.metadata && (img.metadata.prompt || img.metadata.umi_prompt);
        const resolution = `${img.metadata?.width || '?'}x${img.metadata?.height || '?'}`;
        const tags = (img.annotations?.tags || []).slice(0, 3);
        const extraTagCount = (img.annotations?.tags || []).length - tags.length;
        const tagHtml = tags.map(tag => {
            return `<span class="umi-ib-tag">#${this.escapeHtml(tag)}</span>`;
        }).join('') + (extraTagCount > 0 ? `<span class="umi-ib-tag">+${extraTagCount}</span>` : '');
        const favClass = img.annotations?.favorite ? 'umi-ib-fav' : 'umi-ib-fav umi-ib-fav--off';

        return `
            <div class="umi-ib-card ${this.selectedIds.has(img.relative_path) ? 'selected' : ''}" data-id="${img.relative_path}">
                <div class="umi-ib-thumb" style="background-image:url('${img.url}')">
                    <button class="${favClass}">Fav</button>
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
        this.updateCompareButton();
    }

    renderPagination() {
        const pagination = this.element.querySelector('[data-role="pagination"]');
        const totalPages = Math.ceil(this.totalImages / this.pageSize);

        if (totalPages <= 1) {
            pagination.innerHTML = '';
            return;
        }

        pagination.innerHTML = `
            <button class="umi-ib-btn" data-page="${this.currentPage - 1}" ${this.currentPage === 0 ? 'disabled' : ''}>Prev</button>
            <span class="umi-ib-chip">Page ${this.currentPage + 1} of ${totalPages} (${this.totalImages})</span>
            <button class="umi-ib-btn" data-page="${this.currentPage + 1}" ${this.currentPage >= totalPages - 1 ? 'disabled' : ''}>Next</button>
        `;

        pagination.querySelectorAll('button[data-page]:not([disabled])').forEach(btn => {
            btn.addEventListener('click', () => {
                this.currentPage = parseInt(btn.dataset.page, 10);
                this.loadImages();
            });
        });
    }

    renderFacets() {
        ['models', 'loras', 'samplers', 'tags'].forEach((facet) => {
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
        const outputPrompt = metadata.umi_prompt || metadata.prompt || "";
        const outputNegative = metadata.umi_negative || metadata.negative || "";

        const tagChips = (annotations.tags || []).map(tag => `
            <span class="umi-ib-tag" data-tag="${this.escapeHtmlAttr(tag)}">${this.escapeHtml(tag)}</span>
        `).join('');

        details.innerHTML = `
            <div class="umi-ib-detail-section">
                <img class="umi-ib-detail-image" src="${img.url}" />
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
            btn.addEventListener('click', () => {
                const text = btn.dataset.text || '';
                navigator.clipboard.writeText(text || '');
                this.showNotification('Copied to clipboard');
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

    updateCompareButton() {
        const compareBtn = this.element.querySelector('[data-action="compare"]');
        if (!compareBtn) return;
        const size = this.selectedIds.size;
        compareBtn.disabled = size < 2;
        compareBtn.textContent = size >= 2 ? `Compare (${size})` : 'Compare';
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
                        <div class="umi-ib-detail-box">${this.escapeHtml((img.metadata?.umi_prompt || img.metadata?.prompt || '').slice(0, 800))}</div>
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
        const prompt = img.metadata?.umi_prompt || img.metadata?.prompt || '';
        const negative = img.metadata?.umi_negative || img.metadata?.negative || '';
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

        this.contextMenu.querySelector('[data-action="copy-prompt"]').addEventListener('click', () => {
            navigator.clipboard.writeText(prompt || '');
            this.contextMenu.style.display = 'none';
            this.showNotification('Prompt copied');
        });
        this.contextMenu.querySelector('[data-action="copy-negative"]').addEventListener('click', () => {
            navigator.clipboard.writeText(negative || '');
            this.contextMenu.style.display = 'none';
            this.showNotification('Negative copied');
        });
        this.contextMenu.querySelector('[data-action="copy-seed"]').addEventListener('click', () => {
            navigator.clipboard.writeText(String(seed || ''));
            this.contextMenu.style.display = 'none';
            this.showNotification('Seed copied');
        });
        this.contextMenu.querySelector('[data-action="copy-model"]').addEventListener('click', () => {
            navigator.clipboard.writeText(String(model || ''));
            this.contextMenu.style.display = 'none';
            this.showNotification('Model copied');
        });
        this.contextMenu.querySelector('[data-action="open-image"]').addEventListener('click', () => {
            window.open(img.url, '_blank');
            this.contextMenu.style.display = 'none';
        });
    }

    async updateAnnotations(relPath, updates) {
        try {
            const response = await fetch('/umiapp/images/annotations/update', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ relative_path: relPath, ...updates })
            });
            const data = await response.json();
            if (data.item) {
                const target = this.images.find(img => img.relative_path === relPath);
                if (target) {
                    target.annotations = data.item;
                }
                if (this.selectedImage && this.selectedImage.relative_path === relPath) {
                    this.selectedImage.annotations = data.item;
                }
                this.renderGrid();
                this.renderDetails();
                this.renderFacets();
            }
        } catch (error) {
            console.error('[Umi Image Browser] Failed to update annotations:', error);
        }
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
            navigator.clipboard.writeText(text);
            this.showNotification('Copied to clipboard (no active Umi node)');
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

    showNotification(message) {
        const notification = document.createElement('div');
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: #2f7d4b;
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
        if (!this.element) {
            this.createPanel();
        }

        this.element.style.display = 'block';
        this.currentPage = 0;
        await this.loadImages(true);
        setTimeout(() => {
            this.loadImages(false);
        }, 400);
    }

    hide() {
        if (this.element) {
            this.element.style.display = 'none';
            this.selectedImage = null;
            this.selectedIds.clear();
        }
    }
}

const imageBrowser = new ImageBrowser();

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
