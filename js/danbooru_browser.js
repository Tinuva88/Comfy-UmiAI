import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { escapeHtml, showUmiNotification, copyText } from "./umi_frontend_utils.js";
import { ensureUmiTheme } from "./umi_theme.js";

const CATEGORY_LABELS = {
  artist: "Artist",
  copyright: "Copyright",
  character: "Character",
  general: "General",
  meta: "Meta",
};

class DanbooruBrowserPanel {
  constructor() {
    this.element = null;
    this.posts = [];
    this.selectedPost = null;
    this.selectedTags = new Set();
    this.wildcards = [];
    this.page = 1;
    this.lastQuery = "";
    this.lastCount = 0;
    this.suggestTimer = null;
    this.suggestions = [];
  }

  createPanel() {
    const panel = document.createElement("div");
    panel.className = "umi-danbooru-browser";
    panel.style.cssText = `
      position: fixed; inset: 0; width: 100vw; height: 100vh; display: none;
      background: var(--umi-sunken); color: var(--umi-ink); z-index: 10000;
      font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
    `;
    ensureUmiTheme();
    panel.innerHTML = `
      <style>
        .umi-db-root { height: 100%; min-height: 0; display: grid; grid-template-rows: 58px minmax(0, 1fr); }
        .umi-db-header { display: flex; align-items: center; gap: 10px; padding: 10px 16px; background: var(--umi-ground); border-bottom: 1px solid var(--umi-rule); box-sizing: border-box; }
        .umi-db-title { font-size: 17px; font-weight: 700; color: var(--umi-accent); margin-right: 8px; white-space: nowrap; }
        .umi-db-search-wrap { position: relative; flex: 1; min-width: 300px; }
        .umi-db-input, .umi-db-select, .umi-db-textarea { background: var(--umi-sunken); color: var(--umi-ink-strong); border: 1px solid var(--umi-rule-strong); border-radius: 6px; padding: 7px 9px; font-size: 12px; }
        .umi-db-input { min-width: 300px; flex: 1; }
        .umi-db-search-wrap .umi-db-input { width: 100%; box-sizing: border-box; }
        .umi-db-suggestions { position: absolute; left: 0; right: 0; top: calc(100% + 4px); max-height: 280px; overflow: auto; background: var(--umi-sunken); border: 1px solid var(--umi-rule-strong); border-radius: 6px; box-shadow: 0 12px 28px rgba(0,0,0,.4); display: none; z-index: 10001; }
        .umi-db-suggestion { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px; width: 100%; padding: 7px 9px; border: 0; border-bottom: 1px solid var(--umi-rule); background: transparent; color: var(--umi-ink); cursor: pointer; text-align: left; font-size: 12px; }
        .umi-db-suggestion:hover { background: var(--umi-surface); color: var(--umi-ink-strong); }
        .umi-db-suggestion-tag { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .umi-db-suggestion-count { color: var(--umi-ink-2); font-size: 11px; }
        .umi-db-select { height: 32px; }
        .umi-db-btn { background: var(--umi-surface-alt); color: var(--umi-ink); border: 1px solid var(--umi-rule-strong); border-radius: 6px; padding: 7px 10px; cursor: pointer; font-size: 12px; }
        .umi-db-btn:hover { border-color: var(--umi-accent); background: var(--umi-surface-hover); }
        .umi-db-btn:disabled { opacity: .45; cursor: not-allowed; border-color: var(--umi-rule-strong); background: var(--umi-surface); }
        .umi-db-btn:disabled:hover { border-color: var(--umi-rule-strong); background: var(--umi-surface); }
        .umi-db-btn-primary { background: var(--umi-accent-soft); border-color: var(--umi-accent); }
        .umi-db-btn-danger { color: var(--umi-danger); border-color: var(--umi-danger-soft); }
        .umi-db-body { display: grid; grid-template-columns: minmax(420px, 1fr) 440px; min-height: 0; overflow: hidden; }
        .umi-db-grid-wrap { display: grid; grid-template-rows: minmax(0, 1fr) 46px; min-width: 0; min-height: 0; }
        .umi-db-grid { min-height: 0; overflow-y: auto; overflow-x: hidden; padding: 14px; display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); align-content: start; gap: 12px; }
        .umi-db-card { background: var(--umi-ground); border: 1px solid var(--umi-rule); border-radius: 7px; overflow: hidden; cursor: pointer; min-width: 0; }
        .umi-db-card:hover, .umi-db-card.active { border-color: var(--umi-accent); }
        .umi-db-thumb { width: 100%; aspect-ratio: 1 / 1; object-fit: contain; background: var(--umi-sunken); display: block; }
        .umi-db-card-meta { padding: 7px 8px; font-size: 11px; color: var(--umi-ink); display: flex; justify-content: space-between; gap: 8px; }
        .umi-db-footer { display: flex; justify-content: center; align-items: center; gap: 8px; border-top: 1px solid var(--umi-rule); background: var(--umi-sunken); }
        .umi-db-detail { border-left: 1px solid var(--umi-rule); background: var(--umi-sunken); min-height: 0; overflow: auto; padding: 14px; box-sizing: border-box; }
        .umi-db-preview { width: 100%; max-height: 300px; object-fit: contain; background: var(--umi-sunken); border: 1px solid var(--umi-rule); border-radius: 7px; }
        .umi-db-section { margin-top: 12px; }
        .umi-db-section-title { font-size: 11px; color: var(--umi-accent); text-transform: uppercase; letter-spacing: .06em; margin-bottom: 6px; }
        .umi-db-tags { display: flex; flex-wrap: wrap; gap: 6px; }
        .umi-db-tag { font-size: 11px; padding: 4px 7px; border-radius: 5px; border: 1px solid var(--umi-rule-strong); background: var(--umi-surface); color: var(--umi-ink); cursor: pointer; user-select: none; }
        .umi-db-tag.selected { background: var(--umi-accent-soft); border-color: var(--umi-accent); color: var(--umi-ink-strong); }
        .umi-db-tag.artist { border-color: var(--umi-variable); }
        .umi-db-tag.copyright { border-color: var(--umi-warn); }
        .umi-db-tag.character { border-color: var(--umi-ok); }
        .umi-db-tag.meta { color: var(--umi-ink); }
        .umi-db-actions { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 7px; }
        .umi-db-actions .wide { grid-column: 1 / -1; }
        .umi-db-textarea { width: 100%; min-height: 105px; resize: vertical; box-sizing: border-box; font-family: Consolas, monospace; }
        .umi-db-small { font-size: 11px; color: var(--umi-ink-2); line-height: 1.4; }
      </style>
      <div class="umi-db-root">
        <div class="umi-db-header">
          <div class="umi-db-title">Danbooru Browser</div>
          <div class="umi-db-search-wrap">
            <input class="umi-db-input" data-role="query" placeholder="type tags, e.g. princess zelda, solo, blue eyes" autocomplete="off" />
            <div class="umi-db-suggestions" data-role="suggestions"></div>
          </div>
          <select class="umi-db-select" data-role="rating">
            <option value="g">safe/general</option>
            <option value="s">sensitive</option>
            <option value="q">questionable</option>
            <option value="e">explicit</option>
            <option value="any">any rating</option>
          </select>
          <select class="umi-db-select" data-role="limit">
            <option>24</option><option>48</option><option>72</option>
          </select>
          <button class="umi-db-btn umi-db-btn-primary" data-action="search">Search</button>
          <button class="umi-db-btn" data-action="series-importer">Series Importer</button>
          <button class="umi-db-btn" data-action="close">Close</button>
        </div>
        <div class="umi-db-body">
          <div class="umi-db-grid-wrap">
            <div class="umi-db-grid" data-role="grid"></div>
            <div class="umi-db-footer">
              <button class="umi-db-btn" data-action="prev">Previous 24</button>
              <span class="umi-db-small" data-role="page">Page 1</span>
              <button class="umi-db-btn" data-action="next">Next 24</button>
            </div>
          </div>
          <div class="umi-db-detail" data-role="detail"></div>
        </div>
      </div>
    `;
    document.body.appendChild(panel);
    this.element = panel;
    this.bindEvents();
    this.renderDetail();
  }

  bindEvents() {
    this.element.querySelector('[data-action="close"]').onclick = () => this.hide();
    this.element.querySelector('[data-action="series-importer"]').onclick = () => {
      if (!window.umiSeriesImporter) return showUmiNotification("Series Importer is still loading", true);
      window.umiSeriesImporter.show();
    };
    this.element.querySelector('[data-action="search"]').onclick = () => {
      this.page = 1;
      this.search();
    };
    this.element.querySelector('[data-action="prev"]').onclick = () => {
      if (this.page > 1) {
        this.page -= 1;
        this.search();
      }
    };
    this.element.querySelector('[data-action="next"]').onclick = () => {
      this.page += 1;
      this.search();
    };
    this.element.querySelector('[data-role="limit"]').addEventListener("change", () => {
      this.updatePaginationControls();
    });
    this.element.querySelector('[data-role="query"]').addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        if (this.suggestions.length) {
          event.preventDefault();
          this.applySuggestion(this.suggestions[0].tag);
          return;
        }
        this.page = 1;
        this.search();
      }
      if (event.key === "Escape") {
        this.hideSuggestions();
      }
    });
    this.element.querySelector('[data-role="query"]').addEventListener("input", () => this.scheduleSuggestions());
    this.element.querySelector('[data-role="query"]').addEventListener("blur", () => {
      setTimeout(() => this.hideSuggestions(), 160);
    });
    this.updatePaginationControls();
  }

  async fetchWildcards() {
    const data = await this.fetchJson("/umiapp/wildcards/text/list");
    this.wildcards = data.files || [];
  }

  async fetchJson(url, options) {
    const response = api.fetchApi ? await api.fetchApi(url, options) : await fetch(url, options);
    let data = {};
    try {
      data = await response.json();
    } catch (error) {
      if (response.ok) throw error;
    }
    if (!response.ok || data.success === false) {
      throw new Error(data.error || `Request failed with HTTP ${response.status}`);
    }
    return data;
  }

  async search() {
    const query = this.element.querySelector('[data-role="query"]').value.trim();
    const rating = this.element.querySelector('[data-role="rating"]').value;
    const limit = this.element.querySelector('[data-role="limit"]').value;
    const grid = this.element.querySelector('[data-role="grid"]');
    grid.innerHTML = '<div class="umi-db-small">Searching Danbooru...</div>';
    try {
      const params = new URLSearchParams({ tags: query, rating, limit, page: String(this.page) });
      const data = await this.fetchJson(`/umiapp/danbooru/search?${params.toString()}`);
      this.posts = data.posts || [];
      this.lastQuery = data.query || query;
      this.lastCount = data.count ?? this.posts.length;
      this.selectedPost = this.posts[0] || null;
      this.selectedTags.clear();
      this.renderGrid();
      this.renderDetail();
      this.updatePaginationControls();
      grid.scrollTop = 0;
    } catch (error) {
      console.error("[Umi Danbooru] Search failed:", error);
      grid.innerHTML = `<div class="umi-db-small">Search failed: ${escapeHtml(error.message)}</div>`;
    }
  }

  currentLimit() {
    return this.element?.querySelector('[data-role="limit"]')?.value || "24";
  }

  updatePaginationControls() {
    const limit = this.currentLimit();
    const pageEl = this.element?.querySelector('[data-role="page"]');
    const prevEl = this.element?.querySelector('[data-action="prev"]');
    const nextEl = this.element?.querySelector('[data-action="next"]');
    if (pageEl) {
      const start = (this.page - 1) * Number(limit) + 1;
      const end = start + Math.max(0, this.posts.length - 1);
      pageEl.textContent = this.posts.length ? `Results ${start}-${end}` : `Page ${this.page}`;
    }
    if (prevEl) {
      prevEl.textContent = `Previous ${limit}`;
      prevEl.disabled = this.page <= 1;
    }
    if (nextEl) {
      nextEl.textContent = `Next ${limit}`;
      nextEl.disabled = this.posts.length < Number(limit);
    }
  }

  currentSearchFragmentInfo() {
    const input = this.element.querySelector('[data-role="query"]');
    const value = input.value;
    const cursor = input.selectionStart ?? value.length;
    const before = value.slice(0, cursor);
    const commaIndex = before.lastIndexOf(",");
    const chunkStart = commaIndex >= 0 ? commaIndex + 1 : 0;
    const chunk = before.slice(chunkStart);
    if (!chunk.trim() || /\s$/.test(chunk)) {
      return { fragment: "", start: cursor, end: cursor };
    }

    const wordMatches = [...chunk.matchAll(/\S+/g)];
    if (!wordMatches.length) {
      return { fragment: "", start: cursor, end: cursor };
    }
    const words = wordMatches.map(match => ({ text: match[0], start: chunkStart + match.index }));
    const lastWords = words.length <= 2 ? words : words.slice(-2);
    return {
      fragment: lastWords.map(word => word.text).join(" "),
      start: lastWords[0].start,
      end: cursor,
    };
  }

  currentSearchFragment() {
    return this.currentSearchFragmentInfo().fragment;
  }

  scheduleSuggestions() {
    clearTimeout(this.suggestTimer);
    this.suggestTimer = setTimeout(() => this.fetchSuggestions(), 180);
  }

  async fetchSuggestions() {
    const fragment = this.currentSearchFragment();
    if (fragment.length < 2) {
      this.hideSuggestions();
      return;
    }
    try {
      const params = new URLSearchParams({ query: fragment, limit: "12" });
      const data = await this.fetchJson(`/umiapp/autocomplete/tags?${params.toString()}`);
      this.suggestions = (data.tags || [])
        .map(item => ({ tag: item.tag || item.value || "", count: item.count || 0 }))
        .filter(item => item.tag);
      this.renderSuggestions();
    } catch (error) {
      this.hideSuggestions();
    }
  }

  renderSuggestions() {
    const box = this.element.querySelector('[data-role="suggestions"]');
    if (!this.suggestions.length) {
      this.hideSuggestions();
      return;
    }
    box.innerHTML = this.suggestions.map(item => `
      <button class="umi-db-suggestion" data-tag="${escapeHtml(item.tag)}" type="button">
        <span class="umi-db-suggestion-tag">${escapeHtml(item.tag.replaceAll("_", " "))}</span>
        <span class="umi-db-suggestion-count">${item.count ? escapeHtml(String(item.count)) : ""}</span>
      </button>
    `).join("");
    box.querySelectorAll(".umi-db-suggestion").forEach(button => {
      button.onmousedown = (event) => event.preventDefault();
      button.onclick = () => this.applySuggestion(button.dataset.tag);
    });
    box.style.display = "block";
  }

  hideSuggestions() {
    this.suggestions = [];
    const box = this.element?.querySelector('[data-role="suggestions"]');
    if (box) {
      box.style.display = "none";
      box.innerHTML = "";
    }
  }

  applySuggestion(tag) {
    const input = this.element.querySelector('[data-role="query"]');
    const value = input.value;
    const cursor = input.selectionStart ?? value.length;
    const info = this.currentSearchFragmentInfo();
    const before = value.slice(0, info.start);
    const after = value.slice(cursor);
    const prefix = before;
    const needsSeparator = prefix && !/[\s,]$/.test(prefix) ? " " : "";
    const nextValue = `${prefix}${needsSeparator}${tag} ${after.replace(/^\s+/, "")}`;
    const nextCursor = `${prefix}${needsSeparator}${tag} `.length;
    input.value = nextValue;
    input.focus();
    input.setSelectionRange(nextCursor, nextCursor);
    this.hideSuggestions();
  }

  renderGrid() {
    const grid = this.element.querySelector('[data-role="grid"]');
    if (!this.posts.length) {
      const queryText = this.lastQuery ? `<br>Query: <code>${escapeHtml(this.lastQuery)}</code>` : "";
      grid.innerHTML = `<div class="umi-db-small">No posts found.${queryText}</div>`;
      return;
    }
    grid.innerHTML = this.posts.map(post => `
      <div class="umi-db-card ${this.selectedPost?.id === post.id ? "active" : ""}" data-id="${post.id}">
        <img class="umi-db-thumb" src="${escapeHtml(post.preview_url || "")}" loading="lazy" />
        <div class="umi-db-card-meta">
          <span>#${post.id}</span>
          <span>${escapeHtml(post.rating || "?")} | ${post.width || "?"}x${post.height || "?"}</span>
        </div>
      </div>
    `).join("");
    grid.querySelectorAll(".umi-db-card").forEach(card => {
      card.onclick = () => {
        this.selectedPost = this.posts.find(post => String(post.id) === card.dataset.id);
        this.selectedTags.clear();
        this.renderGrid();
        this.renderDetail();
      };
    });
  }

  renderDetail() {
    const detail = this.element?.querySelector('[data-role="detail"]');
    if (!detail) return;
    if (!this.selectedPost) {
      detail.innerHTML = '<div class="umi-db-small">Search for a character, outfit, pose, artist, or source tag. Select an image to inspect and collect its tags.</div>';
      return;
    }
    const post = this.selectedPost;
    detail.innerHTML = `
      <img class="umi-db-preview" src="${escapeHtml(post.large_url || post.preview_url || "")}" />
      <div class="umi-db-section">
        <div class="umi-db-small">
          <a href="${escapeHtml(post.post_url)}" target="_blank" style="color:var(--umi-accent);">Danbooru #${post.id}</a>
          · rating ${escapeHtml(post.rating || "?")} · score ${post.score ?? "?"}
        </div>
      </div>
      <div class="umi-db-section umi-db-actions">
        <button class="umi-db-btn" data-action="select-core">Select character/source/artist</button>
        <button class="umi-db-btn" data-action="select-outfit">Select outfit-ish general tags</button>
        <button class="umi-db-btn" data-action="select-all">Select all tags</button>
        <button class="umi-db-btn" data-action="clear-tags">Clear selection</button>
      </div>
      ${Object.entries(CATEGORY_LABELS).map(([key, label]) => this.renderTagCategory(key, label, post.tags?.[key] || [])).join("")}
      <div class="umi-db-section">
        <div class="umi-db-section-title">Selected tags</div>
        <textarea class="umi-db-textarea" data-role="selected-tags">${escapeHtml(this.tagLine())}</textarea>
      </div>
      <div class="umi-db-section">
        <div class="umi-db-section-title">Wildcard</div>
        <input class="umi-db-input" data-role="wildcard-name" list="umi-db-wildcards" placeholder="characters/zelda_outfit" style="width:100%; box-sizing:border-box; min-width:0;" />
        <datalist id="umi-db-wildcards">${this.wildcards.map(name => `<option value="${escapeHtml(name)}"></option>`).join("")}</datalist>
      </div>
      <div class="umi-db-section umi-db-actions">
        <button class="umi-db-btn" data-action="append-wildcard">Append to wildcard</button>
        <button class="umi-db-btn" data-action="overwrite-wildcard">Overwrite wildcard</button>
        <button class="umi-db-btn" data-action="read-wildcard">Load wildcard editor</button>
        <button class="umi-db-btn" data-action="save-editor">Save editor</button>
        <button class="umi-db-btn wide" data-action="inject-append">Inject into selected Umi prompt</button>
        <button class="umi-db-btn wide" data-action="copy-tags">Copy selected tags</button>
      </div>
      <div class="umi-db-section">
        <textarea class="umi-db-textarea" data-role="wildcard-editor" placeholder="Wildcard file content..."></textarea>
      </div>
    `;
    this.bindDetailEvents();
  }

  renderTagCategory(key, label, tags) {
    if (!tags.length) return "";
    return `
      <div class="umi-db-section">
        <div class="umi-db-section-title">${label}</div>
        <div class="umi-db-tags">
          ${tags.map(tag => `<span class="umi-db-tag ${key} ${this.selectedTags.has(tag) ? "selected" : ""}" data-tag="${escapeHtml(tag)}">${escapeHtml(tag.replaceAll("_", " "))}</span>`).join("")}
        </div>
      </div>
    `;
  }

  bindDetailEvents() {
    this.element.querySelectorAll(".umi-db-tag").forEach(tagEl => {
      tagEl.onclick = () => {
        const tag = tagEl.dataset.tag;
        if (this.selectedTags.has(tag)) this.selectedTags.delete(tag);
        else this.selectedTags.add(tag);
        this.renderDetail();
      };
    });
    const action = (name, fn) => {
      const el = this.element.querySelector(`[data-action="${name}"]`);
      if (el) el.onclick = fn;
    };
    action("select-core", () => this.selectCategories(["artist", "copyright", "character"]));
    action("select-outfit", () => this.selectOutfitTags());
    action("select-all", () => this.selectCategories(["artist", "copyright", "character", "general", "meta"]));
    action("clear-tags", () => { this.selectedTags.clear(); this.renderDetail(); });
    action("append-wildcard", () => this.writeWildcard("append"));
    action("overwrite-wildcard", () => this.writeWildcard("overwrite"));
    action("read-wildcard", () => this.readWildcard());
    action("save-editor", () => this.saveEditor());
    action("inject-append", () => this.injectIntoUmi("append"));
    action("copy-tags", () => copyText(this.tagLine(), "Tags copied"));
    const selectedArea = this.element.querySelector('[data-role="selected-tags"]');
    selectedArea.oninput = () => {
      this.selectedTags = new Set(selectedArea.value.split(",").map(t => t.trim().replaceAll(" ", "_")).filter(Boolean));
    };
  }

  selectCategories(categories) {
    for (const category of categories) {
      for (const tag of this.selectedPost?.tags?.[category] || []) this.selectedTags.add(tag);
    }
    this.renderDetail();
  }

  selectOutfitTags() {
    const needles = /(clothes|shirt|skirt|dress|jacket|coat|pants|boots|shoes|hat|gloves|uniform|armor|sleeves|collar|hood|goggles|belt|bow|hair|eyes|wearing|outfit|bikini|swimsuit|kimono|socks|thighhighs)/i;
    for (const tag of this.selectedPost?.tags?.general || []) {
      if (needles.test(tag)) this.selectedTags.add(tag);
    }
    this.selectCategories(["character", "copyright"]);
  }

  tagLine() {
    return Array.from(this.selectedTags).join(", ");
  }

  wildcardName() {
    return this.element.querySelector('[data-role="wildcard-name"]')?.value?.trim();
  }

  async writeWildcard(mode) {
    const name = this.wildcardName();
    if (!name) return showUmiNotification("Choose a wildcard name", true);
    try {
      await this.fetchJson("/umiapp/wildcards/text/write", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, mode, content: this.tagLine() }),
      });
      showUmiNotification(mode === "append" ? "Tags appended" : "Wildcard saved");
      await this.fetchWildcards();
      this.renderDetail();
    } catch (error) {
      showUmiNotification(error.message || "Wildcard write failed", true);
    }
  }

  async readWildcard() {
    const name = this.wildcardName();
    if (!name) return showUmiNotification("Choose a wildcard name", true);
    try {
      const data = await this.fetchJson(`/umiapp/wildcards/text/read?name=${encodeURIComponent(name)}`);
      this.element.querySelector('[data-role="wildcard-editor"]').value = data.content || "";
    } catch (error) {
      showUmiNotification(error.message || "Wildcard read failed", true);
    }
  }

  async saveEditor() {
    const name = this.wildcardName();
    const content = this.element.querySelector('[data-role="wildcard-editor"]').value;
    if (!name) return showUmiNotification("Choose a wildcard name", true);
    try {
      await this.fetchJson("/umiapp/wildcards/text/write", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, mode: "overwrite", content }),
      });
      showUmiNotification("Wildcard editor saved");
    } catch (error) {
      showUmiNotification(error.message || "Wildcard save failed", true);
    }
  }

  selectedUmiNode() {
    const selected = app.canvas?.selected_nodes ? Object.values(app.canvas.selected_nodes) : [];
    return selected.find(node => node?.type === "UmiAIWildcardNode" || node?.type === "UmiAIWildcardNodeLite")
      || app.graph?._nodes?.find(node => node?.type === "UmiAIWildcardNode" || node?.type === "UmiAIWildcardNodeLite");
  }

  injectIntoUmi(mode) {
    const node = this.selectedUmiNode();
    if (!node) return showUmiNotification("Select or create a Umi wildcard node first", true);
    const widget = node.widgets?.find(w => w.name === "text") || node.widgets?.[0];
    if (!widget) return showUmiNotification("Umi prompt widget not found", true);
    const tags = this.tagLine();
    const current = String(widget.value || "");
    widget.value = mode === "replace" ? tags : (current ? `${current.trim()}\n${tags}` : tags);
    widget.callback?.(widget.value);
    app.graph?.setDirtyCanvas?.(true, true);
    showUmiNotification("Tags injected into Umi prompt");
  }

  async show() {
    if (!this.element) this.createPanel();
    await this.fetchWildcards();
    this.element.style.display = "block";
    this.renderDetail();
  }

  hide() {
    if (this.element) this.element.style.display = "none";
  }
}

app.registerExtension({
  name: "Umi.DanbooruBrowser",
  async setup() {
    window.umiDanbooruBrowser = new DanbooruBrowserPanel();
  },
});
