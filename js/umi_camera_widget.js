/**
 * UmiAI Visual Camera Control Widget
 * Ported from VNCCS Utils - interactive canvas for camera angle selection.
 */

import { app } from "../../scripts/app.js";

// --- Configuration Constants ---
const CANVAS_SIZE = 320;
const CENTER_X = 160;
const CENTER_Y = 160;
const RADIUS_WIDE = 140;
const RADIUS_MEDIUM = 90;
const RADIUS_CLOSE = 50;

// Colors
const COLOR_BG = "#1a1a1a";
const COLOR_GRID_LINES = "#444";
const COLOR_TEXT = "#888";
const COLOR_ACTIVE = "#ffbd45";
const COLOR_HIGHLIGHT = "#ffffff";

// Data
const ELEVATION_STEPS = [-30, 0, 30, 60];
const DISTANCE_MAP = {
    "close-up": RADIUS_CLOSE,
    "medium shot": RADIUS_MEDIUM,
    "wide shot": RADIUS_WIDE
};
const DISTANCE_REVERSE_MAP = {
    [RADIUS_CLOSE]: "close-up",
    [RADIUS_MEDIUM]: "medium shot",
    [RADIUS_WIDE]: "wide shot"
};

// --- Custom Widget Class ---
class UmiCameraWidget {
    constructor(node, inputName, inputData, app) {
        this.node = node;
        this.inputName = inputName;
        this.app = app;

        // Internal State
        this.state = {
            azimuth: 0,
            elevation: 0,
            distance: "medium shot",
            include_trigger: true
        };

        // Try load initial state
        try {
            if (this.node.widgets && this.node.widgets[0]) {
                const loaded = JSON.parse(this.node.widgets[0].value);
                this.state = { ...this.state, ...loaded };
            }
        } catch (e) { }

        this.isDragging = false;
        this.dragMode = null; // 'azimuth' or 'elevation'

        // Create Canvas Element
        this.canvas = document.createElement("canvas");
        this.canvas.width = CANVAS_SIZE;
        this.canvas.height = CANVAS_SIZE;
        this.canvas.style.borderRadius = "4px";
        this.ctx = this.canvas.getContext("2d");

        // UI Event Listeners
        this.canvas.addEventListener("mousedown", this.onMouseDown.bind(this));
        document.addEventListener("mousemove", this.onMouseMove.bind(this));
        document.addEventListener("mouseup", this.onMouseUp.bind(this));

        // Initial Draw
        this.draw();
    }

    // --- Drawing Logic ---
    draw() {
        const ctx = this.ctx;
        ctx.fillStyle = COLOR_BG;
        ctx.fillRect(0, 0, CANVAS_SIZE, CANVAS_SIZE);

        this.drawGrid(ctx);
        this.drawSubject(ctx);
        this.drawCameraTriangle(ctx);
        this.drawElevationBar(ctx);
        this.drawInfoText(ctx);
    }

    drawGrid(ctx) {
        // Draw Circles (distance rings)
        ctx.strokeStyle = COLOR_GRID_LINES;
        ctx.lineWidth = 1;

        [RADIUS_CLOSE, RADIUS_MEDIUM, RADIUS_WIDE].forEach(r => {
            ctx.beginPath();
            ctx.arc(CENTER_X, CENTER_Y, r, 0, Math.PI * 2);
            ctx.stroke();
        });

        // Draw Axes
        ctx.beginPath();
        ctx.moveTo(CENTER_X - RADIUS_WIDE, CENTER_Y);
        ctx.lineTo(CENTER_X + RADIUS_WIDE, CENTER_Y);
        ctx.moveTo(CENTER_X, CENTER_Y - RADIUS_WIDE);
        ctx.lineTo(CENTER_X, CENTER_Y + RADIUS_WIDE);

        // Diagonals (45 degree lines)
        const diag = RADIUS_WIDE * 0.707;
        ctx.moveTo(CENTER_X - diag, CENTER_Y - diag);
        ctx.lineTo(CENTER_X + diag, CENTER_Y + diag);
        ctx.moveTo(CENTER_X + diag, CENTER_Y - diag);
        ctx.lineTo(CENTER_X - diag, CENTER_Y + diag);
        ctx.stroke();

        // Labels for directions
        ctx.fillStyle = "#555";
        ctx.font = "10px sans-serif";
        ctx.textAlign = "center";
        ctx.fillText("Front", CENTER_X, 15);
        ctx.fillText("Back", CENTER_X, CANVAS_SIZE - 55);
        ctx.fillText("Left", 25, CENTER_Y + 4);
        ctx.fillText("Right", CANVAS_SIZE - 45, CENTER_Y + 4);
    }

    drawSubject(ctx) {
        // Subject indicator in center
        ctx.fillStyle = "#666";
        ctx.beginPath();
        ctx.arc(CENTER_X, CENTER_Y, 8, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = "#888";
        ctx.font = "8px sans-serif";
        ctx.textAlign = "center";
        ctx.fillText("S", CENTER_X, CENTER_Y + 3);
    }

    drawCameraTriangle(ctx) {
        const r = DISTANCE_MAP[this.state.distance];
        // Convert azimuth to math angle (0=Front/Top, 90=Right)
        const angleRad = (this.state.azimuth - 90) * (Math.PI / 180);

        const cx = CENTER_X + r * Math.cos(angleRad);
        const cy = CENTER_Y + r * Math.sin(angleRad);

        ctx.save();
        ctx.translate(cx, cy);
        ctx.rotate(angleRad + Math.PI / 2); // Point towards center

        // Camera triangle shape
        ctx.fillStyle = COLOR_ACTIVE;
        ctx.strokeStyle = "#000";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(0, 10); // Pointing IN
        ctx.lineTo(-8, -8);
        ctx.lineTo(8, -8);
        ctx.closePath();
        ctx.fill();
        ctx.stroke();

        ctx.restore();
    }

    drawElevationBar(ctx) {
        // Vertical slider on the right
        const barX = CANVAS_SIZE - 20;
        const barH = 200;
        const barY = (CANVAS_SIZE - barH) / 2;

        // Track line
        ctx.strokeStyle = COLOR_GRID_LINES;
        ctx.lineWidth = 4;
        ctx.beginPath();
        ctx.moveTo(barX, barY);
        ctx.lineTo(barX, barY + barH);
        ctx.stroke();

        // Elevation ticks
        ELEVATION_STEPS.forEach(step => {
            const norm = (step + 30) / 90; // 0..1
            const y = barY + barH - (norm * barH);

            ctx.fillStyle = (step === this.state.elevation) ? COLOR_ACTIVE : "#666";
            ctx.beginPath();
            ctx.arc(barX, y, 4, 0, Math.PI * 2);
            ctx.fill();

            // Text labels
            ctx.fillStyle = "#888";
            ctx.font = "10px sans-serif";
            ctx.textAlign = "right";
            ctx.fillText(step + "°", barX - 8, y + 3);
        });

        // Current indicator
        const currentNorm = (this.state.elevation + 30) / 90;
        const curY = barY + barH - (currentNorm * barH);
        ctx.fillStyle = COLOR_ACTIVE;
        ctx.beginPath();
        ctx.arc(barX, curY, 6, 0, Math.PI * 2);
        ctx.fill();
    }

    drawInfoText(ctx) {
        ctx.fillStyle = COLOR_TEXT;
        ctx.font = "12px monospace";
        ctx.textAlign = "left";
        ctx.fillText(`Azimuth:   ${this.state.azimuth}°`, 10, CANVAS_SIZE - 40);
        ctx.fillText(`Elevation: ${this.state.elevation}°`, 10, CANVAS_SIZE - 25);
        ctx.fillText(`Distance:  ${this.state.distance}`, 10, CANVAS_SIZE - 10);

        // Trigger status indicator
        ctx.fillStyle = this.state.include_trigger ? "#4a4" : "#a44";
        ctx.fillRect(CANVAS_SIZE - 20, CANVAS_SIZE - 20, 10, 10);
        ctx.fillStyle = "#666";
        ctx.font = "8px sans-serif";
        ctx.fillText("<sks>", CANVAS_SIZE - 45, CANVAS_SIZE - 12);
    }

    // --- Interaction ---
    onMouseDown(e) {
        const rect = this.canvas.getBoundingClientRect();
        const scaleX = this.canvas.width / rect.width;
        const scaleY = this.canvas.height / rect.height;

        const x = (e.clientX - rect.left) * scaleX;
        const y = (e.clientY - rect.top) * scaleY;

        // Check Elevation Bar
        const barX = CANVAS_SIZE - 20;
        if (Math.abs(x - barX) < 20) {
            this.isDragging = true;
            this.dragMode = 'elevation';
            this.updateElevation(y);
            return;
        }

        // Check Trigger toggle
        if (x > CANVAS_SIZE - 30 && y > CANVAS_SIZE - 30) {
            this.state.include_trigger = !this.state.include_trigger;
            this.updateNode();
            this.draw();
            return;
        }

        // Default: Azimuth/Distance
        this.isDragging = true;
        this.dragMode = 'azimuth';
        this.updatePos(x, y);
    }

    onMouseMove(e) {
        if (!this.isDragging) return;
        const rect = this.canvas.getBoundingClientRect();
        const scaleX = this.canvas.width / rect.width;
        const scaleY = this.canvas.height / rect.height;

        const x = (e.clientX - rect.left) * scaleX;
        const y = (e.clientY - rect.top) * scaleY;

        if (this.dragMode === 'elevation') {
            this.updateElevation(y);
        } else {
            this.updatePos(x, y);
        }
    }

    onMouseUp(e) {
        this.isDragging = false;
        this.dragMode = null;
    }

    updatePos(x, y) {
        // Calculate angle from center
        const dx = x - CENTER_X;
        const dy = y - CENTER_Y;
        let angleRad = Math.atan2(dy, dx);

        // Convert to Azimuth (0=Top, 90=Right)
        let deg = (angleRad * 180 / Math.PI) + 90;
        if (deg < 0) deg += 360;

        // Snap to 45 degrees
        this.state.azimuth = Math.round(deg / 45) * 45;
        if (this.state.azimuth >= 360) this.state.azimuth = 0;

        // Calculate distance (radius)
        const dist = Math.sqrt(dx * dx + dy * dy);

        // Snap to rings
        const dists = [RADIUS_CLOSE, RADIUS_MEDIUM, RADIUS_WIDE];
        const closest = dists.reduce((prev, curr) =>
            Math.abs(curr - dist) < Math.abs(prev - dist) ? curr : prev
        );

        this.state.distance = DISTANCE_REVERSE_MAP[closest];

        this.updateNode();
        this.draw();
    }

    updateElevation(y) {
        const barH = 200;
        const barY = (CANVAS_SIZE - barH) / 2;

        // Map Y to elevation
        let norm = (barY + barH - y) / barH;
        if (norm < 0) norm = 0;
        if (norm > 1) norm = 1;

        let deg = norm * 90 - 30;

        // Snap to steps
        const closest = ELEVATION_STEPS.reduce((prev, curr) =>
            Math.abs(curr - deg) < Math.abs(prev - deg) ? curr : prev
        );

        this.state.elevation = closest;
        this.updateNode();
        this.draw();
    }

    updateNode() {
        // Serialize state to the hidden widget
        if (this.node.widgets && this.node.widgets[0]) {
            this.node.widgets[0].value = JSON.stringify(this.state);
        }
    }
}


// --- Extension Registration ---
app.registerExtension({
    name: "Umi.VisualCameraControl",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name === "UmiVisualCameraControl") {
            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                if (onNodeCreated) {
                    onNodeCreated.apply(this, arguments);
                }

                // Add Custom Widget
                const widget = new UmiCameraWidget(this, "camera_data", {}, app);

                // Add the canvas to the node
                this.addDOMWidget("CameraControl", "canvas", widget.canvas, {
                    serialize: false,
                    hideOnZoom: false
                });

                // Force initial update
                widget.updateNode();

                // Set node size
                this.setSize([340, 380]);
            };
        }
    }
});

console.log("[UmiAI] Visual Camera Control widget loaded");
