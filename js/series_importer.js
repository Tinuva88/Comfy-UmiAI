import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { escapeHtml, showUmiNotification } from "./umi_frontend_utils.js";
import { ensureUmiTheme } from "./umi_theme.js";

const DEFAULT_FILTERS = {
  gender: "all",
  role: "all",
  minimum_posts: 100,
  minimum_favourites: 0,
  character_limit: 250,
};

const DEFAULT_OPTIONS = {
  target: "",
  copyright_tag: "",
  mode: "overwrite",
  output_format: "danbooru",
  include_copyright: true,
  variant_mode: "none",
  minimum_variant_posts: 25,
  eligible_only: false,
};

class SeriesImporterPanel {
  constructor() {
    this.element = null;
    this.mediaResults = [];
    this.media = null;
    this.characters = [];
    this.copyrightCandidates = [];
    this.tagDatabase = null;
    this.manifests = [];
    this.filters = { ...DEFAULT_FILTERS };
    this.options = { ...DEFAULT_OPTIONS };
    this.busy = false;
    this.lastWrite = null;
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

  createPanel() {
    const panel = document.createElement("div");
    panel.className = "umi-series-importer";
    panel.style.cssText = `
      position:fixed; inset:0; width:100vw; height:100vh; display:none;
      background:var(--umi-sunken); color:var(--umi-ink); z-index:10010;
      font-family:"Segoe UI",Tahoma,Geneva,Verdana,sans-serif;
    `;
    ensureUmiTheme();
    panel.innerHTML = `
      <style>
        .umi-si-root{height:100%;display:grid;grid-template-rows:58px minmax(0,1fr);min-height:0}
        .umi-si-header{display:flex;align-items:center;gap:9px;padding:10px 16px;background:var(--umi-ground);border-bottom:1px solid var(--umi-rule);box-sizing:border-box}
        .umi-si-title{font-size:17px;font-weight:700;color:var(--umi-accent);white-space:nowrap;margin-right:6px}
        .umi-si-input,.umi-si-select,.umi-si-number{background:var(--umi-sunken);color:var(--umi-ink-strong);border:1px solid var(--umi-rule-strong);border-radius:6px;padding:7px 9px;font-size:12px;box-sizing:border-box}
        .umi-si-header .umi-si-input{flex:1;min-width:260px}
        .umi-si-select{height:32px}.umi-si-number{width:100px}
        .umi-si-btn{background:var(--umi-surface-alt);color:var(--umi-ink);border:1px solid var(--umi-rule-strong);border-radius:6px;padding:7px 10px;cursor:pointer;font-size:12px}
        .umi-si-btn:hover{border-color:var(--umi-accent);background:var(--umi-surface-hover)}.umi-si-btn:disabled{opacity:.45;cursor:not-allowed}
        .umi-si-primary{background:var(--umi-accent-soft);border-color:var(--umi-accent)}.umi-si-success{background:var(--umi-ok-soft);border-color:var(--umi-ok)}
        .umi-si-body{display:grid;grid-template-columns:330px minmax(0,1fr);min-height:0;overflow:hidden}
        .umi-si-media{border-right:1px solid var(--umi-rule);background:var(--umi-sunken);overflow:auto;padding:12px;box-sizing:border-box}
        .umi-si-main{min-width:0;min-height:0;overflow:auto;padding:14px;box-sizing:border-box}
        .umi-si-card{display:grid;grid-template-columns:54px minmax(0,1fr);gap:9px;padding:8px;margin-bottom:8px;background:var(--umi-ground);border:1px solid var(--umi-rule);border-radius:7px;cursor:pointer}
        .umi-si-card:hover,.umi-si-card.active{border-color:var(--umi-accent);background:var(--umi-surface)}
        .umi-si-cover{width:54px;height:76px;object-fit:cover;background:var(--umi-sunken);border-radius:4px}
        .umi-si-card-title{font-size:12px;font-weight:650;color:var(--umi-ink-strong);line-height:1.3}.umi-si-muted{font-size:11px;color:var(--umi-ink-2);line-height:1.45}
        .umi-si-empty{display:flex;align-items:center;justify-content:center;min-height:260px;color:var(--umi-ink-2);text-align:center;padding:24px}
        .umi-si-heading{font-size:16px;font-weight:700;color:var(--umi-ink-strong)}.umi-si-subheading{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--umi-accent);margin-bottom:7px}
        .umi-si-config{display:grid;grid-template-columns:repeat(6,minmax(115px,1fr));gap:9px;padding:12px;background:var(--umi-ground);border:1px solid var(--umi-rule);border-radius:8px;margin:12px 0}
        .umi-si-field{display:flex;flex-direction:column;gap:5px;min-width:0}.umi-si-field label{font-size:10px;text-transform:uppercase;letter-spacing:.05em;color:var(--umi-ink)}
        .umi-si-field .umi-si-input,.umi-si-field .umi-si-select,.umi-si-field .umi-si-number{width:100%;min-width:0}
        .umi-si-span2{grid-column:span 2}.umi-si-span3{grid-column:span 3}.umi-si-check{display:flex;align-items:center;gap:7px;font-size:12px;padding-top:7px}
        .umi-si-toolbar{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:10px}.umi-si-summary{margin-left:auto;font-size:11px;color:var(--umi-ink)}
        .umi-si-table-wrap{border:1px solid var(--umi-rule);border-radius:8px;overflow:auto;max-height:calc(100vh - 330px);background:var(--umi-sunken)}
        .umi-si-table{width:100%;border-collapse:collapse;font-size:11px;min-width:980px}
        .umi-si-table th{position:sticky;top:0;z-index:2;background:var(--umi-surface);color:var(--umi-ink);text-align:left;padding:7px;border-bottom:1px solid var(--umi-rule-strong);font-size:10px;text-transform:uppercase;letter-spacing:.04em}
        .umi-si-table td{padding:7px;border-bottom:1px solid var(--umi-rule);vertical-align:top}.umi-si-table tr.ineligible{opacity:.5}.umi-si-table tr:hover{background:var(--umi-ground)}
        .umi-si-character{display:grid;grid-template-columns:36px minmax(0,1fr);gap:7px;min-width:155px}.umi-si-avatar{width:36px;height:48px;object-fit:cover;background:var(--umi-sunken);border-radius:4px}
        .umi-si-tag-input{width:100%;min-width:210px;background:var(--umi-sunken);color:var(--umi-ink);border:1px solid var(--umi-rule-strong);border-radius:4px;padding:5px 6px;font:11px Consolas,monospace;box-sizing:border-box}
        .umi-si-badge{display:inline-block;padding:2px 5px;border:1px solid var(--umi-accent-soft);border-radius:10px;color:var(--umi-ink);font-size:10px;white-space:nowrap}.umi-si-badge.good{border-color:var(--umi-ok);color:var(--umi-ok)}.umi-si-badge.warn{border-color:var(--umi-warn-soft);color:var(--umi-warn)}.umi-si-badge.bad{border-color:var(--umi-danger-soft);color:var(--umi-danger)}
        .umi-si-variants{max-width:300px}.umi-si-variants summary{cursor:pointer;color:var(--umi-accent);white-space:nowrap}.umi-si-variant-list{margin-top:6px;max-height:145px;overflow:auto;background:var(--umi-sunken);border:1px solid var(--umi-rule);border-radius:5px;padding:5px;min-width:250px}
        .umi-si-variant{display:grid;grid-template-columns:18px minmax(0,1fr) auto;gap:5px;padding:3px;align-items:start;font:10px Consolas,monospace}.umi-si-verified{color:var(--umi-ok)}.umi-si-heuristic{color:var(--umi-warn)}
        .umi-si-status{padding:8px 10px;border-radius:6px;background:var(--umi-sunken);border:1px solid var(--umi-rule);font-size:11px;color:var(--umi-ink);margin-bottom:10px}.umi-si-status.error{border-color:var(--umi-danger-soft);color:var(--umi-danger)}.umi-si-status.success{border-color:var(--umi-ok);color:var(--umi-ok)}
        @media(max-width:1150px){.umi-si-body{grid-template-columns:260px minmax(0,1fr)}.umi-si-config{grid-template-columns:repeat(3,minmax(110px,1fr))}}
      </style>
      <div class="umi-si-root">
        <div class="umi-si-header">
          <div class="umi-si-title">Series Character Importer</div>
          <input class="umi-si-input" data-role="series-query" placeholder="Search anime or manga..." />
          <select class="umi-si-select" data-role="media-type"><option value="ANIME">Anime</option><option value="MANGA">Manga</option></select>
          <select class="umi-si-select" data-role="character-limit" title="Popularity-sorted cast depth"><option value="100">Top 100 cast</option><option value="250" selected>Top 250 cast</option><option value="500">Top 500 cast</option><option value="0">Complete cast</option></select>
          <button class="umi-si-btn umi-si-primary" data-action="series-search">Search</button>
          <select class="umi-si-select" data-role="manifest"><option value="">Previous imports...</option></select>
          <button class="umi-si-btn" data-action="load-manifest">Refresh import</button>
          <button class="umi-si-btn" data-action="close">Back to Danbooru</button>
        </div>
        <div class="umi-si-body">
          <div class="umi-si-media" data-role="media-results"><div class="umi-si-muted">Search for a series to begin.</div></div>
          <div class="umi-si-main" data-role="workspace"><div class="umi-si-empty">Choose a precise series entry, review its character matches, then write the wildcard.</div></div>
        </div>
      </div>
    `;
    document.body.appendChild(panel);
    this.element = panel;
    this.bindShellEvents();
  }

  bindShellEvents() {
    const query = this.element.querySelector('[data-role="series-query"]');
    this.element.querySelector('[data-action="close"]').onclick = () => this.hide();
    this.element.querySelector('[data-action="series-search"]').onclick = () => this.searchSeries();
    this.element.querySelector('[data-action="load-manifest"]').onclick = () => this.loadSelectedManifest();
    query.addEventListener("keydown", event => {
      if (event.key === "Enter") this.searchSeries();
      if (event.key === "Escape") this.hide();
    });
  }

  setBusy(busy, message = "") {
    this.busy = busy;
    this.element?.querySelectorAll("button").forEach(button => { button.disabled = busy; });
    if (message) this.setStatus(message);
  }

  setStatus(message, kind = "") {
    const status = this.element?.querySelector('[data-role="status"]');
    if (status) {
      status.className = `umi-si-status ${kind}`;
      status.textContent = message;
    }
  }

  async searchSeries() {
    const query = this.element.querySelector('[data-role="series-query"]').value.trim();
    const type = this.element.querySelector('[data-role="media-type"]').value;
    if (!query) return showUmiNotification("Enter a series title", true);
    const list = this.element.querySelector('[data-role="media-results"]');
    list.innerHTML = '<div class="umi-si-muted">Searching AniList...</div>';
    this.setBusy(true);
    try {
      const params = new URLSearchParams({ query, type });
      const data = await this.fetchJson(`/umiapp/series-import/search?${params}`);
      this.mediaResults = data.items || [];
      this.renderMediaResults();
    } catch (error) {
      list.innerHTML = `<div class="umi-si-muted">Search failed: ${escapeHtml(error.message)}</div>`;
    } finally {
      this.setBusy(false);
    }
  }

  renderMediaResults() {
    const list = this.element.querySelector('[data-role="media-results"]');
    if (!this.mediaResults.length) {
      list.innerHTML = '<div class="umi-si-muted">No matching series found.</div>';
      return;
    }
    list.innerHTML = this.mediaResults.map((media, index) => `
      <div class="umi-si-card ${this.media?.id === media.id ? "active" : ""}" data-media-index="${index}">
        <img class="umi-si-cover" src="${escapeHtml(media.cover || "")}" loading="lazy" />
        <div>
          <div class="umi-si-card-title">${escapeHtml(media.title)}</div>
          <div class="umi-si-muted">${escapeHtml(media.format || media.type || "")} ${media.year ? `&middot; ${media.year}` : ""}</div>
          <div class="umi-si-muted">AniList ${media.id}${media.mal_id ? ` &middot; MAL ${media.mal_id}` : ""}</div>
        </div>
      </div>
    `).join("");
    list.querySelectorAll("[data-media-index]").forEach(card => {
      card.onclick = () => this.loadMedia(this.mediaResults[Number(card.dataset.mediaIndex)]);
    });
  }

  async loadMedia(media, manifest = null) {
    if (!media?.id) return;
    this.media = media;
    this.characters = [];
    this.lastWrite = null;
    if (manifest) {
      this.filters = { ...DEFAULT_FILTERS, ...(manifest.filters || {}) };
      this.options = {
        ...DEFAULT_OPTIONS,
        ...(manifest.options || {}),
        target: manifest.wildcard || "",
        copyright_tag: manifest.copyright_tag || "",
      };
    } else {
      this.filters = { ...DEFAULT_FILTERS };
      this.options = { ...DEFAULT_OPTIONS, target: `characters/${this.slug(media.title)}` };
    }
    const limitControl = this.element.querySelector('[data-role="character-limit"]');
    if (manifest && limitControl) limitControl.value = String(this.filters.character_limit ?? 250);
    const characterLimit = Number(limitControl?.value ?? this.filters.character_limit ?? 250);
    this.filters.character_limit = characterLimit;
    this.renderMediaResults();
    this.element.querySelector('[data-role="workspace"]').innerHTML = '<div class="umi-si-empty">Fetching the complete AniList cast and matching Danbooru tags...</div>';
    this.setBusy(true);
    try {
      const data = await this.fetchJson(`/umiapp/series-import/characters?media_id=${encodeURIComponent(media.id)}&limit=${encodeURIComponent(characterLimit)}`);
      this.media = data.media || media;
      this.characters = data.characters || [];
      this.tagDatabase = data.tag_database || null;
      this.copyrightCandidates = data.copyright_match?.candidates || [];
      if (!manifest) this.options.copyright_tag = data.copyright_match?.selected_tag || "";
      this.applyManifestSelections(manifest);
      this.renderMediaResults();
      this.renderWorkspace();
    } catch (error) {
      this.element.querySelector('[data-role="workspace"]').innerHTML = `<div class="umi-si-empty">Could not load characters:<br>${escapeHtml(error.message)}</div>`;
    } finally {
      this.setBusy(false);
    }
  }

  applyManifestSelections(manifest) {
    if (!manifest?.characters?.length) return;
    const byId = new Map(manifest.characters.map(item => [String(item.source_id), item]));
    for (const character of this.characters) {
      const saved = byId.get(String(character.source_id));
      if (!saved) continue;
      character.selected_tag = saved.selected_tag || character.selected_tag;
      character.post_count = saved.post_count ?? character.post_count;
      character.include = saved.include !== false;
      if (saved.variants?.length) character.variants = saved.variants;
      character.confidence = "saved";
      character.confidence_score = 100;
    }
  }

  renderWorkspace() {
    const workspace = this.element.querySelector('[data-role="workspace"]');
    const media = this.media;
    const copyrightOptions = this.copyrightCandidates.map(item => `<option value="${escapeHtml(item.tag)}">${escapeHtml(item.tag)} (${item.post_count.toLocaleString()})</option>`).join("");
    workspace.innerHTML = `
      <div class="umi-si-heading">${escapeHtml(media.title)}</div>
      <div class="umi-si-muted">${this.characters.length}${media.character_total ? ` of ${media.character_total}` : ""} AniList characters${media.characters_truncated ? " (popularity-sorted cast depth)" : ""} &middot; ${escapeHtml(this.tagDatabase?.source || "no local tag database")}</div>
      <div class="umi-si-config">
        <div class="umi-si-field"><label>Gender</label><select class="umi-si-select" data-filter="gender">
          <option value="all">All</option><option value="Female">Female</option><option value="Male">Male</option><option value="Non-binary">Non-binary</option><option value="Unknown">Unknown</option>
        </select></div>
        <div class="umi-si-field"><label>Role</label><select class="umi-si-select" data-filter="role">
          <option value="all">All roles</option><option value="MAIN">Main</option><option value="SUPPORTING">Supporting</option><option value="BACKGROUND">Background</option>
        </select></div>
        <div class="umi-si-field"><label>Minimum Danbooru posts</label><input class="umi-si-number" type="number" min="0" step="25" data-filter="minimum_posts" /></div>
        <div class="umi-si-field"><label>Minimum AniList favourites</label><input class="umi-si-number" type="number" min="0" step="10" data-filter="minimum_favourites" /></div>
        <div class="umi-si-field"><label>Variant mode</label><select class="umi-si-select" data-option="variant_mode"><option value="none">No variants</option><option value="flat">Flat variants</option><option value="grouped">Grouped variants</option></select></div>
        <div class="umi-si-field"><label>Minimum variant posts</label><input class="umi-si-number" type="number" min="0" step="5" data-option="minimum_variant_posts" /></div>
        <div class="umi-si-field umi-si-span2"><label>Target wildcard</label><input class="umi-si-input" data-option="target" placeholder="characters/series" /></div>
        <div class="umi-si-field umi-si-span2"><label>Danbooru copyright tag</label><input class="umi-si-input" data-option="copyright_tag" list="umi-si-copyrights" /><datalist id="umi-si-copyrights">${copyrightOptions}</datalist></div>
        <div class="umi-si-field"><label>Output</label><select class="umi-si-select" data-option="output_format"><option value="danbooru">Danbooru tags</option><option value="natural">Natural language</option><option value="metadata">Tags + metadata</option></select></div>
        <div class="umi-si-field"><label>Write mode</label><select class="umi-si-select" data-option="mode"><option value="overwrite">Replace</option><option value="append">Append</option></select></div>
        <label class="umi-si-check"><input type="checkbox" data-option="include_copyright" /> Add series/copyright tag</label>
        <label class="umi-si-check"><input type="checkbox" data-option="eligible_only" /> Show eligible only</label>
      </div>
      <div class="umi-si-status" data-role="status">Review automatic matches. Amber matches and local-name variants deserve extra attention.</div>
      <div class="umi-si-toolbar">
        <button class="umi-si-btn" data-action="select-eligible">Select eligible</button>
        <button class="umi-si-btn" data-action="clear-selection">Clear selection</button>
        <button class="umi-si-btn" data-action="verify-variants">Verify variants with Danbooru</button>
        <button class="umi-si-btn umi-si-success" data-action="write">Write wildcard</button>
        <span class="umi-si-summary" data-role="summary"></span>
      </div>
      <div class="umi-si-table-wrap"><table class="umi-si-table">
        <thead><tr><th>Use</th><th>Character</th><th>Gender / role</th><th>Danbooru tag</th><th>Posts</th><th>Match</th><th>Variants</th></tr></thead>
        <tbody data-role="character-rows"></tbody>
      </table></div>
    `;
    this.syncControlValues();
    this.bindWorkspaceEvents();
    this.renderCharacterRows();
  }

  syncControlValues() {
    for (const [key, value] of Object.entries(this.filters)) {
      const input = this.element.querySelector(`[data-filter="${key}"]`);
      if (input) input.value = value;
    }
    for (const [key, value] of Object.entries(this.options)) {
      const input = this.element.querySelector(`[data-option="${key}"]`);
      if (!input) continue;
      if (input.type === "checkbox") input.checked = Boolean(value);
      else input.value = value;
    }
  }

  bindWorkspaceEvents() {
    this.element.querySelectorAll("[data-filter]").forEach(input => {
      input.addEventListener("change", () => {
        const key = input.dataset.filter;
        this.filters[key] = input.type === "number" ? Number(input.value || 0) : input.value;
        this.renderCharacterRows();
      });
    });
    this.element.querySelectorAll("[data-option]").forEach(input => {
      input.addEventListener("change", () => {
        const key = input.dataset.option;
        this.options[key] = input.type === "checkbox" ? input.checked : (input.type === "number" ? Number(input.value || 0) : input.value);
        if (["eligible_only", "minimum_variant_posts", "variant_mode"].includes(key)) this.renderCharacterRows();
      });
    });
    this.element.querySelector('[data-action="select-eligible"]').onclick = () => {
      this.characters.forEach(character => { character.include = this.isEligible(character); });
      this.renderCharacterRows();
    };
    this.element.querySelector('[data-action="clear-selection"]').onclick = () => {
      this.characters.forEach(character => { character.include = false; });
      this.renderCharacterRows();
    };
    this.element.querySelector('[data-action="verify-variants"]').onclick = () => this.verifyVariants();
    this.element.querySelector('[data-action="write"]').onclick = () => this.writeWildcard();
  }

  isEligible(character) {
    const gender = String(this.filters.gender || "all").toLowerCase();
    if (gender !== "all" && gender !== String(character.gender || "Unknown").toLowerCase()) return false;
    const role = String(this.filters.role || "all").toUpperCase();
    if (role !== "ALL" && role !== String(character.role || "").toUpperCase()) return false;
    if (Number(character.post_count || 0) < Number(this.filters.minimum_posts || 0)) return false;
    if (Number(character.favourites || 0) < Number(this.filters.minimum_favourites || 0)) return false;
    return Boolean(character.selected_tag);
  }

  renderCharacterRows() {
    const tbody = this.element.querySelector('[data-role="character-rows"]');
    if (!tbody) return;
    const visible = this.characters.map((character, index) => ({ character, index })).filter(({ character }) => !this.options.eligible_only || this.isEligible(character));
    tbody.innerHTML = visible.map(({ character, index }) => this.characterRow(character, index)).join("") || '<tr><td colspan="7"><div class="umi-si-muted">No characters match the current filters.</div></td></tr>';
    tbody.querySelectorAll("[data-character-use]").forEach(input => {
      input.onchange = () => { this.characters[Number(input.dataset.characterUse)].include = input.checked; this.updateSummary(); };
    });
    tbody.querySelectorAll("[data-character-tag]").forEach(input => {
      input.onchange = () => this.changeCharacterTag(Number(input.dataset.characterTag), input.value.trim());
    });
    tbody.querySelectorAll("[data-variant]").forEach(input => {
      input.onchange = () => {
        const [characterIndex, variantIndex] = input.dataset.variant.split(":").map(Number);
        this.characters[characterIndex].variants[variantIndex].include = input.checked;
        this.updateSummary();
      };
    });
    this.updateSummary();
  }

  characterRow(character, index) {
    const eligible = this.isEligible(character);
    const confidence = Number(character.confidence_score || 0);
    const badgeClass = confidence >= 90 ? "good" : confidence >= 75 ? "warn" : "bad";
    const candidates = (character.candidates || []).map(item => `<option value="${escapeHtml(item.tag)}">${escapeHtml(item.tag)} - ${Number(item.post_count || 0).toLocaleString()} posts - ${item.score}%</option>`).join("");
    const variants = character.variants || [];
    const eligibleVariants = variants.filter(item => Number(item.post_count || 0) >= Number(this.options.minimum_variant_posts || 0));
    const variantHtml = eligibleVariants.length ? `
      <details class="umi-si-variants"><summary>${eligibleVariants.length} candidate${eligibleVariants.length === 1 ? "" : "s"}</summary>
        <div class="umi-si-variant-list">${eligibleVariants.map(variant => {
          const originalIndex = variants.indexOf(variant);
          return `<label class="umi-si-variant ${variant.verified ? "umi-si-verified" : "umi-si-heuristic"}">
            <input type="checkbox" data-variant="${index}:${originalIndex}" ${variant.include !== false ? "checked" : ""} />
            <span>${escapeHtml(variant.tag)}</span><span>${Number(variant.post_count || 0).toLocaleString()}${variant.verified ? " verified" : " ?"}</span>
          </label>`;
        }).join("")}</div>
      </details>` : '<span class="umi-si-muted">None</span>';
    return `
      <tr class="${eligible ? "" : "ineligible"}">
        <td><input type="checkbox" data-character-use="${index}" ${character.include && eligible ? "checked" : ""} ${eligible ? "" : "disabled"} /></td>
        <td><div class="umi-si-character"><img class="umi-si-avatar" src="${escapeHtml(character.image || "")}" loading="lazy" /><div><strong>${escapeHtml(character.name)}</strong><div class="umi-si-muted">${Number(character.favourites || 0).toLocaleString()} favourites</div></div></div></td>
        <td>${escapeHtml(character.gender || "Unknown")}<br><span class="umi-si-muted">${escapeHtml(character.role || "")}</span></td>
        <td><input class="umi-si-tag-input" data-character-tag="${index}" list="umi-si-candidates-${index}" value="${escapeHtml(character.selected_tag || "")}" placeholder="Review / enter canonical tag" /><datalist id="umi-si-candidates-${index}">${candidates}</datalist></td>
        <td>${Number(character.post_count || 0).toLocaleString()}</td>
        <td><span class="umi-si-badge ${badgeClass}">${escapeHtml(character.confidence || "unmatched")}</span></td>
        <td>${variantHtml}</td>
      </tr>
    `;
  }

  async changeCharacterTag(index, tag) {
    const character = this.characters[index];
    let candidate = (character.candidates || []).find(item => item.tag === tag);
    if (tag && !candidate) {
      try {
        const data = await this.fetchJson(`/umiapp/autocomplete/tags?query=${encodeURIComponent(tag)}&limit=100`);
        const exact = (data.tags || []).find(item => item.tag === tag && Number(item.category) === 4);
        if (exact) candidate = { tag: exact.tag, post_count: exact.count, score: 100 };
      } catch (error) {
        console.warn("[Umi Series Importer] Manual tag lookup failed", error);
      }
    }
    character.selected_tag = tag;
    character.post_count = candidate?.post_count || 0;
    character.confidence = candidate ? "manual-candidate" : (tag ? "manual" : "unmatched");
    character.confidence_score = candidate ? candidate.score : (tag ? 70 : 0);
    character.include = Boolean(tag);
    character.variants = [];
    this.renderCharacterRows();
  }

  selectedCharacters() {
    return this.characters.filter(character => character.include && this.isEligible(character));
  }

  updateSummary() {
    const summary = this.element.querySelector('[data-role="summary"]');
    if (!summary) return;
    const eligible = this.characters.filter(character => this.isEligible(character)).length;
    const selected = this.selectedCharacters();
    const variants = selected.reduce((total, character) => total + (character.variants || []).filter(item => item.include !== false && Number(item.post_count || 0) >= Number(this.options.minimum_variant_posts || 0)).length, 0);
    summary.textContent = `${selected.length} selected / ${eligible} eligible / ${variants} variants`;
  }

  async verifyVariants() {
    const selected = this.selectedCharacters();
    if (!selected.length) return showUmiNotification("Select at least one eligible character", true);
    if (selected.length > 100) return showUmiNotification("Variant verification is limited to 100 selected characters", true);
    this.setBusy(true, `Checking Danbooru implications for ${selected.length} characters...`);
    try {
      const data = await this.fetchJson("/umiapp/series-import/variants", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tags: selected.map(item => item.selected_tag) }),
      });
      for (const character of selected) {
        const incoming = data.variants?.[character.selected_tag] || [];
        const existing = new Map((character.variants || []).map(item => [item.tag, item]));
        for (const variant of incoming) {
          const previous = existing.get(variant.tag);
          existing.set(variant.tag, { ...previous, ...variant, include: previous?.include ?? true });
        }
        character.variants = Array.from(existing.values()).sort((a, b) => Number(b.post_count || 0) - Number(a.post_count || 0));
      }
      const failures = Object.keys(data.errors || {}).length;
      this.setStatus(`Variant verification complete.${failures ? ` ${failures} Danbooru requests failed; local candidates were kept.` : ""}`, failures ? "" : "success");
      this.renderCharacterRows();
    } catch (error) {
      this.setStatus(`Variant verification failed: ${error.message}`, "error");
    } finally {
      this.setBusy(false);
    }
  }

  async writeWildcard() {
    const characters = this.selectedCharacters();
    if (!characters.length) return showUmiNotification("No eligible characters are selected", true);
    if (!this.options.target.trim()) return showUmiNotification("Choose a target wildcard name", true);
    const payload = {
      name: this.options.target.trim(),
      mode: this.options.mode,
      media: this.media,
      copyright_tag: this.options.copyright_tag.trim(),
      output_format: this.options.output_format,
      include_copyright: this.options.include_copyright,
      variant_mode: this.options.variant_mode,
      minimum_variant_posts: Number(this.options.minimum_variant_posts || 0),
      filters: { ...this.filters },
      characters,
    };
    this.setBusy(true, `Writing ${characters.length} characters...`);
    try {
      const data = await this.fetchJson("/umiapp/series-import/write", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      this.lastWrite = data;
      const files = (data.written_files || []).map(item => `${item.name} (${item.lines})`).join(", ");
      this.setStatus(`Saved ${data.character_count} characters in ${data.written_files?.length || 0} file(s): ${files}`, "success");
      showUmiNotification(`Series wildcard saved: __${this.options.target.trim()}__`);
      await this.fetchManifests();
      if (window.umiDanbooruBrowser?.fetchWildcards) await window.umiDanbooruBrowser.fetchWildcards();
      app.graph?.setDirtyCanvas?.(true, true);
    } catch (error) {
      this.setStatus(`Wildcard write failed: ${error.message}`, "error");
    } finally {
      this.setBusy(false);
    }
  }

  async fetchManifests() {
    try {
      const data = await this.fetchJson("/umiapp/series-import/manifests");
      this.manifests = data.items || [];
      const select = this.element?.querySelector('[data-role="manifest"]');
      if (select) {
        const previous = select.value;
        select.innerHTML = '<option value="">Previous imports...</option>' + this.manifests.map(item => `<option value="${escapeHtml(item.id)}">${escapeHtml(item.title)} -> ${escapeHtml(item.wildcard)} (${item.character_count})</option>`).join("");
        if (this.manifests.some(item => item.id === previous)) select.value = previous;
      }
    } catch (error) {
      console.warn("[Umi Series Importer] Could not load manifests", error);
    }
  }

  async loadSelectedManifest() {
    const id = this.element.querySelector('[data-role="manifest"]').value;
    if (!id) return showUmiNotification("Choose a previous import", true);
    this.setBusy(true);
    try {
      const data = await this.fetchJson(`/umiapp/series-import/manifests?id=${encodeURIComponent(id)}`);
      const manifest = data.manifest;
      if (!manifest?.media?.id) throw new Error("Manifest has no AniList media ID");
      await this.loadMedia(manifest.media, manifest);
    } catch (error) {
      showUmiNotification(error.message || "Could not refresh import", true);
    } finally {
      this.setBusy(false);
    }
  }

  slug(value) {
    return String(value || "series").normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "") || "series";
  }

  async show() {
    if (!this.element) this.createPanel();
    this.element.style.display = "block";
    await this.fetchManifests();
    this.element.querySelector('[data-role="series-query"]')?.focus();
  }

  hide() {
    if (this.element) this.element.style.display = "none";
  }
}

app.registerExtension({
  name: "Umi.SeriesImporter",
  async setup() {
    window.umiSeriesImporter = new SeriesImporterPanel();
  },
});
