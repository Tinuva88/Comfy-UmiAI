import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { ensureUmiTheme } from "./umi_theme.js";

// =============================================================================
// Wildcard browser
//
// The pack had browsers for LoRAs, images and Danbooru posts and none for
// wildcards -- the thing it is named after -- so authoring meant leaving
// ComfyUI for a text editor. The read/write routes already existed; this is the
// surface over them.
//
// Line counts are the useful column: a wildcard's candidate count is what
// decides whether a filter can match, whether siblings can differ, and whether
// a file was worth creating at all.
// =============================================================================

const STYLE_ID = "umi-wb-style";

function ensureStyles() {
    ensureUmiTheme();
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = `
        .umi-wb-overlay {
            position: fixed; inset: 0; z-index: 10055;
            background: rgba(0,0,0,0.64);
            display: flex; align-items: center; justify-content: center;
        }
        .umi-wb-modal {
            width: min(1020px, 95vw); height: min(760px, 90vh);
            display: flex; flex-direction: column;
            background: var(--umi-surface); color: var(--umi-ink);
            border: 1px solid var(--umi-rule-strong); border-radius: 6px;
            box-shadow: 0 18px 48px rgba(0,0,0,0.6);
            font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
            font-size: 13px;
        }
        .umi-wb-head {
            display: flex; align-items: center; gap: 12px;
            padding: 12px 16px; border-bottom: 1px solid var(--umi-rule);
        }
        .umi-wb-title { font-size: 15px; font-weight: 600; margin-right: auto; }
        .umi-wb-x {
            background: none; border: none; color: var(--umi-ink-2);
            font-size: 20px; line-height: 1; cursor: pointer; padding: 0 4px;
        }
        .umi-wb-x:hover { color: var(--umi-ink-strong); }
        .umi-wb-btn {
            background: var(--umi-surface-alt); color: var(--umi-ink);
            border: 1px solid var(--umi-rule-strong); border-radius: 4px;
            padding: 6px 11px; cursor: pointer; font: inherit;
        }
        .umi-wb-btn:hover { background: var(--umi-surface-hover); }
        .umi-wb-btn:disabled { opacity: 0.5; cursor: not-allowed; }
        .umi-wb-btn-primary { border-color: var(--umi-accent); color: var(--umi-accent); }
        .umi-wb-body { flex: 1; display: flex; min-height: 0; }
        .umi-wb-side {
            width: 300px; flex: 0 0 300px; display: flex; flex-direction: column;
            border-right: 1px solid var(--umi-rule); min-height: 0;
        }
        .umi-wb-search {
            margin: 10px; background: var(--umi-field); color: var(--umi-ink);
            border: 1px solid var(--umi-rule-strong); border-radius: 4px;
            padding: 6px 9px; font: inherit;
        }
        .umi-wb-search:focus { outline: 2px solid var(--umi-accent); outline-offset: -1px; }
        .umi-wb-list { flex: 1; overflow-y: auto; padding: 0 6px 8px; }
        .umi-wb-file {
            display: flex; align-items: baseline; gap: 8px;
            padding: 4px 8px; border-radius: 4px; cursor: pointer;
            font-family: ui-monospace, Consolas, monospace; font-size: 12px;
        }
        .umi-wb-folder {
            display: flex; align-items: center; gap: 6px;
            padding: 4px 8px; border-radius: 4px; cursor: pointer;
            font-family: ui-monospace, Consolas, monospace; font-size: 12px;
            color: var(--umi-ink-2); user-select: none;
        }
        .umi-wb-folder:hover { background: var(--umi-surface-alt); }
        .umi-wb-twisty {
            display: inline-block; width: 10px; flex: 0 0 10px;
            color: var(--umi-ink-3); transition: transform 0.12s;
        }
        .umi-wb-folder[aria-expanded="true"] .umi-wb-twisty { transform: rotate(90deg); }
        .umi-wb-folder-name { flex: 1; word-break: break-all; }
        .umi-wb-kids { display: none; }
        .umi-wb-folder[aria-expanded="true"] + .umi-wb-kids { display: block; }
        .umi-wb-indent { border-left: 1px solid var(--umi-rule); margin-left: 12px; padding-left: 6px; }
        .umi-wb-file:hover { background: var(--umi-surface-alt); }
        .umi-wb-file[aria-selected="true"] {
            background: var(--umi-accent-soft); color: var(--umi-ink-strong);
        }
        .umi-wb-name { flex: 1; word-break: break-all; }
        .umi-wb-count { color: var(--umi-ink-3); font-size: 11px; }
        .umi-wb-file[aria-selected="true"] .umi-wb-count { color: var(--umi-ink); }
        .umi-wb-flag { color: var(--umi-warn); font-size: 11px; }
        .umi-wb-main { flex: 1; display: flex; flex-direction: column; min-width: 0; }
        .umi-wb-bar {
            display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
            padding: 10px 14px; border-bottom: 1px solid var(--umi-rule);
        }
        .umi-wb-open {
            font-family: ui-monospace, Consolas, monospace; font-size: 12px;
            color: var(--umi-ink-2); margin-right: auto; word-break: break-all;
        }
        .umi-wb-editor {
            flex: 1; margin: 0; border: 0; resize: none;
            background: var(--umi-field); color: var(--umi-ink);
            font-family: ui-monospace, Consolas, monospace; font-size: 12px;
            line-height: 1.6; padding: 12px 14px; outline: none;
        }
        .umi-wb-empty {
            flex: 1; display: flex; align-items: center; justify-content: center;
            color: var(--umi-ink-3); padding: 24px; text-align: center;
        }
        .umi-wb-status {
            padding: 7px 14px; border-top: 1px solid var(--umi-rule);
            font-family: ui-monospace, Consolas, monospace; font-size: 11px;
            color: var(--umi-ink-3); min-height: 30px;
        }
        .umi-wb-status[data-tone="error"] { color: var(--umi-danger); }
        .umi-wb-status[data-tone="ok"] { color: var(--umi-ok); }
        .umi-wb-report { flex: 1; overflow-y: auto; padding: 4px 14px 14px; }
        .umi-wb-tally {
            font-family: ui-monospace, Consolas, monospace; font-size: 12px;
            color: var(--umi-ink-2); padding: 10px 0 4px;
        }
        .umi-wb-finding { margin-top: 16px; }
        .umi-wb-finding h4 {
            margin: 0 0 2px; font-size: 13px; display: flex; align-items: center; gap: 8px;
        }
        .umi-wb-sev {
            font-family: ui-monospace, Consolas, monospace;
            font-size: 9px; font-weight: 700; letter-spacing: 0.09em;
            text-transform: uppercase; padding: 2px 5px; border-radius: 2px;
        }
        .umi-wb-sev-error { color: var(--umi-danger); background: var(--umi-danger-wash); }
        .umi-wb-sev-warn { color: var(--umi-warn); background: rgba(255,212,59,0.12); }
        .umi-wb-sev-info { color: var(--umi-accent); background: var(--umi-accent-wash); }
        .umi-wb-why { color: var(--umi-ink-2); font-size: 12px; margin-bottom: 6px; }
        .umi-wb-item {
            display: flex; gap: 10px; padding: 4px 8px;
            border-top: 1px solid var(--umi-rule);
            font-family: ui-monospace, Consolas, monospace; font-size: 11px;
        }
        .umi-wb-item-name { color: var(--umi-ink); flex: 0 0 30%; word-break: break-all; cursor: pointer; }
        .umi-wb-item-name:hover { color: var(--umi-accent); text-decoration: underline; }
        .umi-wb-item-note { color: var(--umi-ink-3); flex: 1; word-break: break-word; }
        .umi-wb-clean { padding: 28px 0; text-align: center; color: var(--umi-ok); }
        .umi-wb-file:focus-visible, .umi-wb-folder:focus-visible { outline: 2px solid var(--umi-accent); outline-offset: -2px; }
        @media (max-width: 680px) {
            .umi-wb-head { gap: 6px; padding: 8px; flex-wrap: wrap; }
            .umi-wb-body { flex-direction: column; }
            .umi-wb-side { width: 100%; flex: 0 0 180px; border-right: 0; border-bottom: 1px solid var(--umi-rule); }
            .umi-wb-main { flex: 1; min-height: 0; }
            .umi-wb-editor { min-height: 100px; }
        }
    `;
    document.head.appendChild(style);
}

// ---------------------------------------------------------------------------

async function fetchFiles() {
    const response = await api.fetchApi("/umiapp/wildcards/text/list?details=1&all=1");
    if (!response.ok) throw new Error(`listing failed (${response.status})`);
    const data = await response.json();

    if (Array.isArray(data.details) && data.details.length) {
        return { files: data.details, root: data.root || "", detailed: true };
    }

    // A server that predates the details parameter answers with the plain
    // `files` array and ignores it. Listing the names without counts is far
    // better than showing an empty panel, which reads as "you have no
    // wildcards" when you have thousands.
    const names = Array.isArray(data.files) ? data.files : [];
    return {
        files: names.map((name) => ({
            name, ext: "txt", lines: null, blank: 0, comments: 0, bytes: 0,
        })),
        root: data.root || "",
        detailed: false,
    };
}

async function fetchContent(name, ext = "txt", source = null) {
    const response = await api.fetchApi(
        `/umiapp/wildcards/text/read?name=${encodeURIComponent(name)}`
        + `&ext=${encodeURIComponent(ext)}` + (source ? `&source=${encodeURIComponent(source)}` : ""));
    const data = await response.json();
    if (!response.ok || !data.success) throw new Error(data.error || "read failed");
    return { content: data.content || "", version: data.version ?? null };
}

async function fetchHealth() {
    const response = await api.fetchApi("/umiapp/wildcards/health");
    const data = await response.json();
    if (!response.ok || !data.success) throw new Error(data.error || "health check failed");
    return data;
}

/**
 * expectedVersion is the version the text was read at; the server refuses the
 * save if the file has changed since. null means the file must not exist yet.
 */
async function saveContent(name, content, ext, expectedVersion) {
    const response = await api.fetchApi("/umiapp/wildcards/text/write", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, content, ext, mode: "overwrite", expected_version: expectedVersion }),
    });
    const data = await response.json();
    if (!response.ok || !data.success) {
        const error = new Error(data.error || "write failed");
        error.conflict = !!data.conflict;
        error.version = data.version ?? null;
        throw error;
    }
    return data;
}

/**
 * What a new YAML wildcard starts as.
 *
 * Commented out, so the file parses as empty and matches nothing until it is
 * filled in. Tags and Prompts are the two fields an entry needs; the rest are
 * optional injections.
 */
export const YAML_TEMPLATE = [
    "# A YAML wildcard is a mapping of named entries.",
    "# Select one with <[Entry Name]>, or by tag with <[soft AND light]>.",
    "#",
    "# Entry Name:",
    "#   Tags: [soft, light]",
    "#   Prompts: [the prompt text, an alternative]",
    "#   Prefix: [masterpiece]",
    "#   Suffix: [bokeh]",
    "#   Neg_Prefix: [harsh]",
    "",
].join("\n");

/** Candidate lines only, matching how the engine counts them. */
export function countCandidates(text) {
    return String(text || "").split("\n")
        .filter((line) => line.trim() && !line.trim().startsWith("#")).length;
}

/**
 * Named entries in a YAML wildcard.
 *
 * A YAML file's candidates are its entries, not its lines, so counting it the
 * way a text file is counted reports a number that means nothing. This reads
 * the top-level keys without a YAML parser: an unindented line ending in a
 * colon. The server count is authoritative; this is what the editor can show
 * while you are still typing.
 */
export function countYamlEntries(text) {
    let count = 0;
    for (const raw of String(text || "").split("\n")) {
        if (!raw.trim() || raw.trim().startsWith("#")) continue;
        if (/^\S.*:\s*(#.*)?$/.test(raw)) count += 1;
    }
    return count;
}

/** Which file type an entry is, defaulting to the text wildcard. */
export function entryExt(entry) {
    return (entry && entry.ext) || "txt";
}

export function isYamlEntry(entry) {
    const ext = entryExt(entry);
    return ext === "yaml" || ext === "yml";
}

/** A stable identity. Names stopped being unique once YAML joined the list. */
export function fileKey(entry) {
    return `${entry && entry.name}.${entryExt(entry)}` + (entry?.source ? `@${entry.source}` : "");
}

/**
 * Split "folder/style.yaml" into its name and extension.
 *
 * Health findings and the new-file prompt both hand over a single string. A
 * trailing ".yaml" there is part of which file is meant, not part of its name,
 * and treating it as a name opened a different file.
 */
export function splitFileRef(ref) {
    const text = String(ref || "").trim();
    for (const ext of ["yaml", "yml", "txt"]) {
        if (text.toLowerCase().endsWith("." + ext)) {
            return { name: text.slice(0, -(ext.length + 1)), ext };
        }
    }
    return { name: text, ext: "txt" };
}

/** What one file's candidates are called, for status lines and tooltips. */
export function candidateWord(entry) {
    return isYamlEntry(entry) ? "entries" : "candidate lines";
}

/** Candidates in the editor's current text, counted for that file type. */
export function countFor(entry, text) {
    return isYamlEntry(entry) ? countYamlEntries(text) : countCandidates(text);
}

/** Things worth flagging about a file at a glance. */
export function fileFlags(entry) {
    const flags = [];
    // Checked before the null guard: a YAML file that does not parse reports
    // no count at all, and that is exactly the file worth flagging.
    if (entry.error) return ["unreadable"];
    if (entry.lines === null || entry.lines === undefined) return flags;
    if (entry.lines === 0) flags.push("empty");
    else if (entry.lines === 1) flags.push("single");
    return flags;
}

/**
 * Group flat "a/b/name" entries into nested folders.
 *
 * Returns {folders: Map<name, node>, files: [entry]} at each level, so the
 * renderer can walk it without re-parsing paths.
 */
export function buildTree(entries) {
    const root = { folders: new Map(), files: [] };
    for (const entry of entries) {
        const parts = String(entry.name || "").split("/");
        const leaf = parts.pop();
        let node = root;
        for (const part of parts) {
            if (!node.folders.has(part)) {
                node.folders.set(part, { folders: new Map(), files: [] });
            }
            node = node.folders.get(part);
        }
        // The leaf carries the extension for anything but a text wildcard,
        // so two files sharing a stem do not render as one name twice.
        const ext = (entry && entry.ext) || "txt";
        node.files.push({ ...entry, leaf: ext === "txt" ? leaf : `${leaf}.${ext}` });
    }
    return root;
}

/** Total files beneath a node, so a folder can show its own count. */
export function countTree(node) {
    let total = node.files.length;
    for (const child of node.folders.values()) total += countTree(child);
    return total;
}

// ---------------------------------------------------------------------------

class WildcardBrowser {
    constructor() {
        this.overlay = null;
        this.files = [];
        this.filter = "";
        this.selected = null;
        this.dirty = false;
        // Which folders are open, by path. Survives repaints.
        this.openFolders = new Set();
    }

    close() {
        if (this.dirty && !confirm("Discard unsaved changes to this wildcard file?")) return;
        this.overlay?.remove();
        this.overlay = null;
        this.openRequest = (this.openRequest || 0) + 1;
        this.listRequest = (this.listRequest || 0) + 1;
        this.dirty = false;
        document.removeEventListener("keydown", this._onKey);
        this.previousFocus?.focus?.();
    }

    async show() {
        if (this.overlay) return;
        this.previousFocus = document.activeElement;
        ensureStyles();
        this.render();
        await this.reload();
    }

    async reload() {
        const request = this.listRequest = (this.listRequest || 0) + 1;
        try {
            const { files, root, detailed } = await fetchFiles();
            if (request !== this.listRequest) return;
            this.files = files;
            this.root = root;
            this.detailed = detailed;
            app.extensions?.find(e => e.name === "UmiAI.WildcardSystem")?.fetchWildcards?.();
            const count = `${files.length} wildcard file${files.length === 1 ? "" : "s"}`;
            this.status(detailed
                ? count
                : `${count} — restart ComfyUI to show candidate counts and enable Health`);
        } catch (error) {
            if (request !== this.listRequest) return;
            this.files = [];
            this.status(`Could not list wildcards: ${error.message}`, "error");
        }
        this.paintList();
    }

    visible() {
        const needle = this.filter.trim().toLowerCase();
        if (!needle) return this.files;
        return this.files.filter((f) => f.name.toLowerCase().includes(needle));
    }

    status(message, tone = "") {
        if (!this.statusEl) return;
        this.statusEl.textContent = message;
        this.statusEl.dataset.tone = tone;
    }

    render() {
        this.overlay?.remove();

        const overlay = document.createElement("div");
        overlay.className = "umi-wb-overlay";
        overlay.addEventListener("mousedown", (e) => { if (e.target === overlay) this.close(); });

        const modal = document.createElement("div");
        modal.className = "umi-wb-modal";
        modal.setAttribute('role', 'dialog');
        modal.setAttribute('aria-modal', 'true');
        modal.setAttribute('aria-label', 'Wildcard editor');

        // head
        const head = document.createElement("div");
        head.className = "umi-wb-head";
        const title = document.createElement("div");
        title.className = "umi-wb-title";
        title.textContent = "Wildcards";

        const newBtn = document.createElement("button");
        newBtn.className = "umi-wb-btn";
        newBtn.textContent = "New file";
        newBtn.onclick = () => this.createFile();

        const health = document.createElement("button");
        health.title = "Check the local editable wildcard collection";
        health.className = "umi-wb-btn";
        health.textContent = "Health";
        health.onclick = () => this.showHealth();

        const refresh = document.createElement("button");
        refresh.className = "umi-wb-btn";
        refresh.textContent = "Refresh";
        refresh.onclick = () => this.reload();

        const close = document.createElement("button");
        close.className = "umi-wb-x";
        close.textContent = "×";
        close.setAttribute('aria-label', 'Close wildcard editor');
        close.onclick = () => this.close();
        head.append(title, newBtn, health, refresh, close);

        // side
        const side = document.createElement("div");
        side.className = "umi-wb-side";
        const search = document.createElement("input");
        search.className = "umi-wb-search";
        search.type = "search";
        search.placeholder = "Filter files…";
        search.setAttribute('aria-label', 'Filter wildcard files');
        search.addEventListener("input", () => {
            this.filter = search.value;
            this.paintList();
        });
        this.listEl = document.createElement("div");
        this.listEl.className = "umi-wb-list";
        side.append(search, this.listEl);

        // main
        const main = document.createElement("div");
        main.className = "umi-wb-main";

        const bar = document.createElement("div");
        bar.className = "umi-wb-bar";
        this.openEl = document.createElement("div");
        this.openEl.className = "umi-wb-open";
        this.openEl.textContent = "No file open";

        this.saveBtn = document.createElement("button");
        this.saveBtn.className = "umi-wb-btn umi-wb-btn-primary";
        this.saveBtn.textContent = "Save";
        this.saveBtn.disabled = true;
        this.saveBtn.onclick = () => this.save();
        bar.append(this.openEl, this.saveBtn);

        this.editorHost = document.createElement("div");
        this.editorHost.className = "umi-wb-empty";
        this.editorHost.textContent = "Pick a wildcard file to view or edit it.";

        this.statusEl = document.createElement("div");
        this.statusEl.className = "umi-wb-status";
        this.statusEl.setAttribute('role', 'status');

        main.append(bar, this.editorHost, this.statusEl);

        const body = document.createElement("div");
        body.className = "umi-wb-body";
        body.append(side, main);

        modal.append(head, body);
        overlay.appendChild(modal);
        document.body.appendChild(overlay);
        this.overlay = overlay;

        this._onKey = (e) => {
            if (e.key === "Escape") this.close();
            if (e.key === "s" && (e.ctrlKey || e.metaKey) && this.selected) {
                e.preventDefault();
                this.save();
            }
        };
        document.addEventListener("keydown", this._onKey);
        search.focus();
    }

    paintList() {
        if (!this.listEl) return;
        this.listEl.textContent = "";

        const rows = this.visible();
        if (!rows.length) {
            const empty = document.createElement("div");
            empty.className = "umi-wb-count";
            empty.style.padding = "10px 8px";
            empty.textContent = this.filter
                ? "No file matches that filter."
                : `No wildcard .txt files found under ${this.root || "the wildcards folder"}.`;
            this.listEl.appendChild(empty);
            return;
        }

        // A filter is a search, so results are shown flat -- folding matches
        // back into collapsed folders would hide what was just searched for.
        if (this.filter.trim()) {
            for (const entry of rows) this.listEl.appendChild(this.fileRow(entry, entry.name));
            return;
        }
        this.renderBranch(buildTree(rows), this.listEl, "");
    }

    /** One file row. `label` is the leaf inside a tree, the full path when flat. */
    fileRow(entry, label) {
        {
            const row = document.createElement("div");
            row.className = "umi-wb-file";
            row.tabIndex = 0;
            row.setAttribute('role', 'button');
            row.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); row.click(); } };
            row.setAttribute("aria-selected", String(fileKey(entry) === this.selected));
            row.title = entry.root ? `${entry.root}/${entry.relative_path || entry.name}`
                + (entry.alternatives > 1 ? ` — ${entry.alternatives} sources; listed in lookup order` : "") : "";

            const name = document.createElement("span");
            name.className = "umi-wb-name";
            name.textContent = label;

            const count = document.createElement("span");
            count.className = "umi-wb-count";
            count.textContent = (entry.lines === null || entry.lines === undefined)
                ? "" : `${entry.lines}`;
            count.title = isYamlEntry(entry)
                ? `${entry.lines} entr${entry.lines === 1 ? "y" : "ies"}`
                : `${entry.lines} candidate line(s)`
                    + (entry.comments ? `, ${entry.comments} comment(s)` : "")
                    + (entry.blank ? `, ${entry.blank} blank` : "");

            row.append(name, count);
            if (entry.root) {
                const source = document.createElement("span");
                source.className = "umi-wb-count";
                Object.assign(source.style, { maxWidth: "110px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" });
                source.textContent = (entry.readonly ? "read-only · " : "")
                    + entry.root.replace(/\\/g, "/").split("/").slice(-2).join("/");
                row.appendChild(source);
            }

            const flags = fileFlags(entry);
            if (flags.length) {
                const flag = document.createElement("span");
                flag.className = "umi-wb-flag";
                flag.textContent = flags.join(" ");
                row.appendChild(flag);
            }

            row.onclick = () => this.open(entry.name, entryExt(entry), entry.source);
            return row;
        }
    }

    /**
     * Render one level of the tree.
     *
     * Folders remember their open state in this.open_ so a repaint -- after a
     * save, or a selection change -- does not collapse everything the user
     * just opened.
     */
    renderBranch(node, host, prefix) {
        for (const [folderName, child] of [...node.folders.entries()].sort(
                (a, b) => a[0].localeCompare(b[0], undefined, { sensitivity: "base" }))) {
            const path = prefix ? prefix + "/" + folderName : folderName;
            const expanded = this.openFolders.has(path);

            const header = document.createElement("div");
            header.className = "umi-wb-folder";
            header.tabIndex = 0;
            header.setAttribute('role', 'button');
            header.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); header.click(); } };
            header.setAttribute("aria-expanded", String(expanded));

            const twisty = document.createElement("span");
            twisty.className = "umi-wb-twisty";
            twisty.textContent = "\u25b6";

            const label = document.createElement("span");
            label.className = "umi-wb-folder-name";
            label.textContent = folderName;

            const count = document.createElement("span");
            count.className = "umi-wb-count";
            count.textContent = String(countTree(child));

            header.append(twisty, label, count);

            const kids = document.createElement("div");
            kids.className = "umi-wb-kids umi-wb-indent";

            header.onclick = () => {
                if (this.openFolders.has(path)) this.openFolders.delete(path);
                else this.openFolders.add(path);
                header.setAttribute("aria-expanded", String(this.openFolders.has(path)));
            };

            host.appendChild(header);
            host.appendChild(kids);
            this.renderBranch(child, kids, path);
        }

        for (const entry of node.files.sort((a, b) =>
                a.leaf.localeCompare(b.leaf, undefined, { sensitivity: "base" }))) {
            host.appendChild(this.fileRow(entry, entry.leaf));
        }
    }

    async open(name, ext = "txt", source = null) {
        if (this.dirty && !confirm("Discard unsaved changes to this wildcard file?")) return;
        const requestId = this.openRequest = (this.openRequest || 0) + 1;
        try {
            const { content, version } = await fetchContent(name, ext, source);
            if (requestId !== this.openRequest) return;
            const entry = this.files.find(e => e.name === name && entryExt(e) === ext && (e.source || null) === source)
                || { name, ext, source };
            this.selected = fileKey(entry);
            this.selectedReadonly = !!entry.readonly;
            this.selectedName = name;
            this.selectedExt = ext;
            this.selectedVersion = version;
            this.dirty = false;

            const editor = document.createElement("textarea");
            editor.className = "umi-wb-editor";
            editor.setAttribute('aria-label', `Contents of ${name}.${ext}`);
            editor.spellcheck = false;
            editor.value = content;
            editor.readOnly = this.selectedReadonly;
            const word = candidateWord(entry);
            editor.addEventListener("input", () => {
                if (this.selectedReadonly) return;
                this.dirty = true;
                this.saveBtn.disabled = false;
                this.status(`${countFor(entry, editor.value)} ${word} — unsaved`);
            });

            this.editorHost.replaceWith(editor);
            this.editorHost = editor;
            this.editor = editor;

            // Reveal the file's folders so the selection is visible after a repaint.
            const parts = name.split("/");
            parts.pop();
            let path = "";
            for (const part of parts) {
                path = path ? path + "/" + part : part;
                this.openFolders.add(path);
            }

            // A text wildcard is used as __name__; a YAML file is selected by
            // entry or tag instead, so showing that form for it would be a lie.
            this.openEl.textContent = ext === "txt" ? `__${name}__` : `${name}.${ext}`;
            this.openEl.title = entry.root || "";
            this.saveBtn.disabled = true;
            this.status(entry.readonly
                ? `Read-only source: ${entry.root || "external folder"}. Edit this file in its source folder.`
                : `${countFor(entry, content)} ${word}`);
            this.paintList();
        } catch (error) {
            if (requestId !== this.openRequest) return;
            this.status(`Could not open ${name}: ${error.message}`, "error");
        }
    }

    async save() {
        if (!this.selected || !this.editor || this.selectedReadonly || this.saving) return;
        const editor = this.editor;
        const content = editor.value;
        this.saving = true;
        this.saveBtn.disabled = true;
        const entry = { name: this.selectedName, ext: this.selectedExt || "txt" };
        try {
            const saved = await saveContent(entry.name, content, entry.ext, this.selectedVersion);
            if (editor !== this.editor) return;
            this.selectedVersion = saved.version;
            this.dirty = editor.value !== content;
            // Reload first: it rewrites the status line with the file count, so
            // setting the confirmation before it would flash and vanish.
            await this.reload();
            if (editor !== this.editor) return;
            this.dirty = editor.value !== content;
            this.saveBtn.disabled = !this.dirty;
            const count = countFor(entry, this.editor.value);
            this.status(this.dirty ? "Saved earlier text — newer edits are still unsaved"
                : `Saved ${this.selected} — ${count} ${candidateWord(entry)}`, this.dirty ? "" : "ok");
        } catch (error) {
            if (editor !== this.editor) return;
            // The file is unchanged on disk, so the edit is still worth saving
            // once the problem is fixed. Malformed YAML is refused by the
            // server rather than written and left to fail silently later.
            this.dirty = true;
            this.saveBtn.disabled = false;
            if (error.conflict) {
                // The next Save overwrites what is on disk now: after this
                // warning that is a deliberate choice, not a silent loss.
                this.selectedVersion = error.version;
                this.status(`Not saved: ${error.message} Reopen the file to see that version, or Save again to replace it.`, "error");
                return;
            }
            this.status(`Could not save: ${error.message}`, "error");
        } finally {
            this.saving = false;
        }
    }

    async showHealth() {
        if (this.dirty && !confirm("Discard unsaved changes to this wildcard file?")) return;
        const request = this.openRequest = (this.openRequest || 0) + 1;
        this.dirty = false;
        this.selected = null;
        this.selectedName = null;
        this.selectedExt = null;
        this.saveBtn.disabled = true;
        this.openEl.textContent = "Collection health";
        this.status("Checking…");

        const view = document.createElement("div");
        view.className = "umi-wb-report";
        this.editorHost.replaceWith(view);
        this.editorHost = view;
        this.editor = null;

        let data;
        try {
            data = await fetchHealth();
        } catch (error) {
            if (request !== this.openRequest) return;
            this.status(`Health check failed: ${error.message}`, "error");
            return;
        }
        if (request !== this.openRequest) return;

        const tally = document.createElement("div");
        tally.className = "umi-wb-tally";
        tally.textContent =
            `${data.files} files · ${data.candidates} candidates · `
            + `${data.counts.error} error · ${data.counts.warn} warn · ${data.counts.info} info`;
        view.appendChild(tally);

        if (!data.findings.length) {
            const clean = document.createElement("div");
            clean.className = "umi-wb-clean";
            clean.textContent = "Nothing to report — every file has candidates and no duplicates.";
            view.appendChild(clean);
            this.status("Collection looks healthy", "ok");
            return;
        }

        for (const finding of data.findings) {
            const block = document.createElement("div");
            block.className = "umi-wb-finding";

            const heading = document.createElement("h4");
            const sev = document.createElement("span");
            sev.className = `umi-wb-sev umi-wb-sev-${finding.severity}`;
            sev.textContent = finding.severity;
            const label = document.createElement("span");
            label.textContent = `${finding.title} (${finding.total})`;
            heading.append(sev, label);

            const why = document.createElement("div");
            why.className = "umi-wb-why";
            why.textContent = finding.why;

            block.append(heading, why);

            for (const item of finding.items) {
                const row = document.createElement("div");
                row.className = "umi-wb-item";
                const name = document.createElement("span");
                name.className = "umi-wb-item-name";
                name.textContent = item.name;
                // Only a single file name can be opened; shared-line findings
                // list several and are informational.
                if (!item.name.includes(",")) {
                    const ref = splitFileRef(item.name);
                    name.onclick = () => this.open(ref.name, ref.ext);
                }
                const note = document.createElement("span");
                note.className = "umi-wb-item-note";
                note.textContent = item.note;
                row.append(name, note);
                block.appendChild(row);
            }

            if (finding.total > finding.items.length) {
                const more = document.createElement("div");
                more.className = "umi-wb-item-note";
                more.style.padding = "6px 8px";
                more.textContent = `…and ${finding.total - finding.items.length} more`;
                block.appendChild(more);
            }

            view.appendChild(block);
        }

        const worst = data.counts.error ? "error" : (data.counts.warn ? "" : "ok");
        this.status(`${data.findings.length} finding group(s)`, worst);
    }

    async createFile() {
        const typed = prompt(
            "New wildcard name (folders allowed).\n"
            + "Ends with .yaml for a YAML wildcard, otherwise a text one.");
        if (!typed || !typed.trim()) return;
        const { name: clean, ext } = splitFileRef(typed);
        if (!clean) return;
        // A new YAML file opens on a commented template. It parses as empty, so
        // it matches nothing until something is filled in, but the shape of an
        // entry is visible rather than having to be remembered.
        const seed = (ext === "txt") ? "" : YAML_TEMPLATE;
        try {
            await saveContent(clean, seed, ext, null);
            await this.reload();
            await this.open(clean, ext);
            this.status(`Created ${clean}.${ext}`, "ok");
        } catch (error) {
            if (error.conflict) {
                // Creating over an existing file used to empty it.
                await this.open(clean, ext);
                this.status(`${clean}.${ext} already exists — opened it instead`, "error");
                return;
            }
            this.status(`Could not create ${clean}.${ext}: ${error.message}`, "error");
        }
    }
}

const browser = new WildcardBrowser();
window.umiWildcardBrowser = browser;

app.registerExtension({
    name: "Umi.WildcardBrowser",
    async setup() { ensureStyles(); },
});

export { WildcardBrowser, fetchFiles };
